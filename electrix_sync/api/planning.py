from datetime import timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, get_system_timezone, nowdate

from electrix_sync.api.master_data import get_staged
from electrix_sync.api.stel import StelClient
from electrix_sync.api.sync import (
    get_catalog_names,
    get_event_status,
    delete_missing_stel_events,
    get_stel_id,
    match_employee_calendar,
    normalize_stel_event_datetime,
    normalize_event_category,
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
        "custom_stel_calendar_id",
        "custom_assigned_employee",
        "custom_planning_status",
        "custom_estimated_duration",
    ]
    if frappe.get_meta("Event").has_field("event_category"):
        fields.append("event_category")
    for fieldname in ("location", "reference_doctype", "reference_docname"):
        if frappe.get_meta("Event").has_field(fieldname):
            fields.append(fieldname)
    planned = frappe.get_all(
        "Event",
        filters={"starts_on": ["between", [str(start_date), str(end_date)]]},
        fields=fields,
        order_by="starts_on asc",
        limit_page_length=2000,
    )
    unplanned = frappe.get_all(
        "Event",
        filters={"custom_planning_status": "Unplanned", "status": ["not in", ["Closed", "Cancelled"]]},
        fields=fields,
        order_by="modified desc",
        limit_page_length=500,
    )
    all_events = {row.name: row for row in [*planned, *unplanned]}
    for event in all_events.values():
        event["assigned_employees"] = [event.custom_assigned_employee] if event.custom_assigned_employee else []
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
    client = StelClient() if refresh else None
    calendars = client.get_calendars() if client else [row["data"] for row in get_staged("calendars")]
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

    # A manual calendar repair must also reload events. Otherwise already
    # imported rows retain historical timezone conversions forever because the
    # incremental job only requests records modified after its last cursor.
    staged_events = client.get_events() if client else [row["data"] for row in get_staged("events")]
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
        event_status = get_event_status(source)
        event_type_id = source.get("eventTypeId") or source.get("event-type-id")
        event_category = event_type_names.get(str(event_type_id)) if event_type_id else None
        event_category = normalize_event_category(event_category) if event_category else None
        planning_status = "Completed" if event_status == "Closed" else (
            "Planned" if employee and starts_on and ends_on else "Unplanned"
        )
        frappe.db.set_value(
            "Event",
            event.name,
            {
                "custom_stel_calendar_id": str(calendar_id) if calendar_id else None,
                "custom_assigned_employee": employee,
                "custom_planning_status": planning_status,
                "status": event_status,
                **({"event_category": event_category} if frappe.get_meta("Event").has_field("event_category") else {}),
                "starts_on": normalize_stel_event_datetime(starts_on),
                "ends_on": normalize_stel_event_datetime(ends_on),
                "description": str(source.get("description") or "").strip(),
            },
            update_modified=False,
        )
        if planning_status != "Unplanned":
            mapped_events += 1

    deleted_events = 0
    if client:
        deleted_events = delete_missing_stel_events(staged_events, employee_by_calendar.keys())

    frappe.db.commit()
    return {
        "employees": mapped_employees,
        "events": mapped_events,
        "deleted_events": deleted_events,
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

    event.starts_on = starts_on
    event.ends_on = ends_on
    if event.get("custom_stel_id"):
        if str(event.get("custom_stel_calendar_id") or "") == str(calendar_id):
            update_stel_event_copy(event, event.custom_stel_id, starts_on, ends_on)
        else:
            event.custom_stel_id = replace_stel_event(event, calendar_id, starts_on, ends_on)
    else:
        event.custom_stel_id = create_stel_event(event, calendar_id, starts_on, ends_on)
    event.custom_assigned_employee = employee
    event.custom_stel_calendar_id = str(calendar_id)
    event.custom_planning_status = "Planned"
    event.custom_estimated_duration = (ends_on - starts_on).total_seconds() / 3600
    event.flags.skip_stel_outbound = True
    event.save(ignore_permissions=True)
    set_event_participant(event, employee_doc.get("user_id"))
    return {"name": event.name, "stel_id": event.custom_stel_id}


@frappe.whitelist()
def create_planned_event(employee, subject, starts_on, ends_on, description=None, event_category=None, status="Open", location=None, employees=None):
    employee_doc = frappe.get_doc("Employee", employee)
    if not employee_doc.get("custom_stel_calendar_id"):
        frappe.throw(_("Employee {0} has no STEL calendar assigned").format(employee_doc.employee_name))
    starts_on = get_datetime(starts_on)
    ends_on = get_datetime(ends_on)
    if ends_on <= starts_on:
        frappe.throw(_("End time must be after start time"))
    event = frappe.new_doc("Event")
    event.subject = subject
    event.description = description
    event.starts_on = starts_on
    event.ends_on = ends_on
    event.event_type = "Private"
    event.status = normalize_event_status(status)
    if event.meta.has_field("event_category"):
        event.event_category = event_category or None
    if event.meta.has_field("location"):
        event.location = location or None
    event.custom_assigned_employee = employee
    event.custom_stel_calendar_id = str(employee_doc.custom_stel_calendar_id)
    event.custom_planning_status = "Planned"
    event.custom_estimated_duration = (ends_on - starts_on).total_seconds() / 3600
    event.flags.skip_stel_outbound = True
    event.insert(ignore_permissions=True)
    event.custom_stel_id = create_stel_event(event, employee_doc.custom_stel_calendar_id, starts_on, ends_on)
    event.flags.skip_stel_outbound = True
    event.save(ignore_permissions=True)
    set_event_participant(event, employee_doc.get("user_id"))
    return {"name": event.name, "stel_id": event.custom_stel_id}


@frappe.whitelist()
def edit_planned_event(event_name, subject, starts_on, ends_on, description=None, event_category=None, status="Open", location=None, employee=None, employees=None):
    event = frappe.get_doc("Event", event_name)
    event.check_permission("write")
    starts_on = get_datetime(starts_on)
    ends_on = get_datetime(ends_on)
    if ends_on <= starts_on:
        frappe.throw(_("End time must be after start time"))
    event.subject = subject
    event.description = description
    event.starts_on = starts_on
    event.ends_on = ends_on
    event.status = normalize_event_status(status)
    if event.meta.has_field("event_category"):
        event.event_category = event_category or None
    if event.meta.has_field("location"):
        event.location = location or None
    event.custom_estimated_duration = (ends_on - starts_on).total_seconds() / 3600
    employee = employee or event.get("custom_assigned_employee")
    if employee:
        employee_doc = frappe.get_doc("Employee", employee)
        calendar_id = employee_doc.get("custom_stel_calendar_id")
        if not calendar_id:
            frappe.throw(_("Employee {0} has no STEL calendar assigned").format(employee_doc.employee_name))
        if event.get("custom_stel_id") and str(event.get("custom_stel_calendar_id") or "") == str(calendar_id):
            update_stel_event_copy(event, event.custom_stel_id, starts_on, ends_on)
        elif event.get("custom_stel_id"):
            event.custom_stel_id = replace_stel_event(event, calendar_id, starts_on, ends_on)
        else:
            event.custom_stel_id = create_stel_event(event, calendar_id, starts_on, ends_on)
        event.custom_assigned_employee = employee
        event.custom_stel_calendar_id = str(calendar_id)
    event.flags.skip_stel_outbound = True
    event.save(ignore_permissions=True)
    return {"name": event.name, "stel_id": event.custom_stel_id}


@frappe.whitelist()
def unplan_event(event_name):
    event = frappe.get_doc("Event", event_name)
    event.check_permission("write")
    if event.get("custom_stel_id"):
        StelClient().delete_event(event.custom_stel_id)
    event.custom_stel_id = None
    event.custom_stel_calendar_id = None
    event.custom_assigned_employee = None
    event.custom_planning_status = "Unplanned"
    event.flags.skip_stel_outbound = True
    event.save(ignore_permissions=True)
    return {"name": event.name}


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
    event_type_id = get_catalog_id("event_types", event.get("event_category"))
    if event_type_id:
        payload["event-type-id"] = int(event_type_id)
    add_standard_event_relations(event, payload)
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
    return str(new_id)


@frappe.whitelist()
def duplicate_event(event_name, starts_on=None, employee=None):
    """Duplicate one ERP/STEL event for the selected employee."""
    source = frappe.get_doc("Event", event_name)
    source.check_permission("read")
    employee = employee or source.get("custom_assigned_employee")
    if not employee:
        frappe.throw(_("Select an employee before duplicating the event"))
    start = get_datetime(starts_on or source.starts_on)
    duration = max(get_datetime(source.ends_on or source.starts_on) - get_datetime(source.starts_on), timedelta(minutes=15))
    return create_planned_event(
        employee=employee, subject=source.subject, starts_on=start, ends_on=start + duration,
        description=source.description, event_category=source.get("event_category"), status=source.status,
        location=source.get("location"),
    )


def create_stel_event(event, calendar_id, starts_on, ends_on):
    payload = {
        "subject": (event.subject or "")[:128],
        "description": (event.description or "")[:5000],
        "start-date": stel_datetime(starts_on),
        "end-date": stel_datetime(ends_on),
        "all-day": bool(event.get("all_day")),
        "calendar-id": int(calendar_id),
        "event-state": erp_event_state(event),
    }
    event_type_id = get_catalog_id("event_types", event.get("event_category"))
    if event_type_id:
        payload["event-type-id"] = int(event_type_id)
    add_standard_event_relations(event, payload)
    created = StelClient().create_event(payload)
    new_id = extract_stel_id(created)
    if not new_id:
        frappe.throw(_("STEL created the event but did not return its ID"))
    return str(new_id)


def update_stel_event_copy(event, stel_event_id, starts_on, ends_on):
    payload = {
        "subject": (event.subject or "")[:128],
        "description": (event.description or "")[:5000],
        "start-date": stel_datetime(starts_on),
        "end-date": stel_datetime(ends_on),
        "all-day": bool(event.get("all_day")),
        "event-state": erp_event_state(event),
    }
    event_type_id = get_catalog_id("event_types", event.get("event_category"))
    if event_type_id:
        payload["event-type-id"] = int(event_type_id)
    add_standard_event_relations(event, payload)
    StelClient().update_event(stel_event_id, payload)


def set_event_participant(event, user):
    set_event_participants(event, [user] if user else [])


def set_event_participants(event, users):
    users = list(dict.fromkeys(user for user in users if user))
    if not users or not event.meta.has_field("event_participants"):
        return
    event.set("event_participants", [])
    for user in users:
        event.append("event_participants", {"reference_doctype": "User", "reference_docname": user})
    event.flags.skip_stel_outbound = True
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
    if event.get("status") == "Cancelled":
        return "REFUSED"
    return "COMPLETED" if event.get("status") == "Closed" else "PENDING"


def normalize_event_status(status):
    status = str(status or "Open")
    aliases = {"PENDING": "Open", "COMPLETED": "Closed", "REFUSED": "Cancelled"}
    return aliases.get(status.upper(), status if status in {"Open", "Closed", "Cancelled"} else "Open")


def get_catalog_id(resource_type, name):
    target = str(name or "").strip().casefold()
    if not target:
        return None
    aliases = {
        "event": {"event", "evento", "visita"},
        "meeting": {"meeting", "reunión", "reunion"},
        "call": {"call", "llamada"},
        "sent/received email": {"email", "correo", "mail", "sent/received email"},
        "other": {"other", "otro"},
    }
    candidates = aliases.get(target, {target})
    for row in get_staged(resource_type):
        source_name = str(row["data"].get("name") or "").strip().casefold()
        if source_name in candidates:
            return row["remote_id"]
    return None


def add_standard_event_relations(event, payload):
    if event.meta.has_field("location") and event.get("location"):
        payload["location"] = str(event.location)[:128]
    if event.get("reference_doctype") == "Customer" and event.get("reference_docname"):
        account_id = frappe.db.get_value("Customer", event.reference_docname, "custom_stel_id")
        if account_id:
            payload["account-id"] = int(account_id)
