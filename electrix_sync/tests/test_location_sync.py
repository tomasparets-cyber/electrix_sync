from electrix_sync.api.location_sync import extract_id, location_external_id, location_payload_hash


def test_location_external_id_is_stable_per_place_and_customer():
    first = location_external_id("LUGAR-00001", 42)
    assert first == location_external_id("LUGAR-00001", 42)
    assert first != location_external_id("LUGAR-00001", 43)
    assert first != location_external_id("LUGAR-00002", 42)
    assert len(first) <= 64


def test_extract_id_accepts_stel_response_shapes():
    assert extract_id({"id": 101}) == 101
    assert extract_id({"data": {"address-id": "102"}}) == "102"
    assert extract_id([{"addressId": 103}]) == 103
    assert extract_id({"path": "app.stelorder.com/app/addresses/104"}) == "104"


def test_location_payload_hash_is_order_independent():
    assert location_payload_hash({"name": "Hotel", "account-id": 1}) == location_payload_hash({"account-id": 1, "name": "Hotel"})
