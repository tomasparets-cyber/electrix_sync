import json
import traceback
import hashlib

import frappe
from frappe import _
from frappe.utils import now

from electrix_sync.api.bulk_sync import get_source_modified


RESOURCE_DOCTYPE = {
    "clients": "Customer",
    "addresses": "Address",
    "contacts": "Contact",
}


@frappe.whitelist()
def start_customer_import():
    frappe.only_for("System Manager")
    validate_import_defaults()
    job = frappe.enqueue(
        "electrix_sync.api.master_data.run_customer_import",
        queue="long",
        timeout=3600,
        enqueue_after_commit=True,
    )
    return {"job_id": getattr(job, "id", None)}


def run_customer_import():
    settings = frappe.get_single("Electrix Sync Settings")
    staged = {key: get_staged(key) for key in RESOURCE_DOCTYPE}
    summary = {key: blank_import_counts() for key in ("clients", "addresses", "places", "contacts")}

    process_rows("clients", staged["clients"], lambda row: import_customer(row, settings), summary)
    process_rows(
        "addresses",
        [row for row in staged["addresses"] if address_destination(row["data"]) == "Address"],
        import_address,
        summary,
    )
    process_rows(
        "places",
        [row for row in staged["addresses"] if address_creates_place(row["data"])],
        import_place,
        summary,
    )
    process_rows("contacts", staged["contacts"], import_contact, summary)

    log_import("Master Data", "Success", None, message=json.dumps(summary, ensure_ascii=False))
    frappe.publish_realtime("stel_erp_import_complete", {"summary": summary}, after_commit=True)
    return summary


def process_rows(group, rows, importer, summary):
    for row in rows:
        try:
            action = importer(row)
            summary[group][action] += 1
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            summary[group]["error"] += 1
            log_import(
                {"clients": "Customer", "addresses": "Address", "places": "Lugar", "contacts": "Contact"}.get(group, "Master Data"),
                "Error",
                row.get("remote_id"),
                message="STEL staging import failed",
                error=traceback.format_exc(),
                payload=row.get("data"),
            )
            frappe.db.commit()


def import_customer(row, settings):
    data = row["data"]
    stel_id = row["remote_id"]
    existing = get_existing("Customer", stel_id)
    if existing and existing.custom_stel_payload_hash == row["payload_hash"]:
        return "unchanged"
    tax_id = clean(data.get("identification-number"))
    if not existing and tax_id:
        tax_match = frappe.db.get_value("Customer", {"tax_id": tax_id}, "name")
        if tax_match:
            log_import("Customer", "Skipped", stel_id, "Customer", tax_match, "NIF/CIF conflict", payload=data)
            return "skipped"

    doc = frappe.get_doc("Customer", existing.name) if existing else frappe.new_doc("Customer")
    values = {
        "customer_name": customer_name(data),
        "customer_type": "Company",
        "customer_group": stel_customer_group(data) or get_customer_group(settings, doc),
        "territory": get_territory(settings, doc),
        "alias": available_customer_alias(clean(data.get("legal-name")), existing.name if existing else None),
        "tax_id": tax_id,
        "email_id": clean(data.get("email")),
        "mobile_no": clean(data.get("phone")),
        "website": clean(data.get("website")),
        "customer_details": clean(data.get("comments")),
        "default_currency": valid_currency(data.get("currency-code")),
        "disabled": 1 if data.get("deleted") is True else 0,
        "account_manager": employee_user_for_stel_id(data.get("agent-id") or data.get("agentId")),
        "custom_stel_id": stel_id,
        "custom_stel_reference": clean(data.get("reference")),
        "custom_stel_full_reference": clean(data.get("full-reference")),
        "custom_stel_legal_name": clean(data.get("legal-name")),
        "custom_stel_phone_2": clean(data.get("phone2")),
        "custom_stel_external_id": clean(data.get("external-id")),
        "custom_stel_modified_at": get_source_modified(data),
        "custom_stel_payload_hash": row["payload_hash"],
    }
    update_existing_fields(doc, values)
    doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
    return "updated" if existing else "created"


def import_address(row):
    data = row["data"]
    customer = customer_for_account(data.get("account-id"))
    if not customer:
        return "skipped"
    existing = get_existing("Address", row["remote_id"])
    if existing and existing.custom_stel_payload_hash == row["payload_hash"]:
        return "unchanged"
    doc = frappe.get_doc("Address", existing.name) if existing else frappe.new_doc("Address")
    values = {
        "address_title": clean(data.get("name")) or customer,
        "address_type": "Billing",
        "address_line1": clean(data.get("address-data")) or clean(data.get("formatted-address")) or _("Sin dirección"),
        "address_line2": clean(data.get("extra-data")),
        "city": clean(data.get("city-town")) or _("Sin ciudad"),
        "state": clean(data.get("province")),
        "pincode": clean(data.get("postal-code")),
        "country": resolve_country(data.get("country-code")),
        "is_primary_address": 1 if (data.get("address-type") or "").upper() == "DEFAULT" else 0,
        "is_shipping_address": 0,
        "disabled": 1 if data.get("deleted") is True else 0,
        "custom_stel_id": row["remote_id"],
        "custom_stel_latitude": data.get("latitude"),
        "custom_stel_longitude": data.get("longitude"),
        "custom_stel_external_id": clean(data.get("external-id")),
        "custom_stel_modified_at": get_source_modified(data),
        "custom_stel_payload_hash": row["payload_hash"],
    }
    update_existing_fields(doc, values)
    ensure_dynamic_link(doc, "Customer", customer)
    doc.flags.skip_stel_outbound = True
    doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
    return "updated" if existing else "created"


def import_contact(row):
    data = row["data"]
    customer = customer_for_account(data.get("account-id"))
    if not customer:
        return "skipped"
    existing = get_existing("Contact", row["remote_id"])
    if existing and existing.custom_stel_payload_hash == row["payload_hash"]:
        return "unchanged"
    doc = frappe.get_doc("Contact", existing.name) if existing else frappe.new_doc("Contact")
    update_existing_fields(doc, {
        "first_name": clean(data.get("name")) or f"STEL {row['remote_id']}",
        "designation": clean(data.get("position")),
        "company_name": frappe.db.get_value("Customer", customer, "customer_name"),
        "status": "Passive" if data.get("deleted") is True else "Open",
        "custom_stel_id": row["remote_id"],
        "custom_stel_fax": clean(data.get("fax")),
        "custom_stel_comments": clean(data.get("comments")),
        "custom_stel_modified_at": get_source_modified(data),
        "custom_stel_payload_hash": row["payload_hash"],
    })
    doc.set("email_ids", [])
    if clean(data.get("email")):
        doc.append("email_ids", {"email_id": clean(data.get("email")), "is_primary": 1})
    doc.set("phone_nos", [])
    if clean(data.get("phone")):
        doc.append("phone_nos", {"phone": clean(data.get("phone")), "is_primary_phone": 1})
    if clean(data.get("fax")) and clean(data.get("fax")) != clean(data.get("phone")):
        doc.append("phone_nos", {"phone": clean(data.get("fax"))})
    ensure_dynamic_link(doc, "Customer", customer)
    doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
    return "updated" if existing else "created"


def import_place(row):
    data = row["data"]
    existing_parent = frappe.db.get_value("Lugar STEL Link", {"stel_address_id": row["remote_id"]}, "parent")
    location_key = get_location_key(data)
    if not existing_parent and location_key:
        existing_parent = frappe.db.get_value("Lugar", {"location_key": location_key}, "name")
    doc = frappe.get_doc("Lugar", existing_parent) if existing_parent else frappe.new_doc("Lugar")
    customer = customer_for_account(data.get("account-id"))
    link = next((x for x in doc.stel_links if str(x.stel_address_id) == row["remote_id"]), None)
    if link and link.payload_hash == row["payload_hash"] and link.get("stel_address_type"):
        return "unchanged"
    if not doc.get("owner_customer") and customer:
        doc.owner_customer = customer
    is_owner_copy = bool(customer and customer == doc.get("owner_customer"))
    # Only the owner's STEL address is authoritative. Copies created below
    # other accounts merely add a link to the same physical ERPNext Lugar.
    if not existing_parent or is_owner_copy:
        update_existing_fields(doc, {
            "location_name": clean(data.get("name")) or clean(data.get("address-data")) or f"STEL {row['remote_id']}",
            "location_key": location_key,
            "status": "Inactivo" if data.get("deleted") is True else "Activo",
            "address_line1": clean(data.get("address-data")) or clean(data.get("formatted-address")),
            "address_line2": clean(data.get("extra-data")),
            "postal_code": clean(data.get("postal-code")),
            "city": clean(data.get("city-town")),
            "province": clean(data.get("province")),
            "country": resolve_country(data.get("country-code")),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        })
    if not link:
        link = doc.append("stel_links", {})
    link.customer = customer
    link.stel_customer_id = str(data.get("account-id")) if data.get("account-id") is not None else None
    link.stel_address_id = row["remote_id"]
    link.stel_address_type = (data.get("address-type") or "OTHER").upper()
    link.is_owner_link = 1 if is_owner_copy else 0
    link.payload_hash = row["payload_hash"]
    link.sync_enabled = 0
    link.sync_status = "Linked" if customer else "Local"
    link.last_sync = now()
    doc.flags.skip_stel_outbound = True
    doc.save(ignore_permissions=True) if existing_parent else doc.insert(ignore_permissions=True)
    return "updated" if existing_parent else "created"


def validate_import_defaults():
    settings = frappe.get_single("Electrix Sync Settings")
    if not get_customer_group(settings, None):
        frappe.throw(_("Configure a default Customer Group before importing."))
    if not get_territory(settings, None):
        frappe.throw(_("Configure a default Territory before importing."))


def get_customer_group(settings, doc):
    current = doc.get("customer_group") if doc else None
    return settings.default_customer_group or current or frappe.db.get_value("Customer Group", {"is_group": 0}, "name", order_by="lft asc")


def get_territory(settings, doc):
    current = doc.get("territory") if doc else None
    return settings.default_territory or current or frappe.db.get_value("Territory", {}, "name", order_by="lft asc")


def stel_customer_group(data):
    category = staged_name("account_categories", data.get("account-category-id") or data.get("accountCategoryId"))
    if not category:
        return None
    if not frappe.db.exists("Customer Group", category):
        root = frappe.db.get_value("Customer Group", {"is_group": 1}, "name", order_by="lft asc")
        frappe.get_doc({
            "doctype": "Customer Group", "customer_group_name": category,
            "parent_customer_group": root, "is_group": 0,
        }).insert(ignore_permissions=True)
    return category


def staged_name(resource_type, remote_id):
    if remote_id in (None, ""):
        return None
    row = frappe.db.get_value(
        "STEL Raw Record", {"resource_type": resource_type, "remote_id": str(remote_id)}, "payload"
    )
    if not row:
        return None
    try:
        return clean(json.loads(row).get("name"))
    except (TypeError, ValueError):
        return None


def employee_user_for_stel_id(stel_id):
    if stel_id in (None, "") or not frappe.db.has_column("Employee", "custom_stel_id"):
        return None
    return frappe.db.get_value("Employee", {"custom_stel_id": str(stel_id)}, "user_id")


def available_customer_alias(value, current_name=None):
    if not value:
        return None
    existing = frappe.db.get_value("Customer", {"alias": value}, "name")
    return value if not existing or existing == current_name else None


def valid_currency(code):
    code = clean(code)
    return code if code and frappe.db.exists("Currency", code) else None


def resolve_country(code):
    code = (clean(code) or "ES").upper()
    country = frappe.db.get_value("Country", {"code": code}, "name")
    if country:
        return country
    fallback = {"ES": "Spain", "GB": "United Kingdom", "US": "United States"}.get(code, code)
    return fallback if frappe.db.exists("Country", fallback) else "Spain"


def customer_for_account(account_id):
    return frappe.db.get_value("Customer", {"custom_stel_id": str(account_id)}, "name") if account_id is not None else None


def ensure_dynamic_link(doc, link_doctype, link_name):
    if not any(x.link_doctype == link_doctype and x.link_name == link_name for x in doc.get("links", [])):
        doc.append("links", {"link_doctype": link_doctype, "link_name": link_name})


def update_existing_fields(doc, values):
    meta = doc.meta
    for fieldname, value in values.items():
        if meta.has_field(fieldname):
            doc.set(fieldname, value)


def blank_import_counts():
    return {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "error": 0}


def log_import(sync_type, status, stel_id, erpnext_doctype=None, erpnext_document=None, message=None, error=None, payload=None):
    frappe.get_doc({
        "doctype": "Electrix Sync Log",
        "sync_type": sync_type,
        "status": status,
        "stel_id": stel_id,
        "erpnext_doctype": erpnext_doctype,
        "erpnext_document": erpnext_document,
        "message": message,
        "error": error,
        "payload": json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None,
    }).insert(ignore_permissions=True)


@frappe.whitelist()
def preview_customer_import():
    """Dry-run the STEL customer, address and contact conversion."""
    frappe.only_for("System Manager")
    staged = {key: get_staged(key) for key in RESOURCE_DOCTYPE}
    staged_client_ids = {str(row["data"].get("id")) for row in staged["clients"] if row["data"].get("id") is not None}
    result = {
        "dry_run": True,
        "clients": preview_clients(staged["clients"]),
        "addresses": preview_linked(
            [row for row in staged["addresses"] if address_destination(row["data"]) == "Address"],
            "Address",
            staged_client_ids,
        ),
        "places": preview_places(
            [row for row in staged["addresses"] if address_creates_place(row["data"])]
        ),
        "unclassified_addresses": len(
            [row for row in staged["addresses"] if address_destination(row["data"]) is None and not address_creates_place(row["data"])]
        ),
        "contacts": preview_linked(staged["contacts"], "Contact", staged_client_ids),
    }
    result["totals"] = sum_counts(result.values())
    return result


def get_staged(resource_type):
    rows = frappe.get_all(
        "STEL Raw Record",
        filters={"resource_type": resource_type},
        fields=["remote_id", "payload", "payload_hash"],
        order_by="remote_id asc",
        limit_page_length=0,
    )
    output = []
    for row in rows:
        try:
            data = json.loads(row.payload)
        except (TypeError, ValueError):
            data = {}
        output.append({"remote_id": str(row.remote_id), "payload_hash": row.payload_hash, "data": data})
    return output


def preview_clients(rows):
    counts = blank_counts()
    conflicts = []
    for row in rows:
        stel_id = row["remote_id"]
        existing = get_existing("Customer", stel_id)
        if existing:
            counts["unchanged" if existing.custom_stel_payload_hash == row["payload_hash"] else "update"] += 1
            continue
        tax_id = clean(row["data"].get("identification-number"))
        tax_match = frappe.db.get_value("Customer", {"tax_id": tax_id}, "name") if tax_id else None
        if tax_match:
            counts["conflict"] += 1
            conflicts.append({"stel_id": stel_id, "tax_id": tax_id, "erpnext": tax_match, "stel_name": customer_name(row["data"])})
        else:
            counts["create"] += 1
    counts["details"] = conflicts[:100]
    return counts


def preview_linked(rows, doctype, staged_client_ids):
    counts = blank_counts()
    missing = []
    for row in rows:
        existing = get_existing(doctype, row["remote_id"])
        if existing:
            counts["unchanged" if existing.custom_stel_payload_hash == row["payload_hash"] else "update"] += 1
            continue
        account_id = row["data"].get("account-id")
        linked = account_id is not None and (
            str(account_id) in staged_client_ids
            or customer_exists(str(account_id))
        )
        if linked:
            counts["create"] += 1
        else:
            counts["unlinked"] += 1
            missing.append({"stel_id": row["remote_id"], "account_id": account_id, "name": row["data"].get("name")})
    counts["details"] = missing[:100]
    return counts


def blank_counts():
    return {"create": 0, "update": 0, "unchanged": 0, "conflict": 0, "unlinked": 0}


def preview_places(rows):
    counts = blank_counts()
    seen_new = set()
    for row in rows:
        existing_parent = frappe.db.get_value(
            "Lugar STEL Link", {"stel_address_id": row["remote_id"]}, "parent"
        )
        location_key = get_location_key(row["data"])
        if not existing_parent and location_key:
            existing_parent = frappe.db.get_value("Lugar", {"location_key": location_key}, "name")
        if existing_parent:
            counts["update"] += 1
        elif location_key and location_key in seen_new:
            counts["update"] += 1
        else:
            counts["create"] += 1
            if location_key:
                seen_new.add(location_key)
    return counts


def address_destination(data):
    address_type = (data.get("address-type") or "").upper()
    if address_type in {"DEFAULT", "INVOICING"}:
        return "Address"
    if address_type in {"DELIVERY", "OTHER"}:
        return "Lugar"
    return None


def address_creates_place(data):
    """Operational locations include the customer's main physical address."""
    return (data.get("address-type") or "").upper() in {"DEFAULT", "DELIVERY", "OTHER"}


def get_existing(doctype, stel_id):
    if not frappe.db.has_column(doctype, "custom_stel_id"):
        return None
    fields = ["name"]
    if frappe.db.has_column(doctype, "custom_stel_payload_hash"):
        fields.append("custom_stel_payload_hash")
    existing = frappe.db.get_value(
        doctype, {"custom_stel_id": stel_id}, fields, as_dict=True
    )
    if existing and "custom_stel_payload_hash" not in existing:
        existing.custom_stel_payload_hash = None
    return existing


def customer_exists(stel_id):
    return bool(
        frappe.db.has_column("Customer", "custom_stel_id")
        and frappe.db.exists("Customer", {"custom_stel_id": stel_id})
    )


def sum_counts(groups):
    total = blank_counts()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for key in total:
            total[key] += int(group.get(key) or 0)
    return total


def customer_name(data):
    return clean(data.get("name")) or clean(data.get("legal-name")) or f"STEL {data.get('id')}"


def clean(value):
    return str(value).strip() if value not in (None, "") else None


def get_location_key(data):
    parts = [
        clean(data.get("address-data")) or clean(data.get("formatted-address")),
        clean(data.get("postal-code")),
        clean(data.get("city-town")),
        clean(data.get("province")),
        clean(data.get("country-code")),
    ]
    normalized = "|".join((part or "").casefold().replace(" ", "") for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized.strip("|") else None
