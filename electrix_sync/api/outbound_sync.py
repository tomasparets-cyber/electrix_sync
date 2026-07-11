from datetime import timedelta

import frappe
from frappe.utils import get_datetime

from electrix_sync.api.planning import erp_event_state, extract_stel_id, stel_datetime
from electrix_sync.api.stel import StelClient


def enqueue_task(doc, method=None):
    enqueue_document("Task", doc)


def enqueue_event(doc, method=None):
    enqueue_document("Event", doc)


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


def push_task(doc):
    payload = {
        "description": (strip_html(doc.description) or doc.subject or doc.name)[:2048],
        "priority": task_priority(doc.priority),
    }
    for fieldname, key in (
        ("custom_stel_state_id", "incident-state-id"),
        ("custom_stel_type_id", "incident-type-id"),
        ("custom_stel_assignee_id", "assignee-id"),
        ("custom_stel_address_id", "address-id"),
    ):
        value = doc.get(fieldname)
        if value not in (None, ""):
            payload[key] = int(value)

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


def strip_html(value):
    return frappe.utils.strip_html(value or "").strip()
