from electrix_sync.api.bulk_sync import get_manifest, get_remote_id


def test_bulk_manifest_matches_all_stel_collections():
    manifest = get_manifest()

    assert len(manifest) == 56
    assert len({row["key"] for row in manifest}) == 56
    assert len({row["endpoint"] for row in manifest}) == 56


def test_remote_id_prefers_stel_primary_id():
    assert get_remote_id({"id": 5921195, "reference": "INC00260"}) == 5921195
    assert get_remote_id({"reference": "INC00260"}) == "INC00260"
