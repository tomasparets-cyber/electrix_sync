from datetime import timedelta

import frappe
from frappe.utils import get_datetime

from electrix_sync.api.master_data import get_staged
from electrix_sync.api.planning import erp_event_state, extract_stel_id, get_catalog_id, stel_datetime
from electrix_sync.api.stel import StelClient


def enqueue_task(doc, method=None):
    enqueue_document("Task", doc)


def enqueue_event(doc, method=None):
    enqueue_document("Event", doc)


def delete_event(doc, method=None):
    """Delete the STEL copy without preventing the ERPNext deletion.

    An unavailable or already deleted remote event must not leave an Event
    permanently undeletable in ERPNext.
    """
    if getattr(frappe.flags, "in_stel_sync", False) or getattr(doc.flags, "skip_stel_outbound", False):
        return
    stel_id = doc.get("custom_stel_id")
    if not stel_id:
        return
    try:
        StelClient().delete_event(stel_id)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Could not delete STEL Event {stel_id}")


def normalize_event(doc, method=None):
    doc.status = doc.status if doc.status in {"Open", "Closed", "Cancelled"} else "Open"
    doc.custom_planning_status = "Completed" if doc.status == "Closed" else (
        "Planned" if doc.get("custom_assigned_employee") and doc.starts_on else "Unplanned"
    )


def enqueue_document(doctype, doc):
    if getattr(frappe.flags, "in_stel_sync", False) or getattr(doc.flags, "skip_stel_outbound", False):
        return
    if doc.get("custom_stel_sync_status") == "Error":
        return
    frappe.enqueue(
        "electrix_sync.api.outbound_sync.push_document",
        queue="short",
        enqueue_after_commit=True,
        doctype=doctype,
        name=doc.name,
    )


def push_document(doctype, name):
    doc = frappe.get_doc(doctype, name)
    try:
        if doctype == "Task":
            push_task(doc)
        elif doctype == "Event":
            push_event(doc)
    except Exception:
        if doc.meta.has_field("custom_stel_sync_status"):
            frappe.db.set_value(doctype, name, "custom_stel_sync_status", "Error", update_modified=False)
        frappe.log_error(frappe.get_traceback(), f"ERPNext → STEL {doctype} {name}")
        frappe.db.commit()
        raise


@frappe.whitelist()
def sync_event_now(event_name):
    """Push an Event synchronously so a subsequent refresh cannot restore stale STEL data."""
    doc = frappe.get_doc("Event", event_name)
    doc.check_permission("write")
    if not doc.get("custom_stel_id") and not doc.get("custom_stel_calendar_id"):
        return {"synced": False, "reason": "not_linked"}
    push_document("Event", doc.name)
    return {
        "synced": True,
        "stel_id": frappe.db.get_value("Event", doc.name, "custom_stel_id"),
    }


def push_task(doc):
    payload = {
        "description": (strip_html(doc.description) or doc.subject or doc.name)[:2048],
        "priority": task_priority(doc.priority),
    }
    state_id = task_state_id(doc.status)
    if state_id:
        payload["incident-state-id"] = int(state_id)
    type_id = catalog_id("incident_types", doc.get("type"))
    if type_id:
        payload["incident-type-id"] = int(type_id)
    payload.update(task_relations(doc))
    if doc.meta.has_field("expected_time") and doc.get("expected_time") is not None:
        payload["length"] = max(float(doc.expected_time or 0) * 60, 0)

    client = StelClient()
    stel_id = doc.get("custom_stel_id")
    response = client.update_incident(stel_id, payload) if stel_id else client.create_incident(payload)
    if not stel_id:
        stel_id = extract_stel_id(response)
        if not stel_id:
            frappe.throw("STEL created the incident but did not return its ID")
        frappe.db.set_value("Task", doc.name, "custom_stel_id", str(stel_id), update_modified=False)
    mark_synced("Task", doc.name)


def push_event(doc):
    if not doc.starts_on:
        return
    starts_on = get_datetime(doc.starts_on)
    ends_on = get_datetime(doc.ends_on or doc.starts_on)
    if ends_on <= starts_on:
        ends_on = starts_on + timedelta(hours=1)
    payload = {
        "subject": (doc.subject or doc.name)[:128],
        "description": (strip_html(doc.description) or "")[:5000],
        "start-date": stel_datetime(starts_on),
        "end-date": stel_datetime(ends_on),
        "all-day": bool(doc.all_day),
        "event-state": erp_event_state(doc),
    }
    if doc.meta.has_field("location") and doc.get("location"):
        payload["location"] = str(doc.location)[:128]
    account_id = event_account_id(doc)
    if account_id:
        payload["account-id"] = int(account_id)
    event_type_id = get_catalog_id("event_types", doc.get("event_category"))
    if event_type_id:
        payload["event-type-id"] = int(event_type_id)
    calendar_id = doc.get("custom_stel_calendar_id")
    if calendar_id and not doc.get("custom_stel_id"):
        payload["calendar-id"] = int(calendar_id)

    client = StelClient()
    stel_id = doc.get("custom_stel_id")
    response = client.update_event(stel_id, payload) if stel_id else client.create_event(payload)
    if not stel_id:
        stel_id = extract_stel_id(response)
        if not stel_id:
            frappe.throw("STEL created the event but did not return its ID")
        frappe.db.set_value("Event", doc.name, "custom_stel_id", str(stel_id), update_modified=False)
    mark_synced("Event", doc.name)


def mark_synced(doctype, name):
    frappe.db.set_value(
        doctype,
        name,
        {"custom_stel_sync_status": "Synced", "custom_stel_last_sync": frappe.utils.now()},
        update_modified=False,
    )
    frappe.db.commit()


def task_priority(priority):
    return {
        "Low": "LOW",
        "Medium": "NORMAL",
        "High": "HIGH",
        "Urgent": "VERYHIGH",
    }.get(priority, "NORMAL")


def task_state_id(status):
    preferred = {
        "Completed": ("resuelta", "resolved", "completed", "cerrada", "closed"),
        "Cancelled": ("rechazada", "refused", "cancelled", "cancelada"),
        "Working": ("atendida", "working", "in progress", "en curso"),
        "Pending Review": ("atendida", "pending review", "en revisión"),
        "Overdue": ("atendida", "overdue", "vencida"),
        "Open": ("abrir/abierto", "abierta", "abierto", "open"),
    }.get(status, ("abrir/abierto", "abierta", "abierto", "open"))
    return catalog_id("incident_states", *preferred)


def catalog_id(resource_type, *names):
    candidates = {str(name or "").strip().casefold() for name in names if name}
    if not candidates:
        return None
    for row in get_staged(resource_type):
        if str(row["data"].get("name") or "").strip().casefold() in candidates:
            return row["remote_id"]
    return None


def task_relations(doc):
    values = {}
    project = frappe.get_doc("Project", doc.project) if doc.get("project") and frappe.db.exists("Project", doc.project) else None
    if project and project.get("customer"):
        account_id = frappe.db.get_value("Customer", project.customer, "custom_stel_id")
        if account_id:
            values["account-id"] = int(account_id)
    if project and project.get("custom_service_location"):
        filters = {"parent": project.custom_service_location, "sync_enabled": 1}
        address_id = frappe.db.get_value("Lugar STEL Link", filters, "stel_address_id") or frappe.db.get_value(
            "Lugar STEL Link", {"parent": project.custom_service_location}, "stel_address_id"
        )
        if address_id:
            values["address-id"] = int(address_id)
    assigned_users = frappe.get_all(
        "ToDo", filters={"reference_type": "Task", "reference_name": doc.name, "status": "Open"},
        pluck="allocated_to", limit_page_length=1,
    )
    if assigned_users:
        assignee_id = frappe.db.get_value("Employee", {"user_id": assigned_users[0]}, "custom_stel_id")
        if assignee_id:
            values["assignee-id"] = int(assignee_id)
    return values


def event_account_id(doc):
    if doc.get("reference_doctype") == "Customer" and doc.get("reference_docname"):
        return frappe.db.get_value("Customer", doc.reference_docname, "custom_stel_id")
    return None


def strip_html(value):
    return frappe.utils.strip_html(value or "").strip()
