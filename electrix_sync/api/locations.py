import frappe
from frappe import _


def validate_lugar(doc, method=None):
    """Protect outbound STEL links for the custom Projects DocType."""
    for link in doc.get("stel_links", []):
        if not link.sync_enabled:
            continue
        if not link.customer:
            frappe.throw(_("A STEL-enabled location link requires an ERPNext customer."))
        stel_customer_id = frappe.db.get_value(
            "Customer", link.customer, "custom_stel_id"
        )
        if not stel_customer_id:
            frappe.throw(
                _("Customer {0} has no STEL ID. Keep this location local-only or synchronize the customer first.").format(
                    link.customer
                )
            )
        link.stel_customer_id = stel_customer_id
