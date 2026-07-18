import frappe
from frappe import _


def validate_lugar(doc, method=None):
    """Protect outbound STEL links for the custom Projects DocType."""
    from electrix_sync.api.location_sync import erp_location_key
    doc.location_key = erp_location_key(doc)
    seen_customers = set()
    for link in doc.get("stel_links", []):
        if link.customer and link.customer in seen_customers:
            frappe.throw(_("Customer {0} is linked more than once to this location.").format(link.customer))
        if link.customer:
            seen_customers.add(link.customer)
        link.is_owner_link = 1 if link.customer and link.customer == doc.get("owner_customer") else 0
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
