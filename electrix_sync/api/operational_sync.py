import json
import traceback

import frappe

from electrix_sync.api.master_data import get_staged, log_import, run_customer_import
from electrix_sync.api.sync import get_catalog_names, sync_employee, sync_event, sync_incident


OPERATIONAL_RESOURCES = ("employees", "incidents", "events")


@frappe.whitelist()
def start_complete_import():
    """Import the current STEL snapshot without making another STEL request."""
    frappe.only_for("System Manager")
    job = frappe.enqueue(
        "electrix_sync.api.operational_sync.run_complete_import",
        queue="long",
        timeout=7200,
        enqueue_after_commit=True,
    )
    return {"job_id": getattr(job, "id", None)}


def run_complete_import():
    master_data = run_customer_import()
    operational = run_operational_import()
    result = {"master_data": master_data, "operational": operational}
    frappe.publish_realtime("stel_complete_import_complete", result, after_commit=True)
    return result


def run_operational_import():
    settings = frappe.get_single("Electrix Sync Settings")
    # Creating ERPNext login users is a separate security decision. Employees
    # are imported now, but no account is provisioned implicitly.
    settings.create_users = 0
    calendars = [row["data"] for row in get_staged("calendars")]
    state_names = get_catalog_names([row["data"] for row in get_staged("incident_states")])
    type_names = get_catalog_names([row["data"] for row in get_staged("incident_types")])
    event_type_names = import_event_types(get_staged("event_types"))
    summary = {resource: blank_counts() for resource in OPERATIONAL_RESOURCES}

    processors = {
        "employees": lambda data: sync_employee(data, settings, calendars),
        "incidents": lambda data: sync_incident(data, state_names, type_names),
        "events": lambda data: sync_event(data, event_type_names),
    }
    previous_flag = getattr(frappe.flags, "in_stel_sync", False)
    frappe.flags.in_stel_sync = True
    try:
        for resource in OPERATIONAL_RESOURCES:
            for row in get_staged(resource):
                try:
                    action = processors[resource](row["data"])
                    summary[resource][action if action in summary[resource] else "error"] += 1
                    frappe.db.commit()
                except Exception:
                    frappe.db.rollback()
                    summary[resource]["error"] += 1
                    log_import(
                        resource.title(),
                        "Error",
                        row.get("remote_id"),
                        message="STEL operational staging import failed",
                        error=traceback.format_exc(),
                        payload=row.get("data"),
                    )
                    frappe.db.commit()
    finally:
        frappe.flags.in_stel_sync = previous_flag

    log_import("Operational Import", "Success", None, message=json.dumps(summary, ensure_ascii=False))
    return summary


def blank_counts():
    return {"created": 0, "updated": 0, "skipped": 0, "unchanged": 0, "error": 0}


def import_event_types(rows):
    names = {}
    for row in rows:
        data = row["data"]
        stel_id = str(data.get("id") or row["remote_id"])
        event_type_name = str(data.get("name") or f"STEL {stel_id}").strip()
        names[stel_id] = event_type_name
        values = {
            "event_type_name": event_type_name,
            "color": data.get("color"),
            "disabled": 1 if data.get("deleted") is True else 0,
        }
        if frappe.db.exists("STEL Event Type", stel_id):
            frappe.db.set_value("STEL Event Type", stel_id, values, update_modified=False)
        else:
            frappe.get_doc({
                "doctype": "STEL Event Type",
                "stel_id": stel_id,
                **values,
            }).insert(ignore_permissions=True)
    frappe.db.commit()
    return names
