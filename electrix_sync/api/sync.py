import json
import re
import traceback

import frappe
from frappe.utils import now, today, validate_email_address, validate_phone_number

from electrix_sync.api.stel import StelClient


@frappe.whitelist()
def sync_all():
    settings = frappe.get_single("Electrix Sync Settings")
    if not settings.enabled:
        return {
            "customers": {"skipped": "Sync disabled"},
            "leads": {"skipped": "Sync disabled"},
            "places": {"skipped": "Sync disabled"},
            "employees": {"skipped": "Sync disabled"},
        }

    result = {}
    if getattr(settings, "sync_employees", 0):
        result["employees"] = sync_employees()
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
def sync_employees():
    settings = frappe.get_single("Electrix Sync Settings")
    if not settings.enabled:
        return {"skipped": "Sync disabled"}

    if not frappe.db.exists("DocType", "Employee"):
        return {"skipped": "DocType Employee not found"}

    stats = {"created": 0, "updated": 0, "error": 0, "skipped": 0}

    try:
        items = StelClient(settings).get_employees()
    except Exception:
        log_sync("Employee", "Error", message="Could not fetch STEL employees", error=traceback.format_exc())
        frappe.db.commit()
        return {"created": 0, "updated": 0, "error": 1, "skipped": 0}

    for item in items:
        status = sync_employee(item, settings)
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


def sync_employee(item, settings):
    stel_id = get_stel_id(item)
    if not stel_id:
        log_sync("Employee", "Skipped", None, message="Missing STEL ID", payload=item)
        return "skipped"

    try:
        if item.get("deleted") is True:
            return sync_deleted_employee(stel_id, item)

        email = get_valid_email(get_first(item, "email", "user-name", "username", "userName"))
        user_name = sync_user(item, settings, stel_id, email) if email and getattr(settings, "create_users", 1) else None

        existing = frappe.db.get_value("Employee", {"custom_stel_id": stel_id}, "name")
        doc = frappe.get_doc("Employee", existing) if existing else frappe.new_doc("Employee")

        first_name, last_name = get_employee_names(item, stel_id)
        doc.first_name = first_name
        if has_field(doc, "last_name"):
            doc.last_name = last_name
        doc.employee_name = " ".join(part for part in (first_name, last_name) if part).strip()
        doc.company = get_default_company(doc)
        doc.status = "Active"
        if has_field(doc, "gender") and not doc.get("gender"):
            doc.gender = get_employee_gender(item, settings)
        if has_field(doc, "date_of_birth") and not doc.get("date_of_birth"):
            doc.date_of_birth = get_employee_date_of_birth(item, settings)
        if has_field(doc, "date_of_joining") and not doc.get("date_of_joining"):
            doc.date_of_joining = get_employee_date_of_joining(item, settings)
        if user_name and has_field(doc, "user_id"):
            doc.user_id = user_name
        if email and has_field(doc, "personal_email"):
            doc.personal_email = email
        phone = get_phone(item, "phone", "phone2", "mobile", "mobileNo", "mobile_no", "telephone", "telefono")
        if phone and has_field(doc, "cell_number"):
            doc.cell_number = phone
        position = get_first(item, "position", "puesto")
        if position and has_field(doc, "designation"):
            doc.designation = get_or_create_designation(position)

        doc.custom_stel_id = stel_id
        doc.custom_stel_last_sync = now()
        doc.custom_stel_sync_status = "Synced"

        if existing:
            doc.save(ignore_permissions=True)
            action = "updated"
        else:
            doc.insert(ignore_permissions=True)
            action = "created"

        log_sync("Employee", "Success", stel_id, "Employee", doc.name, f"Employee {action}", payload=item)
        return action
    except Exception:
        mark_error("Employee", stel_id)
        log_sync("Employee", "Error", stel_id, message="Employee sync failed", error=traceback.format_exc(), payload=item)
        return "error"


def sync_user(item, settings, stel_id, email):
    existing = (
        frappe.db.get_value("User", {"custom_stel_id": stel_id}, "name")
        or frappe.db.get_value("User", {"email": email}, "name")
    )
    user = frappe.get_doc("User", existing) if existing else frappe.new_doc("User")

    first_name, last_name = get_employee_names(item, stel_id)
    user.email = email
    user.username = get_first(item, "user-name", "username", "userName") or email
    user.first_name = first_name
    if hasattr(user, "last_name"):
        user.last_name = last_name
    user.enabled = 0 if item.get("deleted") is True else 1
    if hasattr(user, "send_welcome_email"):
        user.send_welcome_email = 0
    phone = get_phone(item, "phone", "phone2", "mobile", "mobileNo", "mobile_no", "telephone", "telefono")
    if phone and hasattr(user, "mobile_no"):
        user.mobile_no = phone
    user.custom_stel_id = stel_id
    user.custom_stel_last_sync = now()
    user.custom_stel_sync_status = "Synced"

    if existing:
        user.save(ignore_permissions=True)
        action = "updated"
    else:
        user.insert(ignore_permissions=True)
        action = "created"

    log_sync("User", "Success", stel_id, "User", user.name, f"User {action}", payload=item)
    return user.name


def sync_deleted_employee(stel_id, item):
    user_name = frappe.db.get_value("User", {"custom_stel_id": stel_id}, "name")
    if user_name:
        frappe.db.set_value(
            "User",
            user_name,
            {
                "enabled": 0,
                "custom_stel_last_sync": now(),
                "custom_stel_sync_status": "Skipped",
            },
            update_modified=False,
        )

    employee_name = frappe.db.get_value("Employee", {"custom_stel_id": stel_id}, "name")
    if employee_name:
        frappe.db.set_value(
            "Employee",
            employee_name,
            {
                "status": "Inactive",
                "custom_stel_last_sync": now(),
                "custom_stel_sync_status": "Skipped",
            },
            update_modified=False,
        )
        log_sync("Employee", "Skipped", stel_id, "Employee", employee_name, "STEL employee is deleted", payload=item)
        return "updated"

    log_sync("Employee", "Skipped", stel_id, message="STEL employee is deleted", payload=item)
    return "skipped"


def get_employee_names(item, stel_id):
    first_name = get_first(item, "name", "firstName", "first_name", "nombre")
    last_name = get_first(item, "surname", "lastName", "last_name", "apellidos")

    if not first_name:
        full_name = get_first(item, "full-name", "fullName", "employeeName")
        if full_name:
            parts = str(full_name).strip().split(" ", 1)
            first_name = parts[0]
            last_name = last_name or (parts[1] if len(parts) > 1 else None)

    if not first_name:
        email = get_first(item, "email", "user-name", "username", "userName")
        first_name = str(email).split("@", 1)[0] if email else f"STEL Employee {stel_id}"

    return str(first_name).strip(), str(last_name).strip() if last_name else ""


def get_default_company(doc):
    return doc.get("company") or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    ) or frappe.db.get_value("Company", {}, "name")


def get_employee_gender(item, settings):
    raw_gender = get_first(item, "gender", "sex", "genero", "sexo")
    gender = normalize_gender(raw_gender)
    if gender:
        return gender

    default_gender = getattr(settings, "default_employee_gender", None)
    if default_gender and frappe.db.exists("Gender", default_gender):
        return default_gender

    for candidate in ("Other", "Prefer Not to Say", "Gender Diverse", "Male", "Female"):
        if frappe.db.exists("Gender", candidate):
            return candidate

    return frappe.db.get_value("Gender", {}, "name") or get_or_create_gender("Other")


def normalize_gender(value):
    if not value:
        return None

    gender = str(value).strip()
    if frappe.db.exists("Gender", gender):
        return gender

    mapped = {
        "m": "Male",
        "male": "Male",
        "hombre": "Male",
        "masculino": "Male",
        "f": "Female",
        "female": "Female",
        "mujer": "Female",
        "femenino": "Female",
        "other": "Other",
        "otro": "Other",
        "otra": "Other",
    }.get(gender.lower())

    return mapped if mapped and frappe.db.exists("Gender", mapped) else None


def get_employee_date_of_birth(item, settings):
    return normalize_date(
        get_first(item, "date-of-birth", "dateOfBirth", "birthdate", "birthday", "fecha_nacimiento")
        or getattr(settings, "default_employee_date_of_birth", None)
        or "1900-01-01"
    )


def get_employee_date_of_joining(item, settings):
    return normalize_date(
        get_first(item, "date-of-joining", "dateOfJoining", "joiningDate", "startDate", "creation-date")
        or getattr(settings, "default_employee_date_of_joining", None)
        or today()
    )


def normalize_date(value):
    if not value:
        return None

    return str(value).strip()[:10]


def get_valid_email(value):
    if not value:
        return None

    email = str(value).strip()
    try:
        return email if validate_email_address(email, throw=False) else None
    except Exception:
        return None


def get_or_create_designation(position):
    position = str(position).strip()
    if not position:
        return None

    if frappe.db.exists("Designation", position):
        return position

    try:
        frappe.get_doc({"doctype": "Designation", "designation_name": position}).insert(ignore_permissions=True)
        return position
    except Exception:
        return None


def get_or_create_gender(gender):
    try:
        doc = frappe.get_doc({"doctype": "Gender", "gender": gender})
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        return None


def has_field(doc, fieldname):
    return frappe.get_meta(doc.doctype).has_field(fieldname)


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
