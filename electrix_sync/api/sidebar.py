import frappe

from electrix_sync.v16_setup import (
    add_projects_sidebar_items,
    add_projects_workspace_shortcuts,
    migrate_project_location_field,
    repair_task_project_links,
)


@frappe.whitelist()
def repair_projects_sidebar():
    frappe.only_for("System Manager")
    result = add_projects_sidebar_items()
    frappe.db.commit()
    return result


def maintain_projects_customizations():
    """Idempotent self-healing after ERPNext replaces workspace metadata."""
    migrate_project_location_field()
    add_projects_workspace_shortcuts()
    result = add_projects_sidebar_items()
    repair_task_project_links()
    frappe.db.commit()
    return result
