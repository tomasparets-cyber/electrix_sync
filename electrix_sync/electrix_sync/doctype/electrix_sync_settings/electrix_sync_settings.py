import frappe
from frappe.model.document import Document


class ElectrixSyncSettings(Document):
    def validate(self):
        if self.enabled and not self.stel_base_url:
            frappe.throw("STEL Base URL is required when sync is enabled.")

        if self.enabled and not self.api_token:
            frappe.throw("API Token is required when sync is enabled.")

        if self.page_limit and self.page_limit > 500:
            self.page_limit = 500

        if self.page_limit and self.page_limit < 1:
            self.page_limit = 500
