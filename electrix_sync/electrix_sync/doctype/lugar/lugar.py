import frappe
from frappe import _
from frappe.model.document import Document


class Lugar(Document):
    def validate(self):
        for link in self.stel_links:
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
