import frappe
from frappe import _
from frappe.model.document import Document


class Lugar(Document):
    def validate(self):
        from electrix_sync.api.location_sync import erp_location_key
        self.location_key = erp_location_key(self)
        normalize_owner(self)
        seen_parties = set()
        for link in self.stel_links:
            normalize_link(link)
            party = (link.party_type, link.party_name)
            if link.party_name and party in seen_parties:
                frappe.throw(_("Account {0} is linked more than once to this location.").format(link.party_name))
            if link.party_name:
                seen_parties.add(party)
            link.is_owner_link = 1 if party == (self.owner_doctype, self.owner_name) else 0
            if not link.sync_enabled:
                continue
            if not link.party_name:
                frappe.throw(_("A STEL-enabled location link requires an ERPNext account."))
            stel_customer_id = frappe.db.get_value(link.party_type, link.party_name, "custom_stel_id")
            if not stel_customer_id:
                frappe.throw(
                    _("Account {0} has no STEL ID. Synchronize the account first.").format(
                        link.party_name
                    )
                )
            link.stel_customer_id = stel_customer_id


def normalize_owner(doc):
    if not doc.owner_name and doc.owner_customer:
        doc.owner_doctype, doc.owner_name = "Customer", doc.owner_customer
    if doc.owner_doctype not in {"Customer", "Lead"}:
        frappe.throw(_("Lugar owner must be a Customer or Lead."))
    doc.owner_customer = doc.owner_name if doc.owner_doctype == "Customer" else None


def normalize_link(link):
    if not link.party_name and link.customer:
        link.party_type, link.party_name = "Customer", link.customer
    if link.party_name and link.party_type not in {"Customer", "Lead"}:
        frappe.throw(_("Location links only support Customer or Lead accounts."))
    link.customer = link.party_name if link.party_type == "Customer" else None
