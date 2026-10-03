"""AK01 (GAI-215, GAI-202, GAI-214): sum invariants of distributions with predefined results.

Heating cost component (both modes of the tenant switch), house money monthly rates (all
remainder modes), time shares of consecutive occupancies and deposit interest (rate history
equals reference rate, ROUND_HALF_UP on cents).
"""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.billing import heating_calc
from mhvp.billing.calc import Share, days, distribute
from mhvp.contracts import deposit_settlement as ds
from mhvp.hoa.calc import monthly_rates

P0, P1 = date(2025, 1, 1), date(2025, 12, 31)


def _occ(key: str, unit: str, start: date, end: date, area: str) -> heating_calc.Occupant:
    return heating_calc.Occupant(
        key=key, unit_id=unit, unit_number=unit, start=start, end=end, area=Decimal(area)
    )


OCCUPANTS = [
    _occ("a", "1", P0, P1, "70"),
    _occ("b", "2", P0, P1, "50"),
    _occ("c", "3", P0, P1, "33"),
]
CONSUMPTION = {"a": Decimal("1000"), "b": Decimal("700"), "c": Decimal("301")}


def _total(result: dict) -> Decimal:
    return sum((Decimal(v["total"]) for v in result["per_occupant"].values()), Decimal(0))


@pytest.mark.parametrize("costs", ["1000.00", "999.99", "0.01", "12345.67"])
@pytest.mark.parametrize("mode", ["legacy_warn", "distribute"])
def test_heating_component_positive_adds_up_exactly(costs: str, mode: str) -> None:
    result = heating_calc._component(
        "Heizung", Decimal(costs), 70, OCCUPANTS, CONSUMPTION, {}, mode
    )
    assert _total(result) == Decimal(costs)
    assert result["warning"] is None


def test_heating_component_negative_distribute_adds_up_exactly() -> None:
    result = heating_calc._component(
        "Heizung", Decimal("-100.00"), 70, OCCUPANTS, CONSUMPTION, {}, "distribute"
    )
    assert _total(result) == Decimal("-100.00")
    assert result["warning"] is None
    assert Decimal(result["consumption_part"]) + Decimal(result["basic_part"]) == Decimal("-100")


def test_heating_component_negative_legacy_warn_keeps_zero_and_warns() -> None:
    result = heating_calc._component(
        "Heizung", Decimal("-100.00"), 70, OCCUPANTS, CONSUMPTION, {}, "legacy_warn"
    )
    assert _total(result) == Decimal("0.00")
    assert "AJ01-01" in result["warning"]


@pytest.mark.parametrize(
    ("annual", "mode", "expected_first", "expected_last"),
    [
        ("1000.00", "report_only", "83.33", "83.33"),
        ("1000.00", "first_month", "83.37", "83.33"),
        ("1000.00", "last_month", "83.33", "83.37"),
        ("1000.06", "first_month", "83.32", "83.34"),
        ("1000.06", "last_month", "83.34", "83.32"),
    ],
)
def test_monthly_rates_remainder_modes(
    annual: str, mode: str, expected_first: str, expected_last: str
) -> None:
    rates = monthly_rates(Decimal(annual), mode)
    assert len(rates) == 12
    assert rates[0] == Decimal(expected_first)
    assert rates[-1] == Decimal(expected_last)
    if mode == "report_only":
        # 12 * 83.33 = 999.96, the 4 cents stay as reported difference.
        assert sum(rates) == Decimal("999.96")
    else:
        assert sum(rates) == Decimal(annual)


def test_monthly_rates_half_up() -> None:
    # 100.14 / 12 = 8.345 exactly: half up gives 8.35, half even would give 8.34.
    assert monthly_rates(Decimal("100.14"))[1] == Decimal("8.35")


def test_time_shares_of_consecutive_occupancies_add_up() -> None:
    # Change of tenant on 15.04.2025: 105 + 260 = 365 days, costs 1000.00 split exactly.
    first, second = days(P0, date(2025, 4, 15)), days(date(2025, 4, 16), P1)
    assert first + second == days(P0, P1) == 365
    split = distribute(
        Decimal("1000.00"),
        [Share(("1", "a"), Decimal(first)), Share(("1", "b"), Decimal(second))],
    )
    assert split == {("1", "a"): Decimal("287.67"), ("1", "b"): Decimal("712.33")}
    assert sum(split.values()) == Decimal("1000.00")


def test_deposit_interest_history_equals_reference_rate_and_half_up() -> None:
    changes = [ds.BalanceChange(on=date(2024, 1, 1), amount=Decimal("1500.00"))]
    until = date(2025, 12, 31)
    reference = ds.interest_by_reference_rate(
        changes, {2024: Decimal("0.10"), 2025: Decimal("0.10")}, until
    )
    history = ds.interest_by_rate_history(changes, [(date(2024, 1, 1), Decimal("0.10"))], until)
    assert [(y.year, y.days, y.amount) for y in reference] == [
        (y.year, y.days, y.amount) for y in history
    ]
    # 1500.00 * 0.10 % for a full year = 1.50 in both years (366 and 365 day basis).
    assert [y.amount for y in reference] == [Decimal("1.50"), Decimal("1.50")]
