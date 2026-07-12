from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from electrix_sync.api.bulk_sync import format_stel_utc
from electrix_sync.api.master_data import get_staged
from electrix_sync.api.stel import StelClient
from electrix_sync.api.sync import get_catalog_names, match_employee_calendar, sync_event, sync_incident


def sync_event_calendars():
    """Near-real-time STEL calendar pull, budgeted for the public API limits."""
    if frappe.db.exists("STEL Bulk Sync Run", {"status": ["in", ["Queued", "Running"]]}):
        return {"skipped": "bulk sync running"}

    settings = frappe.get_single("Electrix Sync Settings")
    started_at = now_datetime()
    since = settings.last_event_calendar_sync or (started_at - timedelta(minutes=10))
    client = StelClient()
    staged_calendars = [row["data"] for row in get_staged("calendars")]
    calendars = client.get_calendars() if started_at.minute < 5 or not staged_calendars else staged_calendars
    mapped = map_employee_calendars(calendars)
    filters = {"utc-last-modification-date": format_stel_utc(since)}
    events = client.get_collection("/app/events", filters=filters)
    incidents = client.get_collection("/app/incidents", filters=filters)
    event_type_names = get_catalog_names([row["data"] for row in get_staged("event_types")])
    incident_state_names = get_catalog_names([row["data"] for row in get_staged("incident_states")])
    incident_type_names = get_catalog_names([row["data"] for row in get_staged("incident_types")])

    previous_flag = getattr(frappe.flags, "in_stel_sync", False)
    frappe.flags.in_stel_sync = True
    try:
        results = {"created": 0, "updated": 0, "skipped": 0, "error": 0}
        for item in events:
            action = sync_event(item, event_type_names)
            results[action if action in results else "error"] += 1
        incident_results = {"created": 0, "updated": 0, "skipped": 0, "error": 0}
        for item in incidents:
            action = sync_incident(item, incident_state_names, incident_type_names)
            incident_results[action if action in incident_results else "error"] += 1
        frappe.db.set_single_value("Electrix Sync Settings", "last_event_calendar_sync", started_at)
        frappe.db.commit()
    finally:
        frappe.flags.in_stel_sync = previous_flag
    return {"calendars": len(calendars), "employees": mapped, "events": results, "tasks": incident_results}


def map_employee_calendars(calendars):
    mapped = 0
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "custom_stel_id", "custom_stel_calendar_id"],
    )
    for employee in employees:
        calendar_id = match_employee_calendar(
            {"id": employee.custom_stel_id, "name": employee.employee_name}, calendars
        )
        if not calendar_id or str(calendar_id) == str(employee.custom_stel_calendar_id or ""):
            continue
        frappe.db.set_value(
            "Employee", employee.name, "custom_stel_calendar_id", str(calendar_id), update_modified=False
        )
        mapped += 1
    frappe.db.commit()
    return mapped
