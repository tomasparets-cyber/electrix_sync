import json
import re
import traceback

import frappe
from frappe.utils import now, validate_phone_number

from electrix_sync.api.stel import StelClient


@frappe.whitelist()
def sync_all():
    settings = frappe.get_single("Electrix Sync Settings")
    if not settings.enabled:
        return {"customers": {"skipped": "Sync disabled"}, "leads": {"skipped": "Sync disabled"}}

    result = {}
    if settings.sync_customers:
        result["customers"] = sync_customers()
    if settings.sync_leads:
        result["leads"] = sync_leads()

    return result


@frappe.whitelist()
def sync_customers():
    settings = frappe.get_single("Electrix Sync Settings")
    if not settings.enabled:
        return {"skipped": "Sync disabled"}

    stats = {"created": 0, "updated": 0, "error": 0, "skipped": 0}

    try:
        items = StelClient(settings).get_customers()
    except Exception:
        log_sync("Customer", "Error", message="Could not fetch STEL customers", error=traceback.format_exc())
        frappe.db.commit()
        return {"created": 0, "updated": 0, "error": 1, "skipped": 0}

    for item in items:
        status = sync_customer(item, settings)
        stats[status] += 1

    frappe.db.commit()
    return stats


@frappe.whitelist()
def sync_leads():
    settings = frappe.get_single("Electrix Sync Settings")
    if not settings.enabled:
        return {"skipped": "Sync disabled"}

    stats = {"created": 0, "updated": 0, "error": 0, "skipped": 0}

    try:
        items = StelClient(settings).get_leads()
    except Exception:
        log_sync("Lead", "Error", message="Could not fetch STEL potential clients", error=traceback.format_exc())
        frappe.db.commit()
        return {"created": 0, "updated": 0, "error": 1, "skipped": 0}

    for item in items:
        status = sync_lead(item, settings)
        stats[status] += 1

    frappe.db.commit()
    return stats


def sync_customer(item, settings):
    stel_id = get_stel_id(item)
    if not stel_id:
        log_sync("Customer", "Skipped", None, message="Missing STEL ID", payload=item)
        return "skipped"

    try:
        customer_name = get_first(
            item,
            "name",
            "legal-name",
            "nombre",
            "companyName",
            "company_name",
            "commercialName",
            "legalName",
        )
        if not customer_name:
            customer_name = f"STEL Customer {stel_id}"

        existing = frappe.db.get_value("Customer", {"custom_stel_id": stel_id}, "name")
        doc = frappe.get_doc("Customer", existing) if existing else frappe.new_doc("Customer")

        doc.customer_name = customer_name
        doc.customer_type = get_customer_type(item)
        doc.customer_group = settings.default_customer_group or doc.get("customer_group") or "All Customer Groups"
        doc.territory = settings.default_territory or doc.get("territory") or "All Territories"
        doc.custom_stel_id = stel_id
        doc.custom_stel_last_sync = now()
        doc.custom_stel_sync_status = "Synced"

        tax_id = get_first(
            item,
            "tax-identification-number",
            "identification-number",
            "taxId",
            "tax_id",
            "vat",
            "vatNumber",
            "nif",
            "cif",
        )
        if tax_id and hasattr(doc, "tax_id"):
            doc.tax_id = tax_id

        email = get_first(item, "email", "emailId", "email_id")
        if email and hasattr(doc, "email_id"):
            doc.email_id = email

        phone = get_phone(item, "phone", "phone2", "mobile", "mobileNo", "mobile_no", "telephone", "telefono")
        if phone and hasattr(doc, "mobile_no"):
            doc.mobile_no = phone

        if existing:
            doc.save(ignore_permissions=True)
            action = "updated"
        else:
            doc.insert(ignore_permissions=True)
            action = "created"

        log_sync("Customer", "Success", stel_id, "Customer", doc.name, f"Customer {action}", payload=item)
        return action
    except Exception:
        mark_error("Customer", stel_id)
        log_sync("Customer", "Error", stel_id, message="Customer sync failed", error=traceback.format_exc(), payload=item)
        return "error"


def sync_lead(item, settings):
    stel_id = get_stel_id(item)
    if not stel_id:
        log_sync("Lead", "Skipped", None, message="Missing STEL ID", payload=item)
        return "skipped"

    try:
        lead_name = get_first(
            item,
            "name",
            "legal-name",
            "nombre",
            "companyName",
            "company_name",
            "commercialName",
            "legalName",
        )
        if not lead_name:
            lead_name = f"STEL Lead {stel_id}"

        existing = frappe.db.get_value("Lead", {"custom_stel_id": stel_id}, "name")
        doc = frappe.get_doc("Lead", existing) if existing else frappe.new_doc("Lead")

        doc.lead_name = lead_name
        doc.company_name = (
            get_first(item, "legal-name", "companyName", "company_name", "commercialName", "legalName") or lead_name
        )
        doc.status = doc.get("status") or "Lead"
        doc.source = settings.default_lead_source or doc.get("source")
        doc.email_id = get_first(item, "email", "emailId", "email_id")
        doc.mobile_no = get_phone(item, "mobile", "mobileNo", "mobile_no", "phone", "phone2", "telephone", "telefono")
        doc.custom_stel_id = stel_id
        doc.custom_stel_last_sync = now()
        doc.custom_stel_sync_status = "Synced"

        if existing:
            doc.save(ignore_permissions=True)
            action = "updated"
        else:
            doc.insert(ignore_permissions=True)
            action = "created"

        log_sync("Lead", "Success", stel_id, "Lead", doc.name, f"Lead {action}", payload=item)
        return action
    except Exception:
        mark_error("Lead", stel_id)
        log_sync("Lead", "Error", stel_id, message="Lead sync failed", error=traceback.format_exc(), payload=item)
        return "error"


def get_stel_id(item):
    value = get_first(item, "id", "external-id", "stel_id", "uuid", "code", "codigo")
    return str(value) if value not in (None, "") else None


def get_customer_type(item):
    is_company = get_first(item, "isCompany", "is_company", "company", "empresa")
    if is_company is False:
        return "Individual"

    return "Company"


def get_first(item, *keys):
    if not isinstance(item, dict):
        return None

    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value

    return None


def get_phone(item, *keys):
    return clean_phone_number(get_first(item, *keys))


def clean_phone_number(value):
    if value in (None, ""):
        return None

    phone = str(value).strip().replace("\u00a0", " ")
    phone = "".join(character for character in phone if character.isprintable())
    phone = re.sub(r"[^\d+]", "", phone)

    if phone.startswith("00"):
        phone = f"+{phone[2:]}"
    elif phone.startswith("+"):
        digits = re.sub(r"\D", "", phone[1:])
        phone = f"+{digits}"
    else:
        phone = re.sub(r"\D", "", phone)

    if len(re.sub(r"\D", "", phone)) < 6:
        return None

    try:
        return phone if validate_phone_number(phone, throw=False) else None
    except Exception:
        return None


def mark_error(doctype, stel_id):
    if not stel_id:
        return

    name = frappe.db.get_value(doctype, {"custom_stel_id": stel_id}, "name")
    if name:
        frappe.db.set_value(doctype, name, "custom_stel_sync_status", "Error", update_modified=False)


def log_sync(
    sync_type,
    status,
    stel_id=None,
    erpnext_doctype=None,
    erpnext_document=None,
    message=None,
    error=None,
    payload=None,
):
    frappe.get_doc(
        {
            "doctype": "Electrix Sync Log",
            "sync_type": sync_type,
            "status": status,
            "stel_id": stel_id,
            "erpnext_doctype": erpnext_doctype,
            "erpnext_document": erpnext_document,
            "message": message,
            "error": error,
            "payload": json.dumps(payload, ensure_ascii=False, indent=2, default=str) if payload is not None else None,
        }
    ).insert(ignore_permissions=True)
