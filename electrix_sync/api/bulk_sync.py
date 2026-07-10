import hashlib
import json
import traceback
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import get_datetime, now

from electrix_sync.api.stel import StelClient


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "config" / "stel_bulk_endpoints.json"


def get_manifest():
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@frappe.whitelist()
def start_bulk_snapshot():
    frappe.only_for("System Manager")
    active = frappe.db.exists(
        "STEL Bulk Sync Run", {"status": ["in", ["Queued", "Running"]]}
    )
    if active:
        frappe.throw(_("A STEL bulk synchronization is already running: {0}").format(active))

    manifest = get_manifest()
    run = frappe.get_doc(
        {
            "doctype": "STEL Bulk Sync Run",
            "status": "Queued",
            "resources_total": len(manifest),
            "resource_index": 0,
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
    job = enqueue_resource(run.name)
    if job:
        frappe.db.set_value("STEL Bulk Sync Run", run.name, "job_id", job.id, update_modified=False)
    return {"run": run.name, "resources": len(manifest), "job_id": getattr(job, "id", None)}


@frappe.whitelist()
def get_bulk_status(run_name=None):
    frappe.only_for("System Manager")
    if not run_name:
        run_name = frappe.db.get_value("STEL Bulk Sync Run", {}, "name", order_by="creation desc")
    if not run_name:
        return None
    return frappe.db.get_value(
        "STEL Bulk Sync Run",
        run_name,
        [
            "name",
            "status",
            "resources_total",
            "resources_completed",
            "current_resource",
            "records_read",
            "records_created",
            "records_updated",
            "records_unchanged",
            "error_count",
            "started_at",
            "finished_at",
        ],
        as_dict=True,
    )


def enqueue_resource(run_name):
    return frappe.enqueue(
        "electrix_sync.api.bulk_sync.process_next_resource",
        queue="long",
        timeout=1500,
        run_name=run_name,
        enqueue_after_commit=False,
    )


def process_next_resource(run_name):
    run = frappe.get_doc("STEL Bulk Sync Run", run_name)
    manifest = get_manifest()
    if run.resource_index >= len(manifest):
        finish_run(run)
        return

    if run.status == "Queued":
        run.status = "Running"
        run.started_at = now()

    resource = manifest[run.resource_index]
    run.current_resource = resource["key"]
    run.save(ignore_permissions=True)
    frappe.db.commit()

    try:
        items = StelClient().get_collection(resource["endpoint"])
        counters = ingest_resource(run.name, resource, items)
        run.reload()
        run.records_read += counters["read"]
        run.records_created += counters["created"]
        run.records_updated += counters["updated"]
        run.records_unchanged += counters["unchanged"]
    except Exception:
        run.reload()
        run.error_count += 1
        append_error(run, resource["key"], traceback.format_exc())

    run.resource_index += 1
    run.resources_completed = run.resource_index
    run.current_resource = None
    run.save(ignore_permissions=True)
    frappe.db.commit()

    if run.resource_index >= len(manifest):
        finish_run(run)
    else:
        enqueue_resource(run.name)


def ingest_resource(run_name, resource, items):
    counters = {"read": 0, "created": 0, "updated": 0, "unchanged": 0}
    for item in items or []:
        counters["read"] += 1
        result = upsert_raw_record(run_name, resource, item)
        counters[result] += 1
        if counters["read"] % 100 == 0:
            frappe.db.commit()
            publish_progress(run_name, resource["key"], counters["read"])
    frappe.db.commit()
    publish_progress(run_name, resource["key"], counters["read"])
    return counters


def upsert_raw_record(run_name, resource, item):
    payload = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    remote_id = get_remote_id(item) or payload_hash[:24]
    record_key = f"{resource['key']}::{remote_id}"[:140]
    existing = frappe.db.get_value(
        "STEL Raw Record", {"record_key": record_key}, ["name", "payload_hash"], as_dict=True
    )
    values = {
        "resource_type": resource["key"],
        "endpoint": resource["endpoint"],
        "remote_id": str(remote_id),
        "payload": payload,
        "payload_hash": payload_hash,
        "source_modified": get_source_modified(item),
        "fetched_at": now(),
        "sync_run": run_name,
        "is_deleted": 1 if item.get("deleted") is True else 0,
    }
    if existing:
        if existing.payload_hash == payload_hash:
            frappe.db.set_value(
                "STEL Raw Record",
                existing.name,
                {"fetched_at": values["fetched_at"], "sync_run": run_name},
                update_modified=False,
            )
            return "unchanged"
        frappe.db.set_value("STEL Raw Record", existing.name, values, update_modified=False)
        return "updated"

    frappe.get_doc(
        {"doctype": "STEL Raw Record", "record_key": record_key, **values}
    ).insert(ignore_permissions=True)
    return "created"


def get_remote_id(item):
    if not isinstance(item, dict):
        return None
    for key in ("id", "ID", "uuid", "code", "reference", "full-reference", "external-id"):
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def get_source_modified(item):
    if not isinstance(item, dict):
        return None
    for key in ("utc-last-modification-date", "utcLastModificationDate", "modified", "updatedAt"):
        value = item.get(key)
        if value:
            try:
                return get_datetime(value)
            except Exception:
                return None
    return None


def append_error(run, resource_key, details):
    entry = f"[{now()}] {resource_key}\n{details[-6000:]}"
    run.error_log = "\n\n".join(filter(None, [run.error_log, entry]))[-30000:]


def publish_progress(run_name, resource, records):
    frappe.publish_realtime(
        "stel_bulk_progress",
        {"run": run_name, "resource": resource, "records": records},
        after_commit=True,
    )


def finish_run(run):
    run.reload()
    run.status = "Completed with Errors" if run.error_count else "Completed"
    run.finished_at = now()
    run.current_resource = None
    run.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.publish_realtime(
        "stel_bulk_complete",
        {"run": run.name, "status": run.status, "records": run.records_read},
        after_commit=True,
    )
