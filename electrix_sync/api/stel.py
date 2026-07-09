from urllib.parse import urljoin

import frappe
import requests

STEL_BASE_URL = "https://app.stelorder.com"


class StelClient:
    def __init__(self, settings=None):
        self.settings = settings or frappe.get_single("Electrix Sync Settings")
        self.base_url = normalize_base_url(self.settings.stel_base_url)
        self.token = self.settings.get_password("api_token") if self.settings.api_token else None
        self.page_limit = min(max(int(getattr(self.settings, "page_limit", None) or 500), 1), 500)

    def get_customers(self):
        return self.get_collection(self.settings.customers_endpoint)

    def get_leads(self):
        return self.get_collection(self.settings.leads_endpoint)

    def get_addresses(self):
        endpoint = getattr(self.settings, "addresses_endpoint", None) or "/app/addresses"
        return self.get_collection(endpoint)

    def get_employees(self):
        endpoint = getattr(self.settings, "employees_endpoint", None) or "/app/employees"
        return self.get_collection(endpoint)

    def get_incidents(self):
        endpoint = getattr(self.settings, "incidents_endpoint", None) or "/app/incidents"
        return self.get_collection(endpoint)

    def get_events(self):
        endpoint = getattr(self.settings, "events_endpoint", None) or "/app/events"
        return self.get_collection(endpoint)

    def get_collection(self, endpoint):
        if not endpoint:
            return []

        url = urljoin(self.base_url, endpoint.lstrip("/"))
        items = []
        params = {"limit": self.page_limit, "start": 0}

        while url:
            response = requests.get(url, headers=self._headers(), params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            batch = self._extract_items(data)
            items.extend(batch)
            url = self._extract_next_url(data)
            if url:
                params = {}
            elif len(batch) >= self.page_limit:
                params["start"] += self.page_limit
                url = urljoin(self.base_url, endpoint.lstrip("/"))
            else:
                params = {}

        return items

    def _headers(self):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.token:
            header_name = getattr(self.settings, "auth_header_name", None) or "APIKEY"
            header_prefix = (getattr(self.settings, "auth_header_prefix", None) or "").strip()
            headers[header_name] = f"{header_prefix} {self.token}".strip()

        return headers

    def _extract_items(self, data):
        if isinstance(data, list):
            return data

        if not isinstance(data, dict):
            return []

        for key in ("data", "items", "results", "customers", "clients", "leads", "employees", "incidents", "events"):
            value = data.get(key)
            if isinstance(value, list):
                return value

        return []

    def _extract_next_url(self, data):
        if not isinstance(data, dict):
            return None

        links = data.get("links")
        if isinstance(links, dict) and links.get("next"):
            return links.get("next")

        meta = data.get("meta")
        if isinstance(meta, dict) and meta.get("next"):
            return meta.get("next")

        return data.get("next") if isinstance(data.get("next"), str) else None


def normalize_base_url(base_url):
    base_url = (base_url or "").strip()

    if base_url.startswith(STEL_BASE_URL):
        base_url = STEL_BASE_URL

    return base_url.rstrip("/") + "/"
