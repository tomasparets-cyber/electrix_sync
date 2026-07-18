import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now

from electrix_sync.api.stel import StelClient


def enqueue_location(doc, method=None):
    """Synchronize ERPNext-owned locations without echoing inbound STEL writes."""
    if getattr(frappe.flags, "in_stel_sync", False) or getattr(doc.flags, "skip_stel_outbound", False):
        return
    if doc.get("sync_policy") != "Bidireccional" or not doc.get("owner_customer"):
        return
    frappe.enqueue(
        "electrix_sync.api.location_sync.push_location",
        queue="short",
        enqueue_after_commit=True,
        place_name=doc.name,
    )


def push_location(place_name):
    """Ensure the owner copy exists and update every existing STEL copy."""
    place = frappe.get_doc("Lugar", place_name)
    if place.sync_policy != "Bidireccional":
        return {"skipped": True, "reason": "policy"}
    owner_link = ensure_stel_location_link(place.name, place.owner_customer)
    updated = []
    client = StelClient()
    place.reload()
    payload = location_payload(place)
    for link in place.stel_links:
        if not link.stel_address_id:
            continue
        client.update_address(link.stel_address_id, payload)
        frappe.db.set_value("Lugar STEL Link", link.name, {
            "payload_hash": location_payload_hash(payload),
            "sync_enabled": 1,
            "sync_status": "Synced",
            "last_sync": now(),
        }, update_modified=False)
        updated.append(str(link.stel_address_id))
    frappe.db.commit()
    return {"owner_address_id": owner_link.stel_address_id, "updated": updated}


def ensure_stel_location_link(place_name, customer):
    """Return the STEL address representing one ERPNext Lugar for one customer.

    STEL owns addresses under accounts, while ERPNext owns one physical Lugar.
    This function materializes the required per-customer STEL copy lazily.
    """
    if not place_name or not customer:
        return None
    place = frappe.get_doc("Lugar", place_name)
    link = next((row for row in place.stel_links if row.customer == customer), None)
    if link and link.stel_address_id:
        return link

    stel_customer_id = frappe.db.get_value("Customer", customer, "custom_stel_id")
    if not stel_customer_id:
        frappe.throw(_("Customer {0} must be synchronized with STEL before using location {1}.").format(customer, place.location_name))

    client = StelClient()
    external_id = location_external_id(place.name, stel_customer_id)
    account_addresses = client.get_collection("/app/addresses", filters={"account-id": int(stel_customer_id)})
    remote = find_matching_address(place, account_addresses, external_id)
    remote = remote or client.create_address({
        **location_payload(place),
        "account-id": int(stel_customer_id),
        "external-id": external_id,
    })
    address_id = extract_id(remote)
    if not address_id:
        frappe.throw(_("STEL created the location address but did not return its ID."))

    if not link:
        link = place.append("stel_links", {})
    link.customer = customer
    link.stel_customer_id = str(stel_customer_id)
    link.stel_address_id = str(address_id)
    link.is_owner_link = 1 if customer == place.owner_customer else 0
    link.payload_hash = location_payload_hash(location_payload(place))
    link.sync_enabled = 1
    link.sync_status = "Synced"
    link.last_sync = now()
    place.flags.skip_stel_outbound = True
    place.save(ignore_permissions=True)
    # The STEL side effect already exists. Persist its ID before a later
    # document synchronization can fail, so retries never create duplicates.
    frappe.db.commit()
    return next(row for row in place.stel_links if row.customer == customer)


def location_payload(place):
    address = (place.address_line1 or "").strip()
    if not address:
        frappe.throw(_("Location {0} needs an address before it can be synchronized with STEL.").format(place.location_name))
    payload = {
        "name": str(place.location_name or place.name)[:128],
        "address-data": address[:256],
        "address-type": "OTHER",
        "postal-code": optional_text(place.postal_code, 10),
        "province": optional_text(place.province, 64),
        "city-town": optional_text(place.city, 64),
        "country-code": country_code(place.country),
        "latitude": place.latitude if place.latitude is not None else None,
        "longitude": place.longitude if place.longitude is not None else None,
        "extra-data": optional_text(place.address_line2, 128),
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def country_code(country):
    if not country:
        return None
    meta = frappe.get_meta("Country")
    for fieldname in ("code", "country_code"):
        if meta.has_field(fieldname):
            value = frappe.db.get_value("Country", country, fieldname)
            if value:
                return str(value).upper()[:3]
    return "ES" if str(country).casefold() in {"spain", "españa"} else None


def location_external_id(place_name, stel_customer_id):
    digest = hashlib.sha256(f"{place_name}|{stel_customer_id}".encode()).hexdigest()[:20]
    return f"ERP-LUGAR-{digest}"


def location_payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def erp_location_key(place):
    from electrix_sync.api.master_data import get_location_key

    return get_location_key({
        "address-data": place.get("address_line1"),
        "postal-code": place.get("postal_code"),
        "city-town": place.get("city"),
        "province": place.get("province"),
        "country-code": country_code(place.get("country")),
    })


def find_matching_address(place, addresses, external_id):
    """Prefer our stable external ID, then the normalized physical address."""
    from electrix_sync.api.master_data import get_location_key

    local_key = get_location_key({
        "address-data": place.address_line1,
        "postal-code": place.postal_code,
        "city-town": place.city,
        "province": place.province,
        "country-code": country_code(place.country),
    })
    for address in addresses or []:
        if str(address.get("external-id") or "") == external_id:
            return address
    if local_key:
        for address in addresses or []:
            if get_location_key(address) == local_key:
                return address
    return None


def optional_text(value, length):
    return str(value).strip()[:length] if value not in (None, "") else None


def extract_id(payload):
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        return None
    for key in ("id", "address-id", "addressId"):
        if payload.get(key) not in (None, ""):
            return payload[key]
    for key in ("data", "item", "result"):
        if isinstance(payload.get(key), dict):
            value = extract_id(payload[key])
            if value:
                return value
    path = payload.get("path")
    if path and str(path).rstrip("/").rsplit("/", 1)[-1].isdigit():
        return str(path).rstrip("/").rsplit("/", 1)[-1]
    return None
