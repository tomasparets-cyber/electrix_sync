import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as frappe_create_custom_fields


SYNC_STATUS_OPTIONS = "Pending\nSynced\nError\nSkipped"


def after_install():
    create_custom_fields()
    create_unique_indexes()


def create_custom_fields():
    custom_fields = {
        "Customer": [
            {
                "fieldname": "custom_stel_id",
                "label": "STEL ID",
                "fieldtype": "Data",
                "insert_after": "customer_name",
                "unique": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_last_sync",
                "label": "STEL Last Sync",
                "fieldtype": "Datetime",
                "insert_after": "custom_stel_id",
                "read_only": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_sync_status",
                "label": "STEL Sync Status",
                "fieldtype": "Select",
                "options": SYNC_STATUS_OPTIONS,
                "insert_after": "custom_stel_last_sync",
                "default": "Pending",
                "no_copy": 1,
            },
        ],
        "Lead": [
            {
                "fieldname": "custom_stel_id",
                "label": "STEL ID",
                "fieldtype": "Data",
                "insert_after": "lead_name",
                "unique": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_last_sync",
                "label": "STEL Last Sync",
                "fieldtype": "Datetime",
                "insert_after": "custom_stel_id",
                "read_only": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_sync_status",
                "label": "STEL Sync Status",
                "fieldtype": "Select",
                "options": SYNC_STATUS_OPTIONS,
                "insert_after": "custom_stel_last_sync",
                "default": "Pending",
                "no_copy": 1,
            },
        ],
        "Address": [
            {
                "fieldname": "custom_stel_id",
                "label": "STEL ID",
                "fieldtype": "Data",
                "insert_after": "address_title",
                "unique": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_last_sync",
                "label": "STEL Last Sync",
                "fieldtype": "Datetime",
                "insert_after": "custom_stel_id",
                "read_only": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_sync_status",
                "label": "STEL Sync Status",
                "fieldtype": "Select",
                "options": SYNC_STATUS_OPTIONS,
                "insert_after": "custom_stel_last_sync",
                "default": "Pending",
                "no_copy": 1,
            },
        ],
    }

    if frappe.db.exists("DocType", "Lugar"):
        custom_fields["Lugar"] = [
            {
                "fieldname": "custom_stel_id",
                "label": "STEL ID",
                "fieldtype": "Data",
                "insert_after": "pais",
                "unique": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_last_sync",
                "label": "STEL Last Sync",
                "fieldtype": "Datetime",
                "insert_after": "custom_stel_id",
                "read_only": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "custom_stel_sync_status",
                "label": "STEL Sync Status",
                "fieldtype": "Select",
                "options": SYNC_STATUS_OPTIONS,
                "insert_after": "custom_stel_last_sync",
                "default": "Pending",
                "no_copy": 1,
            },
        ]

    frappe_create_custom_fields(custom_fields, update=True)

    frappe.clear_cache(doctype="Customer")
    frappe.clear_cache(doctype="Lead")
    frappe.clear_cache(doctype="Address")
    if frappe.db.exists("DocType", "Lugar"):
        frappe.clear_cache(doctype="Lugar")


def create_unique_indexes():
    doctypes = ["Customer", "Lead", "Address"]
    if frappe.db.exists("DocType", "Lugar"):
        doctypes.append("Lugar")

    for doctype in doctypes:
        table = f"tab{doctype}"
        index_name = f"unique_{doctype.lower()}_stel_id"
        if not frappe.db.has_index(table, index_name):
            try:
                frappe.db.add_unique(doctype, ["custom_stel_id"], constraint_name=index_name)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"Could not create {index_name}")
