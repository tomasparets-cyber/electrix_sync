import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_staging_doctypes():
    """Load the phase-1 staging schema after install and every migration.

    Explicit reloads make upgrades from the v15 app deterministic even when the
    site was originally installed before these DocTypes existed.
    """
    for doctype_name in (
        "stel_bulk_sync_run",
        "stel_raw_record",
        "lugar_stel_link",
        "lugar",
    ):
        frappe.reload_doc("electrix_sync", "doctype", doctype_name, force=True)

    frappe.clear_cache(doctype="STEL Bulk Sync Run")
    frappe.clear_cache(doctype="STEL Raw Record")
    ensure_master_data_fields()
    add_projects_workspace_shortcuts()


def ensure_master_data_fields():
    common = [
        {"fieldname": "custom_stel_id", "label": "STEL ID", "fieldtype": "Data", "unique": 1, "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_stel_modified_at", "label": "STEL Modified At", "fieldtype": "Datetime", "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_stel_payload_hash", "label": "STEL Payload Hash", "fieldtype": "Data", "read_only": 1, "hidden": 1, "no_copy": 1},
    ]
    fields = {
        "Customer": [
            {**common[0], "insert_after": "customer_name"},
            {"fieldname": "custom_stel_reference", "label": "STEL Reference", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_full_reference", "label": "STEL Full Reference", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_reference"},
            {"fieldname": "custom_stel_legal_name", "label": "STEL Legal Name", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_full_reference"},
            {"fieldname": "custom_stel_phone_2", "label": "STEL Phone 2", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_legal_name"},
            {"fieldname": "custom_stel_external_id", "label": "STEL External ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_phone_2"},
            {**common[1], "insert_after": "custom_stel_external_id"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
        ],
        "Address": [
            {**common[0], "insert_after": "address_title"},
            {"fieldname": "custom_stel_latitude", "label": "STEL Latitude", "fieldtype": "Float", "read_only": 1, "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_longitude", "label": "STEL Longitude", "fieldtype": "Float", "read_only": 1, "insert_after": "custom_stel_latitude"},
            {"fieldname": "custom_stel_external_id", "label": "STEL External ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_longitude"},
            {**common[1], "insert_after": "custom_stel_external_id"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
        ],
        "Contact": [
            {**common[0], "insert_after": "first_name"},
            {"fieldname": "custom_stel_fax", "label": "STEL Fax", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_comments", "label": "STEL Comments", "fieldtype": "Small Text", "read_only": 1, "insert_after": "custom_stel_fax"},
            {**common[1], "insert_after": "custom_stel_comments"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
        ],
        "Project": [
            {
                "fieldname": "custom_service_location",
                "label": "Lugar de servicio",
                "fieldtype": "Link",
                "options": "Lugar",
                "insert_after": "customer",
            },
        ],
    }
    available = {doctype: definitions for doctype, definitions in fields.items() if frappe.db.exists("DocType", doctype)}
    create_custom_fields(available, update=True)
    # Custom fields are created from an after_migrate hook, after Frappe's
    # normal schema pass. Force the physical columns to be added in this deploy.
    for doctype in available:
        frappe.clear_cache(doctype=doctype)
        frappe.db.updatedb(doctype)


def add_projects_workspace_shortcuts():
    """Expose Lugar and Planificación alongside the standard project tools."""
    if not frappe.db.exists("Workspace", "Projects"):
        return
    try:
        workspace = frappe.get_doc("Workspace", "Projects")
        existing = {row.link_to for row in workspace.get("shortcuts", [])}
        if "Lugar" not in existing:
            workspace.append("shortcuts", {"label": "Lugar", "type": "DocType", "link_to": "Lugar", "doc_view": "List"})
        if "planning" not in existing:
            workspace.append("shortcuts", {"label": "Planificación", "type": "Page", "link_to": "planning"})
        workspace.flags.ignore_validate = True
        workspace.save(ignore_permissions=True)
    except Exception:
        # Workspace layouts vary between Frappe releases. A layout issue must
        # never block schema migration or data synchronization.
        frappe.log_error(frappe.get_traceback(), "Could not add Electrix project shortcuts")
