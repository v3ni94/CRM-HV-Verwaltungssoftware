"""AE08 / rule AE08-01: split of unbound reserve payments by plan ratio (expected by hand)."""

from decimal import Decimal

from mhvp.hoa.reserve_split import add_proposal, split_by_plan_ratio

D = Decimal


def test_split_ratio_and_rest_cent() -> None:
    # 100,00 by 1:2 -> 33,33 and 66,67 (half even 66,666.. -> 66,67, sum 100,00).
    parts = split_by_plan_ratio(D("100.00"), {"a": D("1200.00"), "b": D("2400.00")})
    assert parts == {"a": D("33.33"), "b": D("66.67")}
    # 100,00 in three equal parts: 33,33 each, rest 0,01 to the smallest id among the largest.
    parts = split_by_plan_ratio(D("100.00"), {"c": D("1"), "a": D("1"), "b": D("1")})
    assert parts == {"a": D("33.34"), "b": D("33.33"), "c": D("33.33")}
    assert sum(parts.values()) == D("100.00")


def test_split_without_plan_or_amount() -> None:
    assert split_by_plan_ratio(D("50.00"), {"a": D("0.00")}) == {}
    assert split_by_plan_ratio(D("0.00"), {"a": D("10.00")}) == {}
    assert split_by_plan_ratio(D("10.00"), {"a": D("10.00"), "b": D("0")}) == {"a": D("10.00")}


def test_add_proposal_keeps_paid() -> None:
    positions = [
        {"reserve_id": "a", "contributions_planned": "300.00", "contributions_paid": "50.00"},
        {"reserve_id": "b", "contributions_planned": "100.00", "contributions_paid": "0.00"},
    ]
    add_proposal(positions, D("40.00"))
    assert positions[0]["contributions_paid"] == "50.00"
    assert positions[0]["contributions_paid_proposal"] == "30.00"
    assert positions[0]["contributions_paid_with_proposal"] == "80.00"
    assert positions[1]["contributions_paid_proposal"] == "10.00"
