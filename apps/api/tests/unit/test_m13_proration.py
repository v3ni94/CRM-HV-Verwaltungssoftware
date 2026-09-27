"""M13-01 to M13-03: pro rata receivables, instalments and VAT split with precomputed values.

Expected values are worked out by hand (rule documents docs/rules/M13-01.md to M13-03.md):
- start on 15.03.2026 (31 days), 500,00 per month: 500 x 17 / 31 = 274,19354839 -> 274,19;
  30/360: 500 x 16 / 30 = 266,66666667 -> 266,67; full month: 500,00;
- amount change 500,00 until 15.03., 600,00 from 16.03.: 241,93548387 -> 241,94 and
  309,67741935 -> 309,68, exact total 551,61290322 -> 551,61, so the last segment carries the
  rounding difference of -0,01 (309,67);
- quarterly instalment of 300,00 per month anchored on 01.01.: 900,00 due in January (advance)
  or March (arrears), nothing in February;
- VAT 19 % on 1.000,00 net: 190,00 tax, 1.190,00 gross.
"""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.accounting import proration as pr

D = Decimal
MAR = date(2026, 3, 1)


def test_start_on_15th_of_31_day_month_calendar_days() -> None:
    result = pr.prorate_month(
        MAR,
        pr.CALENDAR_DAYS,
        [(date(2026, 3, 15), None, D("500.00"))],
        contract_start=date(2026, 3, 15),
    )
    assert result.total == D("274.19")
    assert result.full_month is False
    [seg] = result.segments
    assert (seg.start, seg.end, seg.days, seg.base_days) == (
        date(2026, 3, 15),
        date(2026, 3, 31),
        17,
        31,
    )
    assert seg.fraction == D("0.54838710")
    assert seg.exact == D("274.19354839")
    assert seg.rounded == D("274.19")
    assert seg.adjustment == D("0")
    path = result.as_json()
    assert path["method"] == "calendar_days"
    assert path["total"] == "274.19"


def test_start_on_15th_thirty_360_and_full_month() -> None:
    periods = [(date(2026, 3, 15), None, D("500.00"))]
    t360 = pr.prorate_month(MAR, pr.THIRTY_360, periods)
    assert t360.total == D("266.67")
    assert t360.segments[0].days == 16
    assert t360.segments[0].base_days == 30
    assert t360.segments[0].exact == D("266.66666667")
    full = pr.prorate_month(MAR, pr.FULL_MONTH, periods)
    assert full.total == D("500.00")
    assert full.full_month is False


def test_end_on_last_day_thirty_360_counts_30_days() -> None:
    # 16.03. to 31.03. is 15 days 30/360 (end of month counts as day 30): 500 x 15 / 30.
    result = pr.prorate_month(MAR, pr.THIRTY_360, [(date(2026, 3, 16), None, D("500.00"))])
    assert result.segments[0].days == 15
    assert result.total == D("250.00")


def test_amount_change_puts_rounding_difference_on_last_segment() -> None:
    periods = [
        (date(2026, 1, 1), date(2026, 3, 15), D("500.00")),
        (date(2026, 3, 16), None, D("600.00")),
    ]
    result = pr.prorate_month(MAR, pr.CALENDAR_DAYS, periods)
    first, second = result.segments
    assert (first.exact, first.rounded) == (D("241.93548387"), D("241.94"))
    assert second.exact == D("309.67741935")
    assert result.exact_total == D("551.61290322")
    assert result.total == D("551.61")
    assert second.adjustment == D("-0.01")
    assert second.rounded == D("309.67")
    assert first.rounded + second.rounded == result.total
    # full month rule: the amount valid on the last covered day applies in full
    assert pr.prorate_month(MAR, pr.FULL_MONTH, periods).total == D("600.00")


def test_full_month_and_contract_end_cut() -> None:
    periods = [(date(2020, 1, 1), None, D("500.00"))]
    whole = pr.prorate_month(MAR, pr.CALENDAR_DAYS, periods)
    assert whole.total == D("500.00")
    assert whole.full_month is True
    ended = pr.prorate_month(MAR, pr.CALENDAR_DAYS, periods, contract_end=date(2026, 3, 10))
    assert ended.total == D("161.29")  # 500 x 10 / 31 = 161,29032258
    assert ended.segments[0].end == date(2026, 3, 10)
    gone = pr.prorate_month(MAR, pr.CALENDAR_DAYS, periods, contract_end=date(2026, 2, 28))
    assert gone.segments == []
    assert gone.total == D("0.00")


def test_quarterly_instalment_in_advance_and_arrears() -> None:
    periods = [(date(2020, 1, 1), None, D("300.00"))]

    def run(month: date, mode: str) -> pr.Instalment | None:
        return pr.instalment_for_month(
            month,
            interval="quarterly",
            anchor=date(2026, 1, 1),
            payment_mode=mode,
            amount_basis=pr.PER_MONTH,
            method=pr.CALENDAR_DAYS,
            periods=periods,
        )

    jan = run(date(2026, 1, 1), pr.ADVANCE)
    assert jan is not None
    assert (jan.period_start, jan.period_end) == (date(2026, 1, 1), date(2026, 3, 31))
    assert jan.total == D("900.00")
    assert len(jan.months) == 3
    assert run(date(2026, 2, 1), pr.ADVANCE) is None
    assert run(date(2026, 3, 1), pr.ADVANCE) is None
    assert run(date(2026, 1, 1), pr.ARREARS) is None
    mar = run(date(2026, 3, 1), pr.ARREARS)
    assert mar is not None
    assert mar.total == D("900.00")
    assert mar.due_month == date(2026, 3, 1)
    # second quarter, anchored on the schedule start, not on the calendar year
    apr = run(date(2026, 4, 1), pr.ADVANCE)
    assert apr is not None
    assert apr.period_end == date(2026, 6, 30)
    assert apr.as_json()["payment_mode"] == "advance"


def test_quarterly_instalment_with_start_inside_the_quarter() -> None:
    # Contract starts 15.02.: January 0, February 300 x 14 / 28 = 150,00, March 300,00.
    result = pr.instalment_for_month(
        date(2026, 1, 1),
        interval="quarterly",
        anchor=date(2026, 1, 1),
        payment_mode=pr.ADVANCE,
        amount_basis=pr.PER_MONTH,
        method=pr.CALENDAR_DAYS,
        periods=[(date(2026, 2, 15), None, D("300.00"))],
        contract_start=date(2026, 2, 15),
    )
    assert result is not None
    assert [m.total for m in result.months] == [D("0.00"), D("150.00"), D("300.00")]
    assert result.total == D("450.00")


def test_amount_per_instalment_is_spread_over_the_months() -> None:
    result = pr.instalment_for_month(
        date(2026, 7, 1),
        interval="semiannual",
        anchor=date(2026, 1, 1),
        payment_mode=pr.ADVANCE,
        amount_basis=pr.PER_INSTALMENT,
        method=pr.CALENDAR_DAYS,
        periods=[(date(2020, 1, 1), None, D("1200.00"))],
    )
    assert result is not None
    assert result.period_start == date(2026, 7, 1)
    assert result.period_end == date(2026, 12, 31)
    assert result.total == D("1200.00")
    assert result.months[0].segments[0].amount == D("200.00")


def test_annual_anchor_and_semiannual_arrears() -> None:
    start, end, first, last = pr.instalment_period(date(2025, 4, 1), "annual", date(2026, 5, 1))
    assert (start, end) == (date(2026, 4, 1), date(2027, 3, 31))
    assert (first, last) == (date(2026, 4, 1), date(2027, 3, 1))
    start, end, _, _ = pr.instalment_period(date(2026, 1, 1), "semiannual", date(2026, 9, 1))
    assert (start, end) == (date(2026, 7, 1), date(2026, 12, 31))


def test_vat_split_19_percent_and_tax_free() -> None:
    assert pr.split_vat(D("1000.00"), D("19")) == {
        "net": D("1000.00"),
        "vat_percent": D("19"),
        "vat": D("190.00"),
        "gross": D("1190.00"),
    }
    # pro rata net 274,19 x 19 % = 52,0961 -> 52,10
    assert pr.split_vat(D("274.19"), D("19"))["vat"] == D("52.10")
    assert pr.split_vat(D("274.19"), D("19"))["gross"] == D("326.29")
    assert pr.split_vat(D("500.00"), D("0"))["gross"] == D("500.00")
    assert pr.split_vat(D("500.00"), D("0"))["vat"] == D("0.00")


def test_due_dates_and_invalid_inputs() -> None:
    assert pr.due_date_for("day", 31, date(2026, 2, 1)) == date(2026, 2, 28)
    assert pr.due_date_for("last_day", 3, MAR) == date(2026, 3, 31)
    assert pr.due_date_for("day_next_month", 3, date(2026, 12, 1)) == date(2027, 1, 3)
    assert pr.due_date_for("workday", 3, MAR) is None  # no holiday calendar released
    with pytest.raises(ValueError, match="unknown"):
        pr.prorate_month(MAR, "actual_365", [])
    with pytest.raises(ValueError, match="unknown"):
        pr.instalment_for_month(
            MAR,
            interval="quarterly",
            anchor=MAR,
            payment_mode="later",
            amount_basis=pr.PER_MONTH,
            method=pr.CALENDAR_DAYS,
            periods=[],
        )
