import hashlib
import json
import re
from datetime import timezone

from frappe.utils import get_datetime


def event_hash_from_doc(doc):
    return snapshot_hash({
        "subject": doc.get("subject"),
        "description": strip_html(doc.get("description")),
        "starts_on": local_datetime(doc.get("starts_on")),
        "ends_on": local_datetime(doc.get("ends_on") or doc.get("starts_on")),
        "all_day": bool(doc.get("all_day")),
        "status": normalize_erp_status(doc.get("status")),
        "location": doc.get("location"),
        "calendar_id": doc.get("custom_stel_calendar_id"),
    })


def event_hash_from_stel(item):
    item = single_item(item)
    return snapshot_hash({
        "subject": first(item, "subject", "description"),
        "description": first(item, "description"),
        "starts_on": stel_datetime(first(item, "start-date", "startDate", "date")),
        "ends_on": stel_datetime(first(item, "end-date", "endDate", "start-date", "startDate", "date")),
        "all_day": first(item, "all-day", "allDay") is True,
        "status": stel_status(first(item, "event-state", "eventState", "state")),
        "location": first(item, "location"),
        "calendar_id": first(item, "calendar-id", "calendarId"),
    })


def stel_modified_at(item):
    item = single_item(item)
    value = first(item, "utc-last-modification-date", "utcLastModificationDate", "modified", "updatedAt")
    if not value:
        return None
    parsed = get_datetime(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def snapshot_hash(values):
    normalized = {key: normalize(value) for key, value in values.items()}
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    return str(value).strip()


def local_datetime(value):
    if not value:
        return ""
    return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


def stel_datetime(value):
    if not value:
        return ""
    match = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?", str(value).strip())
    return f"{match.group(1)} {match.group(2)}:{match.group(3) or '00'}" if match else local_datetime(value)


def normalize_erp_status(value):
    return value if value in {"Open", "Closed", "Cancelled"} else "Open"


def stel_status(value):
    state = str(value or "PENDING").strip().upper()
    if state in {"COMPLETED", "CLOSED", "RESOLVED"}:
        return "Closed"
    if state in {"REFUSED", "CANCELLED", "CANCELED"}:
        return "Cancelled"
    return "Open"


def strip_html(value):
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def first(item, *keys):
    item = single_item(item)
    for key in keys:
        if item.get(key) is not None:
            return item.get(key)
    return None


def single_item(item):
    if isinstance(item, list):
        return item[0] if item and isinstance(item[0], dict) else {}
    return item if isinstance(item, dict) else {}
