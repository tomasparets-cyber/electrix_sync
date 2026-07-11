from electrix_sync.api.master_data import (
    address_destination,
    blank_counts,
    customer_name,
    get_location_key,
    sum_counts,
)


def test_customer_name_prefers_commercial_name():
    assert customer_name({"id": 68, "name": "Peter sticks", "legal-name": "Peter SL"}) == "Peter sticks"
    assert customer_name({"id": 68, "legal-name": "Peter SL"}) == "Peter SL"


def test_preview_counts_are_summed():
    first = blank_counts()
    first["create"] = 2
    second = blank_counts()
    second["unlinked"] = 1
    assert sum_counts([first, second]) == {
        "create": 2,
        "update": 0,
        "unchanged": 0,
        "conflict": 0,
        "unlinked": 1,
    }


def test_address_destination_uses_confirmed_business_rule():
    assert address_destination({"address-type": "DEFAULT"}) == "Address"
    assert address_destination({"address-type": "INVOICING"}) == "Address"
    assert address_destination({"address-type": "DELIVERY"}) == "Lugar"
    assert address_destination({"address-type": "OTHER"}) == "Lugar"
    assert address_destination({"address-type": "UNKNOWN"}) is None


def test_location_key_merges_same_physical_address():
    first = {"address-data": "Calle Mayor, 1", "postal-code": "07001", "city-town": "Palma", "country-code": "ES"}
    second = {"address-data": " CALLE MAYOR, 1 ", "postal-code": "07001", "city-town": "PALMA", "country-code": "es"}
    assert get_location_key(first) == get_location_key(second)
