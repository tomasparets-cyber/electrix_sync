import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now

from electrix_sync.api.planning import extract_stel_id
from electrix_sync.api.stel import StelClient


ACCOUNT_CONFIG = {
    "Customer": {"endpoint": "/app/clients", "kind": "customer"},
    "Lead": {"endpoint": "/app/potentialClients", "kind": "potential"},
}


def enqueue_account(doc, method=None):
    if doc.doctype not in ACCOUNT_CONFIG or should_skip(doc):
        return
    set_sync_state(doc.doctype, doc.name, "Pending")
    frappe.enqueue(
        "electrix_sync.api.account_sync.push_account",
        queue="short",
        enqueue_after_commit=True,
        doctype=doc.doctype,
        name=doc.name,
    )


def should_skip(doc):
    return bool(
        getattr(frappe.flags, "in_stel_sync", False)
        or getattr(doc.flags, "skip_stel_outbound", False)
        or getattr(doc.flags, "from_stel_sync", False)
    )


def push_account(doctype, name):
    if doctype not in ACCOUNT_CONFIG:
        frappe.throw(_("Unsupported STEL account type {0}").format(doctype))
    doc = frappe.get_doc(doctype, name)
    payload = account_payload(doc)
    client = StelClient()
    stel_id = doc.get("custom_stel_id")
    try:
        if not stel_id:
            remote = find_existing_remote(client, doctype, doc)
            if remote:
                stel_id = extract_stel_id(remote)
            else:
                response = client.create_customer(payload) if doctype == "Customer" else client.create_potential_client(payload)
                stel_id = extract_stel_id(response)
            if not stel_id:
                frappe.throw(_("STEL created the account but did not return its ID"))
            frappe.db.set_value(doctype, name, "custom_stel_id", str(stel_id), update_modified=False)
        else:
            if doctype == "Customer":
                client.update_customer(stel_id, payload)
            else:
                client.update_potential_client(stel_id, payload)
        mark_synced(doctype, name, payload)
        if doctype == "Customer":
            transfer_lead_locations(doc)
        return {"doctype": doctype, "name": name, "stel_id": str(stel_id)}
    except Exception:
        set_sync_state(doctype, name, "Error")
        frappe.log_error(frappe.get_traceback(), f"ERPNext → STEL {doctype} {name}")
        frappe.db.commit()
        raise


def ensure_account_synced(doctype, name):
    if not doctype or not name:
        return None
    stel_id = frappe.db.get_value(doctype, name, "custom_stel_id")
    if stel_id:
        return str(stel_id)
    return push_account(doctype, name)["stel_id"]


def retry_failed_accounts(limit=50):
    """Retry accounts left Pending/Error by a transient STEL failure."""
    retried = []
    for doctype in ACCOUNT_CONFIG:
        if not frappe.get_meta(doctype).has_field("custom_stel_sync_status"):
            continue
        names = frappe.get_all(
            doctype,
            filters={"custom_stel_sync_status": ["in", ["Pending", "Error"]]},
            pluck="name",
            limit_page_length=int(limit),
        )
        for name in names:
            try:
                push_account(doctype, name)
                retried.append(f"{doctype}:{name}")
            except Exception:
                continue
    return {"retried": retried}


def account_payload(doc):
    legal_name = account_legal_name(doc)
    payload = {
        "legal-name": legal_name[:128],
        "name": account_display_name(doc)[:128],
        "tax-identification-number": first(doc, "tax_id"),
        "phone": first(doc, "mobile_no", "phone"),
        "email": first(doc, "email_id"),
        "website": first(doc, "website"),
        "comments": first(doc, "customer_details", "notes"),
        "external-id": account_external_id(doc),
    }
    address = primary_address(doc.doctype, doc.name)
    if address:
        from electrix_sync.api.location_sync import main_address_payload
        payload["main-address"] = main_address_payload(address)
    return {key: value for key, value in payload.items() if value not in (None, "", {})}


def account_legal_name(doc):
    value = first(doc, "custom_stel_legal_name", "company_name", "customer_name", "lead_name")
    return str(value or doc.name)


def account_display_name(doc):
    value = first(doc, "customer_name", "lead_name", "company_name")
    return str(value or doc.name)


def account_external_id(doc):
    prefix = "CUSTOMER" if doc.doctype == "Customer" else "LEAD"
    digest = hashlib.sha256(f"{doc.doctype}|{doc.name}".encode()).hexdigest()[:24]
    return f"ERP-{prefix}-{digest}"


def find_existing_remote(client, doctype, doc):
    external_id = account_external_id(doc)
    rows = client.get_collection(ACCOUNT_CONFIG[doctype]["endpoint"], filters={"external-id": external_id})
    return next((row for row in rows if str(row.get("external-id") or "") == external_id), None)


def primary_address(doctype, name):
    links = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": doctype, "link_name": name, "parenttype": "Address"},
        pluck="parent",
        limit_page_length=0,
    )
    if not links:
        return None
    address_name = frappe.db.get_value("Address", {"name": ["in", links], "is_primary_address": 1}, "name")
    address_name = address_name or links[0]
    return frappe.get_doc("Address", address_name) if frappe.db.exists("Address", address_name) else None


def transfer_lead_locations(customer):
    if not customer.meta.has_field("lead_name") or not customer.get("lead_name"):
        return
    lead = customer.lead_name
    places = frappe.get_all(
        "Lugar",
        filters={"owner_doctype": "Lead", "owner_name": lead},
        pluck="name",
        limit_page_length=0,
    )
    for place_name in places:
        place = frappe.get_doc("Lugar", place_name)
        place.owner_doctype = "Customer"
        place.owner_name = customer.name
        place.owner_customer = customer.name
        place.save(ignore_permissions=True)
    address_names = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Lead", "link_name": lead, "parenttype": "Address"},
        pluck="parent",
        limit_page_length=0,
    )
    for address_name in address_names:
        address = frappe.get_doc("Address", address_name)
        if not any(row.link_doctype == "Customer" and row.link_name == customer.name for row in address.links):
            address.append("links", {"link_doctype": "Customer", "link_name": customer.name})
            address.flags.skip_stel_outbound = True
            address.save(ignore_permissions=True)
        if address.get("is_primary_address"):
            from electrix_sync.api.location_sync import push_primary_address
            push_primary_address(address.name, "Customer", customer.name)


def mark_synced(doctype, name, payload):
    values = {
        "custom_stel_sync_status": "Synced",
        "custom_stel_last_sync": now(),
        "custom_stel_payload_hash": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest(),
    }
    frappe.db.set_value(doctype, name, values, update_modified=False)
    frappe.db.commit()


def set_sync_state(doctype, name, state):
    if frappe.get_meta(doctype).has_field("custom_stel_sync_status"):
        frappe.db.set_value(doctype, name, "custom_stel_sync_status", state, update_modified=False)


def first(doc, *fieldnames):
    for fieldname in fieldnames:
        if doc.meta.has_field(fieldname) and doc.get(fieldname) not in (None, ""):
            return str(doc.get(fieldname))
    return None
