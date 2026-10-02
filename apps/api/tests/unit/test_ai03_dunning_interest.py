"""AI03 (GAH-110, GAH-113): day count variants of the default interest and the Basiszinssatz
hint. Expected values computed by hand (0.1.8):

- 1.000,00 EUR at 7 % from 01.01.2024 to 01.03.2024 (60 days, leap year 2024):
  act_365_fixed: 1000 * 0,07 * 60 / 365 = 11,5068... -> 11,51 EUR;
  act_act:       1000 * 0,07 * 60 / 366 = 11,4754... -> 11,48 EUR.
- 1.000,00 EUR at 7 % from 01.12.2023 to 01.02.2024 (31 days 2023, 31 days 2024):
  act_act: 1000 * 0,07 * (31/365 + 31/366) = 5,9452... + 5,9289... = 11,8741... -> 11,87 EUR;
  act_365_fixed: 1000 * 0,07 * 62 / 365 = 11,8904... -> 11,89 EUR.
"""

from datetime import date
from decimal import Decimal

from mhvp.accounting import dunning

RATES = [(date(2023, 7, 1), Decimal("2"))]


def _run(start: date, end: date, day_count: str) -> dunning.InterestResult:
    return dunning.interest_over_periods(
        RATES, Decimal("5"), Decimal("1000.00"), start, end, day_count
    )


def test_default_stays_days_by_365_also_in_leap_year() -> None:
    result = dunning.interest_over_periods(
        RATES, Decimal("5"), Decimal("1000.00"), date(2024, 1, 1), date(2024, 3, 1)
    )
    assert result.amount == Decimal("11.51")
    assert result.day_count == dunning.DAY_COUNT_FIXED
    assert result.periods[0]["day_count"] == "act_365_fixed"
    assert "365" in result.periods[0]["day_count_label"]


def test_actual_day_count_uses_366_in_leap_year() -> None:
    result = _run(date(2024, 1, 1), date(2024, 3, 1), dunning.DAY_COUNT_ACTUAL)
    assert result.amount == Decimal("11.48")
    assert result.periods[0]["day_count"] == "act_act"


def test_actual_day_count_splits_at_year_end() -> None:
    assert _run(date(2023, 12, 1), date(2024, 2, 1), "act_act").amount == Decimal("11.87")
    assert _run(date(2023, 12, 1), date(2024, 2, 1), "act_365_fixed").amount == Decimal("11.89")


def test_year_fraction_edges() -> None:
    assert dunning.year_fraction(date(2024, 1, 1), date(2024, 1, 1), "act_act") == 0
    assert dunning.year_fraction(date(2024, 1, 1), date(2025, 1, 1), "act_act") == 1
    assert dunning.year_fraction(date(2023, 1, 1), date(2024, 1, 1), "act_act") == 1


def test_interest_for_takes_tenant_switch() -> None:
    eff = dunning.EffectiveSettings(
        property_id=None,
        interest_enabled=True,
        interest_spread=Decimal("5"),
        interest_day_count=dunning.DAY_COUNT_ACTUAL,
    )
    result = dunning.interest_for(
        eff, RATES, Decimal("1000.00"), date(2024, 1, 1), date(2024, 3, 1)
    )
    assert result.amount == Decimal("11.48")


def test_base_rate_hint_per_half_year() -> None:
    assert dunning.base_rate_boundary(date(2026, 10, 2)) == date(2026, 7, 1)
    assert dunning.base_rate_boundary(date(2026, 6, 30)) == date(2026, 1, 1)
    assert dunning.next_base_rate_dates(date(2026, 10, 2)) == [date(2027, 1, 1), date(2027, 7, 1)]
    assert dunning.next_base_rate_dates(date(2026, 1, 1)) == [date(2026, 7, 1), date(2027, 1, 1)]
    fresh = [(date(2026, 7, 1), Decimal("1.27"))]
    assert dunning.base_rate_hint(fresh, date(2026, 10, 2)) is None
    stale = dunning.base_rate_hint(fresh, date(2027, 1, 2))
    assert stale is not None
    assert "01.07.2026" in stale
    assert "01.01.2027" in stale
    assert dunning.base_rate_hint([], date(2026, 10, 2)) is not None
