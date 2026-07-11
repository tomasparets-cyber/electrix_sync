import json

import frappe


RESOURCE_DOCTYPE = {
    "clients": "Customer",
    "addresses": "Address",
    "contacts": "Contact",
}


@frappe.whitelist()
def preview_customer_import():
    """Dry-run the STEL customer, address and contact conversion."""
    frappe.only_for("System Manager")
    staged = {key: get_staged(key) for key in RESOURCE_DOCTYPE}
    staged_client_ids = {str(row["data"].get("id")) for row in staged["clients"] if row["data"].get("id") is not None}
    result = {
        "dry_run": True,
        "clients": preview_clients(staged["clients"]),
        "addresses": preview_linked(staged["addresses"], "Address", staged_client_ids),
        "contacts": preview_linked(staged["contacts"], "Contact", staged_client_ids),
    }
    result["totals"] = sum_counts(result.values())
    return result


def get_staged(resource_type):
    rows = frappe.get_all(
        "STEL Raw Record",
        filters={"resource_type": resource_type},
        fields=["remote_id", "payload", "payload_hash"],
        order_by="remote_id asc",
        limit_page_length=0,
    )
    output = []
    for row in rows:
        try:
            data = json.loads(row.payload)
        except (TypeError, ValueError):
            data = {}
        output.append({"remote_id": str(row.remote_id), "payload_hash": row.payload_hash, "data": data})
    return output


def preview_clients(rows):
    counts = blank_counts()
    conflicts = []
    for row in rows:
        stel_id = row["remote_id"]
        existing = get_existing("Customer", stel_id)
        if existing:
            counts["unchanged" if existing.custom_stel_payload_hash == row["payload_hash"] else "update"] += 1
            continue
        tax_id = clean(row["data"].get("identification-number"))
        tax_match = frappe.db.get_value("Customer", {"tax_id": tax_id}, "name") if tax_id else None
        if tax_match:
            counts["conflict"] += 1
            conflicts.append({"stel_id": stel_id, "tax_id": tax_id, "erpnext": tax_match, "stel_name": customer_name(row["data"])})
        else:
            counts["create"] += 1
    counts["details"] = conflicts[:100]
    return counts


def preview_linked(rows, doctype, staged_client_ids):
    counts = blank_counts()
    missing = []
    for row in rows:
        existing = get_existing(doctype, row["remote_id"])
        if existing:
            counts["unchanged" if existing.custom_stel_payload_hash == row["payload_hash"] else "update"] += 1
            continue
        account_id = row["data"].get("account-id")
        linked = account_id is not None and (
            str(account_id) in staged_client_ids
            or customer_exists(str(account_id))
        )
        if linked:
            counts["create"] += 1
        else:
            counts["unlinked"] += 1
            missing.append({"stel_id": row["remote_id"], "account_id": account_id, "name": row["data"].get("name")})
    counts["details"] = missing[:100]
    return counts


def blank_counts():
    return {"create": 0, "update": 0, "unchanged": 0, "conflict": 0, "unlinked": 0}


def get_existing(doctype, stel_id):
    if not frappe.db.has_column(doctype, "custom_stel_id"):
        return None
    fields = ["name"]
    if frappe.db.has_column(doctype, "custom_stel_payload_hash"):
        fields.append("custom_stel_payload_hash")
    existing = frappe.db.get_value(
        doctype, {"custom_stel_id": stel_id}, fields, as_dict=True
    )
    if existing and "custom_stel_payload_hash" not in existing:
        existing.custom_stel_payload_hash = None
    return existing


def customer_exists(stel_id):
    return bool(
        frappe.db.has_column("Customer", "custom_stel_id")
        and frappe.db.exists("Customer", {"custom_stel_id": stel_id})
    )


def sum_counts(groups):
    total = blank_counts()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for key in total:
            total[key] += int(group.get(key) or 0)
    return total


def customer_name(data):
    return clean(data.get("name")) or clean(data.get("legal-name")) or f"STEL {data.get('id')}"


def clean(value):
    return str(value).strip() if value not in (None, "") else None
