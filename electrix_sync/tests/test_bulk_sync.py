from datetime import datetime

from electrix_sync.api.bulk_sync import (
    get_manifest,
    get_remote_id,
    get_run_manifest,
    get_source_modified,
)


def test_bulk_manifest_matches_all_stel_collections():
    manifest = get_manifest()

    assert len(manifest) == 56
    assert len({row["key"] for row in manifest}) == 56
    assert len({row["endpoint"] for row in manifest}) == 56


def test_remote_id_prefers_stel_primary_id():
    assert get_remote_id({"id": 5921195, "reference": "INC00260"}) == 5921195
    assert get_remote_id({"reference": "INC00260"}) == "INC00260"


def test_source_modified_is_naive_utc_for_mariadb():
    assert get_source_modified(
        {"utc-last-modification-date": "2026-04-30T06:30:03+02:00"}
    ) == datetime(2026, 4, 30, 4, 30, 3)


def test_incremental_manifest_only_contains_operational_resources():
    assert {row["key"] for row in get_run_manifest("Incremental")} == {
        "addresses",
        "clients",
        "contacts",
        "employees",
        "events",
        "incidents",
    }
