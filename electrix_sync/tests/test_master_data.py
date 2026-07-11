from electrix_sync.api.master_data import blank_counts, customer_name, sum_counts


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
