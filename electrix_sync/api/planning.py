from datetime import timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, get_system_timezone, nowdate

from electrix_sync.api.master_data import get_staged
from electrix_sync.api.stel import StelClient
from electrix_sync.api.sync import (
    ensure_stel_event_type,
    get_catalog_names,
    get_stel_event_state,
    get_stel_id,
    match_employee_calendar,
)


@frappe.whitelist()
def get_board(start_date=None, days=7):
    ensure_calendar_assignments()
    start_date = get_datetime(start_date or nowdate()).date()
    days = max(1, min(int(days or 7), 14))
    end_date = add_days(start_date, days)

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "designation", "user_id", "custom_stel_calendar_id"],
        order_by="employee_name asc",
    )
    fields = [
        "name",
        "subject",
        "description",
        "starts_on",
        "ends_on",
        "status",
        "custom_stel_id",
        "custom_stel_event_type",
        "custom_stel_event_type_name",
        "custom_stel_event_state",
        "custom_stel_calendar_id",
        "custom_assigned_employee",
        "custom_planning_status",
        "custom_estimated_duration",
    ]
    planned = frappe.get_all(
        "Event",
        filters={"starts_on": ["between", [str(start_date), str(end_date)]]},
        fields=fields,
        order_by="starts_on asc",
        limit_page_length=2000,
    )
    unplanned = frappe.get_all(
        "Event",
        filters={"custom_planning_status": "Unplanned", "status": ["!=", "Closed"]},
        fields=fields,
        order_by="modified desc",
        limit_page_length=500,
    )
    return {
        "start_date": str(start_date),
        "days": [str(add_days(start_date, offset)) for offset in range(days)],
        "employees": employees,
        "events": planned,
        "unplanned": unplanned,
    }


def ensure_calendar_assignments():
    active_count = frappe.db.count("Employee", {"status": "Active"})
    mapped_count = frappe.db.count(
        "Employee", {"status": "Active", "custom_stel_calendar_id": ["is", "set"]}
    )
    if active_count and mapped_count == 0:
        repair_calendar_assignments()


@frappe.whitelist()
def repair_calendar_assignments(refresh=False):
    # Planning must never spend STEL API quota merely by opening the page.
    # Calendars and events are rebuilt from the most recent immutable staging
    # snapshot instead.
    refresh = str(refresh).lower() in {"1", "true", "yes"}
    calendars = StelClient().get_calendars() if refresh else [row["data"] for row in get_staged("calendars")]
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "custom_stel_id"],
    )
    employee_by_calendar = {}
    mapped_employees = 0
    unmatched_employees = []

    for employee in employees:
        calendar_id = match_employee_calendar(
            {"id": employee.custom_stel_id, "name": employee.employee_name}, calendars
        )
        if not calendar_id:
            unmatched_employees.append({
                "employee": employee.name,
                "employee_name": employee.employee_name,
                "stel_id": employee.custom_stel_id,
            })
            continue
        frappe.db.set_value(
            "Employee", employee.name, "custom_stel_calendar_id", str(calendar_id), update_modified=False
        )
        employee_by_calendar[str(calendar_id)] = employee.name
        mapped_employees += 1

    staged_events = [row["data"] for row in get_staged("events")]
    event_type_names = get_catalog_names([row["data"] for row in get_staged("event_types")])
    stel_events = {str(get_stel_id(row)): row for row in staged_events if get_stel_id(row)}
    erp_events = frappe.get_all(
        "Event",
        filters={"custom_stel_id": ["is", "set"]},
        fields=["name", "custom_stel_id", "starts_on", "ends_on", "status"],
        limit_page_length=10000,
    )
    mapped_events = 0
    for event in erp_events:
        source = stel_events.get(str(event.custom_stel_id))
        if not source:
            continue
        calendar_id = source.get("calendarId") or source.get("calendar-id")
        employee = employee_by_calendar.get(str(calendar_id)) if calendar_id else None
        starts_on = source.get("startDate") or source.get("start-date") or event.starts_on
        ends_on = source.get("endDate") or source.get("end-date") or event.ends_on
        state = str(source.get("state") or source.get("event-state") or "").upper()
        event_type_id = source.get("eventTypeId") or source.get("event-type-id")
        if event_type_id:
            event_type_id = str(event_type_id)
            ensure_stel_event_type(event_type_id, event_type_names.get(event_type_id))
        planning_status = "Completed" if state == "COMPLETED" else (
            "Planned" if employee and starts_on and ends_on else "Unplanned"
        )
        frappe.db.set_value(
            "Event",
            event.name,
            {
                "custom_stel_calendar_id": str(calendar_id) if calendar_id else None,
                "custom_stel_event_type": event_type_id,
                "custom_stel_event_state": get_stel_event_state(source),
                "custom_assigned_employee": employee,
                "custom_planning_status": planning_status,
            },
            update_modified=False,
        )
        if planning_status != "Unplanned":
            mapped_events += 1

    frappe.db.commit()
    return {
        "employees": mapped_employees,
        "events": mapped_events,
        "calendars": len(calendars),
        "unmatched": unmatched_employees,
        "source": "STEL API" if refresh else "staging",
    }


@frappe.whitelist()
def plan_event(event_name, employee, starts_on, ends_on=None):
    event = frappe.get_doc("Event", event_name)
    event.check_permission("write")
    employee_doc = frappe.get_doc("Employee", employee)
    calendar_id = employee_doc.get("custom_stel_calendar_id")
    if not calendar_id:
        frappe.throw(_("Employee {0} has no STEL calendar assigned").format(employee_doc.employee_name))

    starts_on = get_datetime(starts_on)
    duration = float(event.get("custom_estimated_duration") or 1)
    ends_on = get_datetime(ends_on) if ends_on else starts_on + timedelta(hours=duration)
    if ends_on <= starts_on:
        frappe.throw(_("End time must be after start time"))

    old_calendar_id = event.get("custom_stel_calendar_id")
    if event.get("custom_stel_id"):
        if str(old_calendar_id or "") != str(calendar_id):
            replace_stel_event(event, calendar_id, starts_on, ends_on)
        else:
            update_stel_event(event, starts_on, ends_on)

    event.starts_on = starts_on
    event.ends_on = ends_on
    event.custom_assigned_employee = employee
    event.custom_stel_calendar_id = str(calendar_id)
    event.custom_planning_status = "Planned"
    event.custom_estimated_duration = (ends_on - starts_on).total_seconds() / 3600
    event.flags.skip_stel_outbound = True
    event.save(ignore_permissions=True)
    set_event_participant(event, employee_doc.get("user_id"))
    return {"name": event.name, "stel_id": event.custom_stel_id}


@frappe.whitelist()
def resize_event(event_name, starts_on, ends_on):
    event = frappe.get_doc("Event", event_name)
    event.check_permission("write")
    starts_on = get_datetime(starts_on)
    ends_on = get_datetime(ends_on)
    if ends_on <= starts_on:
        frappe.throw(_("End time must be after start time"))
    if event.get("custom_stel_id"):
        update_stel_event(event, starts_on, ends_on)
    event.starts_on = starts_on
    event.ends_on = ends_on
    event.custom_estimated_duration = (ends_on - starts_on).total_seconds() / 3600
    event.flags.skip_stel_outbound = True
    event.save(ignore_permissions=True)
    return {"name": event.name}


def update_stel_event(event, starts_on, ends_on):
    payload = {
        "start-date": stel_datetime(starts_on),
        "end-date": stel_datetime(ends_on),
        "event-state": erp_event_state(event),
    }
    StelClient().update_event(event.custom_stel_id, payload)


def replace_stel_event(event, calendar_id, starts_on, ends_on):
    client = StelClient()
    payload = {
        "subject": (event.subject or "")[:128],
        "description": (event.description or "")[:5000],
        "start-date": stel_datetime(starts_on),
        "end-date": stel_datetime(ends_on),
        "all-day": bool(event.get("all_day")),
        "calendar-id": int(calendar_id),
        "event-state": erp_event_state(event),
    }
    created = client.create_event(payload)
    new_id = extract_stel_id(created)
    if not new_id:
        frappe.throw(_("STEL created the event but did not return its ID"))
    try:
        client.delete_event(event.custom_stel_id)
    except Exception:
        try:
            client.delete_event(new_id)
        except Exception:
            pass
        raise
    event.custom_stel_id = str(new_id)


def set_event_participant(event, user):
    if not user or not event.meta.has_field("event_participants"):
        return
    event.set("event_participants", [])
    event.append("event_participants", {"reference_doctype": "User", "reference_docname": user})
    event.save(ignore_permissions=True)


def extract_stel_id(response):
    if isinstance(response, list) and response:
        return extract_stel_id(response[0])
    if isinstance(response, dict):
        for key in ("id", "ID"):
            if response.get(key):
                return response[key]
        for key in ("data", "item", "result"):
            value = response.get(key)
            if isinstance(value, dict) and value.get("id"):
                return value["id"]
    return None


def stel_datetime(value):
    value = get_datetime(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(get_system_timezone()))
    return value.strftime("%Y-%m-%dT%H:%M:%S%z")


def erp_event_state(event):
    state = str(event.get("custom_stel_event_state") or "").upper()
    if state in {"PENDING", "COMPLETED", "REFUSED"}:
        return state
    if event.get("status") == "Cancelled":
        return "REFUSED"
    return "COMPLETED" if event.get("status") == "Closed" else "PENDING"
