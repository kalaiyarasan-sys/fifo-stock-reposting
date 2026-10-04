from datetime import date

import pytest

from stock_ledger import build_milk_scenario, change_rate, get_row, post


def test_values_before_the_change():
    ledger = build_milk_scenario()
    assert get_row(ledger, "DN-15JAN", "Milk")["value_change"] == -4000
    assert get_row(ledger, "PR-20JAN", "Milk")["balance_value"] == 7000
    assert get_row(ledger, "MFG-21JAN", "Milk")["value_change"] == -5800
    assert get_row(ledger, "MFG-21JAN", "Milk Powder")["rate"] == 580
    assert get_row(ledger, "DN-25JAN", "Milk Powder")["value_change"] == -5800


def test_values_after_rate_changed_to_80():
    ledger = build_milk_scenario()
    change_rate(ledger, "PR-10JAN", "Milk", 80)

    assert get_row(ledger, "PR-10JAN", "Milk")["balance_value"] == 9000

    # 15 Jan delivery: cost is same, but balance value is different
    dn = get_row(ledger, "DN-15JAN", "Milk")
    assert dn["value_change"] == -4000
    assert dn["balance_value"] == 5000
    assert dn["queue"] == [[20, 50], [50, 80]]

    assert get_row(ledger, "PR-20JAN", "Milk")["balance_value"] == 8000

    # 20@50 + 50@80 + 30@60 = 6800
    assert get_row(ledger, "MFG-21JAN", "Milk")["value_change"] == -6800
    assert get_row(ledger, "MFG-21JAN", "Milk Powder")["rate"] == 680
    assert get_row(ledger, "DN-25JAN", "Milk Powder")["value_change"] == -6800


def test_opening_stock_is_not_touched():
    ledger = build_milk_scenario()
    before = dict(get_row(ledger, "OPENING", "Milk"))
    change_rate(ledger, "PR-10JAN", "Milk", 80)
    assert get_row(ledger, "OPENING", "Milk") == before


def test_final_milk_stock_is_same():
    ledger = build_milk_scenario()
    change_rate(ledger, "PR-10JAN", "Milk", 80)
    last = get_row(ledger, "MFG-21JAN", "Milk")
    assert last["balance_qty"] == 20
    assert last["balance_value"] == 1200


def test_rate_decrease():
    ledger = build_milk_scenario()
    change_rate(ledger, "PR-10JAN", "Milk", 40)
    assert get_row(ledger, "MFG-21JAN", "Milk")["value_change"] == -4800
    assert get_row(ledger, "MFG-21JAN", "Milk Powder")["rate"] == 480


def test_repost_twice_gives_same_result():
    ledger = build_milk_scenario()
    change_rate(ledger, "PR-10JAN", "Milk", 80)
    first = [dict(row) for row in ledger]
    change_rate(ledger, "PR-10JAN", "Milk", 80)
    assert ledger == first


def test_changing_last_purchase_does_not_change_earlier_rows():
    ledger = build_milk_scenario()
    before = dict(get_row(ledger, "DN-15JAN", "Milk"))
    change_rate(ledger, "PR-20JAN", "Milk", 70)
    assert get_row(ledger, "DN-15JAN", "Milk") == before
    # 20@50 + 50@60 + 30@70
    assert get_row(ledger, "MFG-21JAN", "Milk")["value_change"] == -6100


def test_backdated_purchase_changes_later_cost():
    ledger = []
    post(ledger, "Milk", date(2026, 1, 10), "PR-1", 50, 60)
    post(ledger, "Milk", date(2026, 1, 15), "DN-1", -30)
    assert get_row(ledger, "DN-1", "Milk")["value_change"] == -1800

    post(ledger, "Milk", date(2026, 1, 5), "PR-0", 20, 40)  # entered late
    assert get_row(ledger, "DN-1", "Milk")["value_change"] == -(20 * 40 + 10 * 60)


def test_balance_value_matches_queue():
    ledger = build_milk_scenario()
    change_rate(ledger, "PR-10JAN", "Milk", 80)
    for row in ledger:
        assert row["balance_value"] == sum(q * r for q, r in row["queue"])


def test_cannot_deliver_more_than_stock():
    ledger = build_milk_scenario()
    rows_before = len(ledger)
    with pytest.raises(ValueError):
        post(ledger, "Milk", date(2026, 1, 26), "DN-BIG", -500)
    assert len(ledger) == rows_before  # nothing half saved


def test_cannot_change_rate_of_delivery_or_finished_good():
    ledger = build_milk_scenario()
    with pytest.raises(ValueError):
        change_rate(ledger, "DN-15JAN", "Milk", 80)
    with pytest.raises(ValueError):
        change_rate(ledger, "MFG-21JAN", "Milk Powder", 999)
    with pytest.raises(ValueError):
        change_rate(ledger, "NOT-THERE", "Milk", 80)
