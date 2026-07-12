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
        "stel_event_type",
        "stel_event_assignment",
    ):
        frappe.reload_doc("electrix_sync", "doctype", doctype_name, force=True)

    frappe.clear_cache(doctype="STEL Bulk Sync Run")
    frappe.clear_cache(doctype="STEL Raw Record")
    ensure_master_data_fields()
    add_projects_workspace_shortcuts()
    add_projects_sidebar_items()


def ensure_master_data_fields():
    common = [
        {"fieldname": "custom_stel_id", "label": "STEL ID", "fieldtype": "Data", "unique": 1, "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_stel_modified_at", "label": "STEL Modified At", "fieldtype": "Datetime", "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_stel_payload_hash", "label": "STEL Payload Hash", "fieldtype": "Data", "read_only": 1, "hidden": 1, "no_copy": 1},
        {"fieldname": "custom_stel_last_sync", "label": "STEL Last Sync", "fieldtype": "Datetime", "read_only": 1, "no_copy": 1},
        {"fieldname": "custom_stel_sync_status", "label": "STEL Sync Status", "fieldtype": "Select", "options": "Pending\nSynced\nError\nSkipped", "read_only": 1, "no_copy": 1},
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
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
        ],
        "Address": [
            {**common[0], "insert_after": "address_title"},
            {"fieldname": "custom_stel_latitude", "label": "STEL Latitude", "fieldtype": "Float", "read_only": 1, "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_longitude", "label": "STEL Longitude", "fieldtype": "Float", "read_only": 1, "insert_after": "custom_stel_latitude"},
            {"fieldname": "custom_stel_external_id", "label": "STEL External ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_longitude"},
            {**common[1], "insert_after": "custom_stel_external_id"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
        ],
        "Contact": [
            {**common[0], "insert_after": "first_name"},
            {"fieldname": "custom_stel_fax", "label": "STEL Fax", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_comments", "label": "STEL Comments", "fieldtype": "Small Text", "read_only": 1, "insert_after": "custom_stel_fax"},
            {**common[1], "insert_after": "custom_stel_comments"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
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
        "Employee": [
            {**common[0], "insert_after": "employee_name"},
            {"fieldname": "custom_stel_calendar_id", "label": "STEL Calendar ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_id"},
            {**common[1], "insert_after": "custom_stel_calendar_id"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
        ],
        "Task": [
            {**common[0], "insert_after": "subject"},
            {"fieldname": "custom_stel_reference", "label": "STEL Incident Reference", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_address_id", "label": "STEL Address ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_reference"},
            {"fieldname": "custom_stel_assignee_id", "label": "STEL Assignee ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_address_id"},
            {"fieldname": "custom_stel_state_id", "label": "STEL State ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_assignee_id"},
            {"fieldname": "custom_stel_type_id", "label": "STEL Type ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_state_id"},
            {**common[1], "insert_after": "custom_stel_type_id"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
        ],
        "Issue": [
            {**common[0], "insert_after": "subject"},
            {"fieldname": "custom_stel_reference", "label": "STEL Incident Reference", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_address_id", "label": "STEL Address ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_reference"},
            {"fieldname": "custom_stel_assignee_id", "label": "STEL Assignee ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_address_id"},
            {"fieldname": "custom_stel_state_id", "label": "STEL State ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_assignee_id"},
            {"fieldname": "custom_stel_type_id", "label": "STEL Type ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_state_id"},
            {**common[1], "insert_after": "custom_stel_type_id"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
        ],
        "Event": [
            {**common[0], "insert_after": "subject"},
            {"fieldname": "custom_stel_event_type", "label": "Tipo de evento STEL", "fieldtype": "Link", "options": "STEL Event Type", "insert_after": "custom_stel_id"},
            {"fieldname": "custom_stel_event_type_name", "label": "Nombre del tipo STEL", "fieldtype": "Data", "fetch_from": "custom_stel_event_type.event_type_name", "read_only": 1, "insert_after": "custom_stel_event_type"},
            {"fieldname": "custom_stel_event_state", "label": "Estado STEL", "fieldtype": "Select", "options": "PENDING\nCOMPLETED\nREFUSED", "default": "PENDING", "insert_after": "custom_stel_event_type_name"},
            {"fieldname": "custom_assigned_employee", "label": "Empleado planificado", "fieldtype": "Link", "options": "Employee", "insert_after": "custom_stel_event_state"},
            {"fieldname": "custom_stel_assignments", "label": "Empleados y calendarios STEL", "fieldtype": "Table", "options": "STEL Event Assignment", "insert_after": "custom_assigned_employee"},
            {"fieldname": "custom_stel_calendar_id", "label": "STEL Calendar ID", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_assignments"},
            {"fieldname": "custom_planning_status", "label": "Estado de planificación", "fieldtype": "Select", "options": "Unplanned\nPlanned\nCompleted", "default": "Unplanned", "insert_after": "custom_stel_calendar_id"},
            {"fieldname": "custom_estimated_duration", "label": "Duración estimada (horas)", "fieldtype": "Float", "default": "1", "insert_after": "custom_planning_status"},
            {**common[1], "insert_after": "custom_estimated_duration"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
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


def add_projects_sidebar_items():
    """Add Lugar and Planificación to Frappe v16's persistent Projects sidebar."""
    if not frappe.db.exists("DocType", "Workspace Sidebar"):
        return {"updated": [], "missing": ["Workspace Sidebar DocType"]}

    sidebar_rows = frappe.get_all(
        "Workspace Sidebar",
        filters=[["Workspace Sidebar", "title", "like", "Projects%"]],
        fields=["name", "title", "module", "for_user"],
    )
    module_rows = frappe.get_all(
        "Workspace Sidebar",
        filters={"module": "Projects"},
        fields=["name", "title", "module", "for_user"],
    )
    by_name = {row.name: row for row in [*sidebar_rows, *module_rows]}

    desired = (
        {"label": "Lugar", "type": "Link", "link_type": "DocType", "link_to": "Lugar", "icon": "map-pin"},
        {"label": "Planificación", "type": "Link", "link_type": "Page", "link_to": "planning", "icon": "calendar"},
        {"label": "Evento", "type": "Link", "link_type": "DocType", "link_to": "Event", "icon": "calendar-days"},
    )
    updated = []
    for sidebar_name in by_name:
        try:
            items = frappe.get_all(
                "Workspace Sidebar Item",
                filters={"parent": sidebar_name, "parenttype": "Workspace Sidebar", "parentfield": "items"},
                fields=["name", "idx", "link_to"],
                order_by="idx asc",
            )
            existing_links = {item.link_to for item in items}
            missing = [item for item in desired if item["link_to"] not in existing_links]
            if not missing:
                continue
            task_idx = next((int(item.idx) for item in items if item.link_to == "Task"), len(items))
            for item in reversed(items):
                if int(item.idx or 0) > task_idx:
                    frappe.db.set_value(
                        "Workspace Sidebar Item", item.name, "idx", int(item.idx) + len(missing), update_modified=False
                    )
            for offset, item_data in enumerate(missing, start=1):
                child = frappe.get_doc({
                    "doctype": "Workspace Sidebar Item",
                    "parent": sidebar_name,
                    "parenttype": "Workspace Sidebar",
                    "parentfield": "items",
                    "idx": task_idx + offset,
                    **item_data,
                })
                child.insert(ignore_permissions=True)
            updated.append({"sidebar": sidebar_name, "added": [item["label"] for item in missing]})
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Could not update Projects sidebar {sidebar_name}"
            )

    frappe.clear_cache()
    return {"updated": updated, "sidebars_found": list(by_name)}
