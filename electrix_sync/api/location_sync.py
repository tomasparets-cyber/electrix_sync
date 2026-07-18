import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now

from electrix_sync.api.stel import StelClient


def enqueue_primary_address(doc, method=None):
    """Push ERPNext's primary customer Address through STEL's client API."""
    if getattr(frappe.flags, "in_stel_sync", False) or getattr(doc.flags, "skip_stel_outbound", False):
        return
    if not doc.get("is_primary_address") or not doc.get("custom_stel_id"):
        return
    customer = primary_address_customer(doc)
    if not customer:
        return
    frappe.enqueue(
        "electrix_sync.api.location_sync.push_primary_address",
        queue="short",
        enqueue_after_commit=True,
        address_name=doc.name,
        customer=customer,
    )


def push_primary_address(address_name, customer):
    address = frappe.get_doc("Address", address_name)
    stel_customer_id = frappe.db.get_value("Customer", customer, "custom_stel_id")
    if not stel_customer_id:
        frappe.throw(_("Customer {0} must be synchronized before its primary address.").format(customer))
    try:
        payload = main_address_payload(address)
        response = StelClient().update_customer(stel_customer_id, {"main-address": payload})
        if address.meta.has_field("custom_stel_last_sync"):
            frappe.db.set_value("Address", address.name, {
                "custom_stel_last_sync": now(),
                "custom_stel_sync_status": "Synced",
            }, update_modified=False)
        mirror_primary_address_to_place(address)
        frappe.db.commit()
        return response
    except Exception:
        if address.meta.has_field("custom_stel_sync_status"):
            frappe.db.set_value("Address", address.name, "custom_stel_sync_status", "Error", update_modified=False)
            frappe.db.commit()
        raise


def primary_address_customer(address):
    for link in address.get("links", []):
        if link.link_doctype == "Customer" and link.link_name:
            return link.link_name
    return None


def main_address_payload(address):
    payload = {
        "address-data": optional_text(address.address_line1, 256),
        "postal-code": optional_text(address.pincode, 10),
        "province": optional_text(address.state, 64),
        "city-town": optional_text(address.city, 64),
        "country-code": country_code(address.country),
        "latitude": address.get("custom_stel_latitude"),
        "longitude": address.get("custom_stel_longitude"),
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def place_main_address_payload(place):
    payload = {
        "address-data": optional_text(place.address_line1, 256),
        "postal-code": optional_text(place.postal_code, 10),
        "province": optional_text(place.province, 64),
        "city-town": optional_text(place.city, 64),
        "country-code": country_code(place.country),
        "latitude": place.latitude,
        "longitude": place.longitude,
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def mirror_primary_address_to_place(address):
    if not frappe.db.exists("DocType", "Lugar STEL Link"):
        return
    place_name = frappe.db.get_value(
        "Lugar STEL Link", {"stel_address_id": str(address.custom_stel_id)}, "parent"
    )
    if not place_name:
        return
    place = frappe.get_doc("Lugar", place_name)
    place.address_line1 = address.address_line1
    place.address_line2 = address.address_line2
    place.postal_code = address.pincode
    place.city = address.city
    place.province = address.state
    place.country = address.country
    if address.meta.has_field("custom_stel_latitude"):
        place.latitude = address.custom_stel_latitude
    if address.meta.has_field("custom_stel_longitude"):
        place.longitude = address.custom_stel_longitude
    place.flags.skip_stel_outbound = True
    place.save(ignore_permissions=True)


def mirror_place_to_primary_address(place, stel_address_id):
    address_name = frappe.db.get_value("Address", {"custom_stel_id": str(stel_address_id)}, "name")
    if not address_name:
        return
    address = frappe.get_doc("Address", address_name)
    address.address_line1 = place.address_line1
    address.address_line2 = place.address_line2
    address.pincode = place.postal_code
    address.city = place.city
    address.state = place.province
    address.country = place.country
    if address.meta.has_field("custom_stel_latitude"):
        address.custom_stel_latitude = place.latitude
    if address.meta.has_field("custom_stel_longitude"):
        address.custom_stel_longitude = place.longitude
    address.flags.skip_stel_outbound = True
    address.save(ignore_permissions=True)


def enqueue_location(doc, method=None):
    """Synchronize ERPNext-owned locations without hiding STEL write errors."""
    if getattr(frappe.flags, "in_stel_sync", False) or getattr(doc.flags, "skip_stel_outbound", False):
        return
    if not doc.get("owner_customer"):
        return
    # Location edits are interactive and must not appear successful when the
    # background worker later rejects the STEL request. Run the small outbound
    # write now so Desk reports the real API error to the user immediately.
    push_location(doc.name)


def push_location(place_name):
    """Ensure the owner copy exists and update every existing STEL copy."""
    place = frappe.get_doc("Lugar", place_name)
    owner_link = ensure_stel_location_link(place.name, place.owner_customer)
    updated = []
    client = StelClient()
    place.reload()
    payload = location_payload(place)
    for link in place.stel_links:
        if not link.stel_address_id:
            continue
        try:
            if is_default_address_link(link, client):
                stel_customer_id = link.stel_customer_id or frappe.db.get_value("Customer", link.customer, "custom_stel_id")
                if stel_customer_id:
                    client.update_customer(stel_customer_id, {"main-address": place_main_address_payload(place)})
                    mirror_place_to_primary_address(place, link.stel_address_id)
                    frappe.db.set_value("Lugar STEL Link", link.name, {
                        "stel_address_type": "DEFAULT",
                        "payload_hash": location_payload_hash(payload),
                        "sync_enabled": 1,
                        "sync_status": "Synced",
                        "last_sync": now(),
                    }, update_modified=False)
                    updated.append(str(link.stel_address_id))
                continue
            client.update_address(link.stel_address_id, payload)
            frappe.db.set_value("Lugar STEL Link", link.name, {
                "payload_hash": location_payload_hash(payload),
                "sync_enabled": 1,
                "sync_status": "Synced",
                "last_sync": now(),
            }, update_modified=False)
            updated.append(str(link.stel_address_id))
        except Exception:
            frappe.db.set_value("Lugar STEL Link", link.name, "sync_status", "Error", update_modified=False)
            frappe.db.commit()
            raise
    frappe.db.commit()
    return {"owner_address_id": owner_link.stel_address_id, "updated": updated}


def is_default_address_link(link, client=None):
    if str(link.get("stel_address_type") or "").upper() == "DEFAULT":
        return True
    if not link.get("stel_address_id"):
        return False
    if frappe.db.exists("Address", {
        "custom_stel_id": str(link.stel_address_id),
        "is_primary_address": 1,
    }):
        return True
    # Some historical main addresses were imported before their STEL type was
    # stored locally. Ask STEL for the authoritative type instead of trying a
    # secondary-address PUT, which STEL rejects for DEFAULT addresses.
    if client:
        remote = client.get_address(link.stel_address_id)
        remote_type = str(remote.get("address-type") or "").upper() if isinstance(remote, dict) else ""
        if remote_type:
            frappe.db.set_value(
                "Lugar STEL Link", link.name, "stel_address_type", remote_type, update_modified=False
            )
        return remote_type == "DEFAULT"
    return False


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
    link.stel_address_type = str(remote.get("address-type") or "OTHER").upper() if isinstance(remote, dict) else "OTHER"
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
