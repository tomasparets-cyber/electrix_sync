from datetime import timedelta
import json

import frappe
from frappe.utils import get_datetime

from electrix_sync.api.master_data import get_staged
from electrix_sync.api.event_sync_state import event_hash_from_doc, event_hash_from_stel, stel_modified_at
from electrix_sync.api.planning import erp_event_state, extract_stel_id, get_catalog_id, stel_datetime
from electrix_sync.api.stel import StelClient


def enqueue_task(doc, method=None):
    enqueue_document("Task", doc)


def enqueue_event(doc, method=None):
    if not doc.get("custom_stel_id") and not doc.get("custom_stel_calendar_id"):
        return
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
        delete_remote_event(stel_id)
    except Exception:
        frappe.get_doc({
            "doctype": "Electrix Sync Log",
            "sync_type": "Event",
            "status": "Error",
            "stel_id": str(stel_id),
            "erpnext_doctype": "Event",
            "erpnext_document": doc.name,
            "message": "Pending STEL event deletion",
            "error": frappe.get_traceback(),
            "payload": json.dumps({"operation": "delete", "stel_id": str(stel_id)}),
        }).insert(ignore_permissions=True)
        frappe.log_error(frappe.get_traceback(), f"Could not delete STEL Event {stel_id}")


def normalize_event(doc, method=None):
    doc.status = doc.status if doc.status in {"Open", "Closed", "Cancelled"} else "Open"
    doc.custom_planning_status = "Completed" if doc.status == "Closed" else (
        "Planned" if doc.get("custom_assigned_employee") and doc.starts_on else "Unplanned"
    )


def enqueue_document(doctype, doc):
    if getattr(frappe.flags, "in_stel_sync", False) or getattr(doc.flags, "skip_stel_outbound", False):
        return
    if doc.meta.has_field("custom_stel_sync_status"):
        frappe.db.set_value(doctype, doc.name, "custom_stel_sync_status", "Pending", update_modified=False)
    frappe.enqueue(
        "electrix_sync.api.outbound_sync.push_document",
        queue="short",
        enqueue_after_commit=True,
        doctype=doctype,
        name=doc.name,
    )


def push_document(doctype, name, force=False):
    doc = frappe.get_doc(doctype, name)
    try:
        if doctype == "Task":
            push_task(doc)
        elif doctype == "Event":
            push_event(doc, force=force)
    except Exception:
        if doc.meta.has_field("custom_stel_sync_status"):
            values = {"custom_stel_sync_status": "Error"}
            if doc.meta.has_field("custom_stel_last_error"):
                values["custom_stel_last_error"] = str(frappe.get_traceback())[-2000:]
            frappe.db.set_value(doctype, name, values, update_modified=False)
        frappe.log_error(frappe.get_traceback(), f"ERPNext → STEL {doctype} {name}")
        frappe.db.commit()
        raise


@frappe.whitelist()
def sync_event_now(event_name):
    """Push an Event synchronously so a subsequent refresh cannot restore stale STEL data."""
    from electrix_sync.api.planning import check_planning_access
    check_planning_access()
    doc = frappe.get_doc("Event", event_name)
    if not doc.get("custom_stel_id") and not doc.get("custom_stel_calendar_id"):
        return {"synced": False, "reason": "not_linked"}
    push_document("Event", doc.name)
    status = frappe.db.get_value("Event", doc.name, "custom_stel_sync_status")
    if status == "Conflict":
        frappe.throw("ERPNext and STEL both changed this event. Resolve the conflict from the Event form.")
    return {
        "synced": True,
        "status": status,
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


def push_event(doc, force=False):
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
    remote = None
    if stel_id:
        remote = client.get_event(stel_id)
        baseline = doc.get("custom_stel_payload_hash")
        local_hash = event_hash_from_doc(doc)
        remote_hash = event_hash_from_stel(remote)
        if not force and baseline and remote_hash != baseline and local_hash != baseline:
            mark_event_conflict(doc, remote, "ERPNext and STEL changed since the last synchronization")
            return
        if not force and baseline and remote_hash != baseline and local_hash == baseline:
            from electrix_sync.api.sync import sync_event
            sync_event(remote, force=True)
            return
    response = client.update_event(stel_id, payload) if stel_id else client.create_event(payload)
    if not stel_id:
        stel_id = extract_stel_id(response)
        if not stel_id:
            frappe.throw("STEL created the event but did not return its ID")
        frappe.db.set_value("Event", doc.name, "custom_stel_id", str(stel_id), update_modified=False)
    synced_hash = event_hash_from_doc(doc)
    source = response if isinstance(response, dict) and response else remote or {}
    mark_synced("Event", doc.name, synced_hash, stel_modified_at(source))


def mark_synced(doctype, name, payload_hash=None, modified_at=None):
    values = {"custom_stel_sync_status": "Synced", "custom_stel_last_sync": frappe.utils.now()}
    if payload_hash:
        values["custom_stel_payload_hash"] = payload_hash
    if modified_at:
        values["custom_stel_modified_at"] = modified_at
    if frappe.get_meta(doctype).has_field("custom_stel_last_error"):
        values.update({"custom_stel_last_error": None, "custom_stel_conflict_payload": None})
    frappe.db.set_value(
        doctype,
        name,
        values,
        update_modified=False,
    )
    frappe.db.commit()


def mark_event_conflict(doc, remote, message):
    frappe.db.set_value(
        "Event",
        doc.name,
        {
            "custom_stel_sync_status": "Conflict",
            "custom_stel_last_error": message,
            "custom_stel_conflict_payload": json.dumps(remote, ensure_ascii=False, indent=2, default=str),
        },
        update_modified=False,
    )
    from electrix_sync.api.sync import log_sync
    log_sync("Event", "Conflict", doc.get("custom_stel_id"), "Event", doc.name, message, payload=remote)
    frappe.db.commit()


@frappe.whitelist()
def resolve_event_conflict(event_name, resolution):
    from electrix_sync.api.planning import check_planning_access
    check_planning_access()
    doc = frappe.get_doc("Event", event_name)
    if resolution == "erpnext":
        push_event(doc, force=True)
    elif resolution == "stel":
        from electrix_sync.api.sync import sync_event
        sync_event(StelClient().get_event(doc.custom_stel_id), force=True)
        frappe.db.commit()
    else:
        frappe.throw("Unknown conflict resolution")
    return {"name": doc.name, "resolution": resolution}


def retry_failed_events():
    names = frappe.get_all(
        "Event", filters={"custom_stel_sync_status": ["in", ["Pending", "Error"]]},
        pluck="name", limit_page_length=100,
    )
    results = {"synced": 0, "error": 0}
    for name in names:
        try:
            push_document("Event", name)
            results["synced"] += 1
        except Exception:
            results["error"] += 1
    deletion_logs = frappe.get_all(
        "Electrix Sync Log",
        filters={"sync_type": "Event", "status": "Error", "message": "Pending STEL event deletion"},
        pluck="name", limit_page_length=100,
    )
    results["deleted"] = 0
    for log_name in deletion_logs:
        log = frappe.get_doc("Electrix Sync Log", log_name)
        try:
            payload = json.loads(log.payload or "{}")
            delete_remote_event(payload.get("stel_id") or log.stel_id)
            log.status = "Success"
            log.message = "STEL event deletion completed"
            log.error = None
            log.save(ignore_permissions=True)
            frappe.db.commit()
            results["deleted"] += 1
        except Exception:
            log.error = frappe.get_traceback()
            log.save(ignore_permissions=True)
            frappe.db.commit()
    return results


def delete_remote_event(stel_id):
    try:
        return StelClient().delete_event(stel_id)
    except Exception as error:
        if getattr(getattr(error, "response", None), "status_code", None) == 404:
            return None
        raise


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
    customer = project.customer if project and project.get("customer") else None
    if project and project.get("customer"):
        account_id = frappe.db.get_value("Customer", project.customer, "custom_stel_id")
        if account_id:
            values["account-id"] = int(account_id)
    if project and project.get("custom_service_location") and customer:
        from electrix_sync.api.location_sync import ensure_stel_location_link
        link = ensure_stel_location_link(project.custom_service_location, customer)
        if link and link.stel_address_id:
            values["address-id"] = int(link.stel_address_id)
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
