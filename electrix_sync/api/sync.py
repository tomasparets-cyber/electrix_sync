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
        return {
            "customers": {"skipped": "Sync disabled"},
            "leads": {"skipped": "Sync disabled"},
            "places": {"skipped": "Sync disabled"},
        }

    result = {}
    if settings.sync_customers:
        result["customers"] = sync_customers()
    if settings.sync_leads:
        result["leads"] = sync_leads()
    if getattr(settings, "sync_places", 0):
        result["places"] = sync_places()

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


@frappe.whitelist()
def sync_places():
    settings = frappe.get_single("Electrix Sync Settings")
    if not settings.enabled:
        return {"skipped": "Sync disabled"}

    if not frappe.db.exists("DocType", "Lugar"):
        return {"skipped": "DocType Lugar not found"}

    stats = {"created": 0, "updated": 0, "error": 0, "skipped": 0}

    try:
        items = StelClient(settings).get_addresses()
    except Exception:
        log_sync("Lugar", "Error", message="Could not fetch STEL addresses", error=traceback.format_exc())
        frappe.db.commit()
        return {"created": 0, "updated": 0, "error": 1, "skipped": 0}

    for item in items:
        status = sync_place(item)
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
        doc.customer_group = get_customer_group(settings, doc)
        doc.territory = get_territory(settings, doc)
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

        sync_billing_address(item, doc.name)

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


def get_customer_group(settings, doc):
    return (
        get_non_group_customer_group(settings.default_customer_group)
        or get_non_group_customer_group(doc.get("customer_group"))
        or get_non_group_customer_group("Individual")
        or get_non_group_customer_group("Commercial")
        or frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
    )


def get_non_group_customer_group(customer_group):
    if not customer_group:
        return None

    is_group = frappe.db.get_value("Customer Group", customer_group, "is_group")
    return customer_group if is_group == 0 else None


def get_territory(settings, doc):
    return settings.default_territory or doc.get("territory") or "All Territories"


def sync_billing_address(item, customer_name):
    address_data = item.get("main-address") if isinstance(item, dict) else None
    if not isinstance(address_data, dict):
        return None

    stel_address_id = get_stel_id(address_data)
    if not stel_address_id:
        log_sync("Address", "Skipped", None, "Customer", customer_name, "Missing STEL address ID", payload=address_data)
        return None

    try:
        existing = frappe.db.get_value("Address", {"custom_stel_id": stel_address_id}, "name")
        address = frappe.get_doc("Address", existing) if existing else frappe.new_doc("Address")

        address.address_title = get_address_title(address_data, customer_name)
        address.address_type = "Billing"
        address.address_line1 = get_address_line1(address_data)
        address.address_line2 = get_first(address_data, "extra-data", "extraData") or None
        address.city = get_first(address_data, "city-town", "city", "localidad") or None
        address.state = get_first(address_data, "province", "state", "provincia") or None
        address.pincode = get_first(address_data, "postal-code", "postalCode", "zip", "zipcode") or None
        address.country = get_country(address_data)
        address.is_primary_address = 1
        address.is_shipping_address = 0
        address.custom_stel_id = stel_address_id
        address.custom_stel_last_sync = now()
        address.custom_stel_sync_status = "Synced"

        ensure_dynamic_link(address, "Customer", customer_name)

        if existing:
            address.save(ignore_permissions=True)
            action = "updated"
        else:
            address.insert(ignore_permissions=True)
            action = "created"

        log_sync("Address", "Success", stel_address_id, "Address", address.name, f"Billing address {action}", payload=address_data)
        return action
    except Exception:
        mark_error("Address", stel_address_id)
        log_sync(
            "Address",
            "Error",
            stel_address_id,
            "Customer",
            customer_name,
            "Billing address sync failed",
            traceback.format_exc(),
            address_data,
        )
        return "error"


def sync_place(address_data):
    stel_address_id = get_stel_id(address_data)
    if not stel_address_id:
        log_sync("Lugar", "Skipped", None, message="Missing STEL address ID", payload=address_data)
        return "skipped"

    if is_main_or_billing_address(address_data):
        return "skipped"

    if frappe.db.exists("Address", {"custom_stel_id": stel_address_id}):
        return "skipped"

    try:
        existing = frappe.db.get_value("Lugar", {"custom_stel_id": stel_address_id}, "name")
        place = frappe.get_doc("Lugar", existing) if existing else frappe.new_doc("Lugar")

        place.nombre_lugar = get_place_name(address_data)
        place.direccion = get_address_line1(address_data)
        place.codigo_postal = get_first(address_data, "postal-code", "postalCode", "zip", "zipcode") or None
        place.municipio = get_first(address_data, "city-town", "city", "localidad") or None
        place.provincia = get_first(address_data, "province", "state", "provincia") or None
        place.pais = get_place_country(address_data)
        place.custom_stel_id = stel_address_id
        place.custom_stel_last_sync = now()
        place.custom_stel_sync_status = "Synced"

        if existing:
            place.save(ignore_permissions=True)
            action = "updated"
        else:
            place.insert(ignore_permissions=True)
            action = "created"

        log_sync("Lugar", "Success", stel_address_id, "Lugar", place.name, f"Lugar {action}", payload=address_data)
        return action
    except Exception:
        mark_error("Lugar", stel_address_id)
        log_sync("Lugar", "Error", stel_address_id, message="Lugar sync failed", error=traceback.format_exc(), payload=address_data)
        return "error"


def is_main_or_billing_address(address_data):
    address_type = (get_first(address_data, "address-type", "addressType") or "").upper()
    address_type_name = (get_first(address_data, "address-type-name", "addressTypeName", "name") or "").strip().lower()

    return address_type in {"DEFAULT", "BILLING"} or address_type_name in {"default", "billing", "facturacion", "facturación"}


def get_place_name(address_data):
    return (
        get_first(address_data, "name", "address-type-name", "formatted-address", "address-data")
        or f"STEL Lugar {get_stel_id(address_data)}"
    )


def get_address_title(address_data, customer_name):
    return get_first(address_data, "name", "address-type-name", "address-type") or customer_name


def get_address_line1(address_data):
    return (
        get_first(address_data, "formatted-address", "address-data", "address", "addressLine1", "direccion")
        or f"STEL Address {get_stel_id(address_data)}"
    )


def get_country(address_data):
    country_code = get_first(address_data, "country-code", "countryCode")
    if country_code:
        country = get_country_by_code(country_code)
        if country:
            return country

    return get_first(address_data, "country", "pais") or "Spain"


def get_place_country(address_data):
    raw_country = get_first(address_data, "country", "pais")
    candidates = [get_country(address_data), raw_country, "Spain", "España"]
    field = frappe.get_meta("Lugar").get_field("pais")
    options = field.options if field else None

    if options:
        for candidate in candidates:
            if candidate and frappe.db.exists(options, candidate):
                return candidate

    return candidates[0]


def get_country_by_code(country_code):
    meta = frappe.get_meta("Country")
    for fieldname in ("code", "country_code"):
        if meta.has_field(fieldname):
            country = frappe.db.get_value("Country", {fieldname: country_code}, "name")
            if country:
                return country

    if country_code == "ES" and frappe.db.exists("Country", "Spain"):
        return "Spain"

    return None


def ensure_dynamic_link(doc, link_doctype, link_name):
    for link in doc.get("links", []):
        if link.link_doctype == link_doctype and link.link_name == link_name:
            return

    doc.append("links", {"link_doctype": link_doctype, "link_name": link_name})


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
