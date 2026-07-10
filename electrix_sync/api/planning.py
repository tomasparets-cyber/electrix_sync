from datetime import timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, get_system_timezone, nowdate

from electrix_sync.api.stel import StelClient


@frappe.whitelist()
def get_board(start_date=None, days=7):
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
    planned_names = {row.name for row in planned}

    return {
        "start_date": str(start_date),
        "days": [str(add_days(start_date, offset)) for offset in range(days)],
        "employees": employees,
        "events": planned,
        "unplanned": [row for row in unplanned if row.name not in planned_names],
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
    return "COMPLETED" if event.get("status") == "Closed" else "PENDING"
