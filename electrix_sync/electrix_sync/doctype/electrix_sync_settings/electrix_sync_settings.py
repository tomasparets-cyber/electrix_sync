import frappe
from frappe.model.document import Document

from electrix_sync.api.stel import normalize_base_url


class ElectrixSyncSettings(Document):
    def validate(self):
        if self.enabled and not self.stel_base_url:
            frappe.throw("STEL Base URL is required when sync is enabled.")

        self.stel_base_url = normalize_base_url(self.stel_base_url).rstrip("/")

        if self.enabled and not self.api_token:
            frappe.throw("API Token is required when sync is enabled.")

        if self.page_limit and self.page_limit > 500:
            self.page_limit = 500

        if self.page_limit and self.page_limit < 1:
            self.page_limit = 500
