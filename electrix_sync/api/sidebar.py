import frappe

from electrix_sync.v16_setup import add_projects_sidebar_items


@frappe.whitelist()
def repair_projects_sidebar():
    frappe.only_for("System Manager")
    result = add_projects_sidebar_items()
    frappe.db.commit()
    return result
