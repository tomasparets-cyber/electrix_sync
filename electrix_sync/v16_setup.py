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
    migrate_standard_status_and_type_fields()
    remove_redundant_functional_fields()
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
            {**common[1], "insert_after": "custom_stel_reference"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
        ],
        "Issue": [
            {**common[0], "insert_after": "subject"},
            {"fieldname": "custom_stel_reference", "label": "STEL Incident Reference", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_stel_id"},
            {**common[1], "insert_after": "custom_stel_reference"},
            {**common[2], "insert_after": "custom_stel_modified_at"},
            {**common[3], "insert_after": "custom_stel_payload_hash"},
            {**common[4], "insert_after": "custom_stel_last_sync"},
        ],
        "Event": [
            {**common[0], "insert_after": "subject"},
            {"fieldname": "custom_assigned_employee", "label": "Empleado planificado", "fieldtype": "Link", "options": "Employee", "insert_after": "custom_stel_id"},
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


def migrate_standard_status_and_type_fields():
    """Move earlier mirrored STEL values into standard ERPNext fields."""
    from electrix_sync.api.sync import normalize_event_category

    event_meta = frappe.get_meta("Event") if frappe.db.exists("DocType", "Event") else None
    if not event_meta:
        return
    legacy_fields = {field.fieldname for field in event_meta.fields}
    query_fields = ["name", "status"]
    if "custom_stel_event_state" in legacy_fields:
        query_fields.append("custom_stel_event_state")
    if "custom_stel_event_type" in legacy_fields:
        query_fields.append("custom_stel_event_type")
    for event in frappe.get_all("Event", fields=query_fields, limit_page_length=0):
        values = {}
        legacy_state = str(event.get("custom_stel_event_state") or "").upper()
        if legacy_state:
            values["status"] = {"PENDING": "Open", "COMPLETED": "Closed", "REFUSED": "Cancelled"}.get(
                legacy_state, event.status or "Open"
            )
        type_id = event.get("custom_stel_event_type")
        if type_id and event_meta.has_field("event_category"):
            category = frappe.db.get_value("STEL Event Type", str(type_id), "event_type_name")
            if category:
                values["event_category"] = normalize_event_category(category)
        if values:
            frappe.db.set_value("Event", event.name, values, update_modified=False)


def remove_redundant_functional_fields():
    """Remove UI fields that duplicated standard Task/Event status and type fields."""
    redundant = (
        ("Task", "custom_stel_state_id"),
        ("Task", "custom_stel_type_id"),
        ("Task", "custom_stel_assignee_id"),
        ("Task", "custom_stel_address_id"),
        ("Issue", "custom_stel_state_id"),
        ("Issue", "custom_stel_type_id"),
        ("Issue", "custom_stel_assignee_id"),
        ("Issue", "custom_stel_address_id"),
        ("Event", "custom_stel_event_state"),
        ("Event", "custom_stel_event_type"),
        ("Event", "custom_stel_event_type_name"),
    )
    for doctype, fieldname in redundant:
        name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
        if name:
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
    for doctype in {row[0] for row in redundant}:
        frappe.clear_cache(doctype=doctype)


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
    """Build the managed part of Frappe v16's persistent Projects sidebar."""
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

    desired_links = (
        {"label": "Home", "link_type": "Workspace", "link_to": "Projects", "icon": "home"},
        {"label": "Tablero", "link_type": "Page", "link_to": "project-dashboard", "icon": "bar-chart-2"},
        {"label": "Lugar", "link_type": "DocType", "link_to": "Lugar", "icon": "map-pin"},
        {"label": "Project", "link_type": "DocType", "link_to": "Project", "icon": "briefcase"},
        {"label": "Task", "link_type": "DocType", "link_to": "Task", "icon": "list-checks"},
        {"label": "Event", "link_type": "DocType", "link_to": "Event", "icon": "calendar-days"},
    )
    updated = []
    for sidebar_name in by_name:
        try:
            items = frappe.get_all(
                "Workspace Sidebar Item",
                filters={"parent": sidebar_name, "parenttype": "Workspace Sidebar", "parentfield": "items"},
                fields=["name", "idx", "label", "type", "link_type", "link_to", "child"],
                order_by="idx asc",
            )
            managed_targets = {row["link_to"] for row in desired_links} | {"planning", "planning-calendar"}
            planning_sections = {
                row.name for row in items
                if row.type in {"Section Break", "Sidebar Item Group"}
                and str(row.label or "").casefold() in {"planificación", "planificacion"}
            }
            candidates = {}
            for row in items:
                if row.link_to in managed_targets and row.link_to not in candidates:
                    candidates[row.link_to] = row
            # Core sidebar routes may vary slightly between ERPNext builds;
            # reuse their translated Home/Dashboard entries instead of creating duplicates.
            for row in items:
                label = str(row.label or "").casefold()
                if label in {"home", "inicio"} and "Projects" not in candidates:
                    candidates["Projects"] = row
                if label in {"dashboard", "tablero"} and "project-dashboard" not in candidates:
                    candidates["project-dashboard"] = row

            # Remove obsolete/duplicate planning links and an earlier section;
            # they contain navigation metadata only, never business records.
            keep_names = {row.name for row in candidates.values() if row.link_to not in {"planning", "planning-calendar"}}
            for row in items:
                if row.name in planning_sections or (
                    row.link_to in managed_targets and row.name not in keep_names
                ):
                    frappe.delete_doc("Workspace Sidebar Item", row.name, ignore_permissions=True)

            ordered_names = []
            for idx, item_data in enumerate(desired_links, start=1):
                row = candidates.get(item_data["link_to"])
                if row and frappe.db.exists("Workspace Sidebar Item", row.name):
                    name = row.name
                else:
                    name = frappe.get_doc({
                        "doctype": "Workspace Sidebar Item",
                        "parent": sidebar_name,
                        "parenttype": "Workspace Sidebar",
                        "parentfield": "items",
                        "idx": idx, "type": "Link", "child": 0, **item_data,
                    }).insert(ignore_permissions=True).name
                frappe.db.set_value("Workspace Sidebar Item", name, {
                    "idx": idx, "type": "Link", "child": 0, **item_data,
                }, update_modified=False)
                ordered_names.append(name)

            section = frappe.get_doc({
                "doctype": "Workspace Sidebar Item", "parent": sidebar_name,
                "parenttype": "Workspace Sidebar", "parentfield": "items",
                "idx": 7, "label": "Planificación", "type": "Section Break",
                "collapsible": 1, "indent": 0, "show_arrow": 0, "keep_closed": 0,
            }).insert(ignore_permissions=True)
            ordered_names.append(section.name)
            for idx, item_data in enumerate((
                {"label": "Tabla", "link_type": "Page", "link_to": "planning", "icon": "table"},
                {"label": "Calendario", "link_type": "Page", "link_to": "planning-calendar", "icon": "calendar"},
            ), start=8):
                row = frappe.get_doc({
                    "doctype": "Workspace Sidebar Item", "parent": sidebar_name,
                    "parenttype": "Workspace Sidebar", "parentfield": "items",
                    "idx": idx, "type": "Link", "child": 1, **item_data,
                }).insert(ignore_permissions=True)
                ordered_names.append(row.name)

            remaining = [row for row in items if row.name not in ordered_names and frappe.db.exists("Workspace Sidebar Item", row.name)]
            for idx, row in enumerate(remaining, start=10):
                frappe.db.set_value("Workspace Sidebar Item", row.name, "idx", idx, update_modified=False)
            updated.append({"sidebar": sidebar_name, "order": [row["label"] for row in desired_links] + ["Planificación", "Tabla", "Calendario"]})
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Could not update Projects sidebar {sidebar_name}"
            )

    frappe.clear_cache()
    return {"updated": updated, "sidebars_found": list(by_name)}
