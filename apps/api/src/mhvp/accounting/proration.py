"""Pro rata receivables, non monthly instalments and VAT split (7.5, M13-01 to M13-03).

Pure functions without database access. Every result carries its calculation path so the run
can store it as JSON (rule documents ``docs/rules/M13-01.md`` to ``M13-03.md``). Intermediate
values use 8 decimals (NUMERIC(20,8)), amounts are rounded half up to 2 decimals and the
rounding difference of a month goes to its last partial period.

The methods are contract rules chosen by the operator (default per tenant); none of them is
claimed as a legal rule (7.5: a freely chosen 30/360 method is no general legal basis).
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CALENDAR_DAYS = "calendar_days"
THIRTY_360 = "thirty_360"
FULL_MONTH = "full_month"
PRORATION_METHODS = (CALENDAR_DAYS, THIRTY_360, FULL_MONTH)

ADVANCE = "advance"
ARREARS = "arrears"
PAYMENT_MODES = (ADVANCE, ARREARS)

PER_MONTH = "per_month"
PER_INSTALMENT = "per_instalment"
AMOUNT_BASES = (PER_MONTH, PER_INSTALMENT)

INTERVAL_MONTHS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}

CENT = Decimal("0.01")
RATIO = Decimal("0.00000001")


def q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def q8(value: Decimal) -> Decimal:
    return value.quantize(RATIO, rounding=ROUND_HALF_UP)


def month_first(day: date) -> date:
    return day.replace(day=1)


def month_last(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def months_between(start: date, end: date) -> int:
    """Whole months from the month of ``start`` to the month of ``end`` (both first days)."""
    return (end.year - start.year) * 12 + end.month - start.month


@dataclass
class Segment:
    """A part of a month with one constant amount."""

    start: date
    end: date
    amount: Decimal
    method: str
    days: int = 0
    base_days: int = 0
    fraction: Decimal = Decimal(0)
    exact: Decimal = Decimal(0)
    rounded: Decimal = Decimal(0)
    adjustment: Decimal = Decimal(0)

    def as_json(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "amount_per_month": str(self.amount),
            "method": self.method,
            "days": self.days,
            "base_days": self.base_days,
            "fraction": str(self.fraction),
            "exact": str(self.exact),
            "rounded": str(self.rounded),
            "adjustment": str(self.adjustment),
        }


@dataclass
class MonthResult:
    month: date
    method: str
    segments: list[Segment] = field(default_factory=list)
    total: Decimal = Decimal("0.00")
    exact_total: Decimal = Decimal(0)
    full_month: bool = True

    def as_json(self) -> dict[str, Any]:
        return {
            "month": self.month.isoformat(),
            "method": self.method,
            "full_month": self.full_month,
            "segments": [s.as_json() for s in self.segments],
            "exact_total": str(self.exact_total),
            "total": str(self.total),
        }


def _fraction(method: str, start: date, end: date) -> tuple[int, int, Decimal]:
    """Days counted, base days of the month and the ratio (8 decimals) for one segment."""
    last = month_last(start)
    if method == CALENDAR_DAYS:
        base = last.day
        days = (end - start).days + 1
    elif method == THIRTY_360:
        base = 30
        d1 = min(start.day, 30)
        d2 = 30 if end == last else min(end.day, 30)
        days = d2 - d1 + 1
    elif method == FULL_MONTH:
        base = 1
        days = 1
    else:
        raise ValueError(f"unknown proration method {method}")
    return days, base, q8(Decimal(days) / Decimal(base))


def prorate_month(
    month: date,
    method: str,
    periods: Sequence[tuple[date, date | None, Decimal]],
    *,
    contract_start: date | None = None,
    contract_end: date | None = None,
) -> MonthResult:
    """Amount of one month from validity periods ``(valid_from, valid_to, amount per month)``.

    Periods are cut to the month and to the contract term; gaps count as 0,00. With
    ``full_month`` the amount valid on the last covered day of the month applies in full.
    Rounding: every segment is rounded half up to 2 decimals; the month total is the rounded
    exact sum and the difference, if any, is put on the last segment.
    """
    if method not in PRORATION_METHODS:
        raise ValueError(f"unknown proration method {method}")
    first, last = month_first(month), month_last(month)
    lower = max(first, contract_start) if contract_start else first
    upper = min(last, contract_end) if contract_end else last
    result = MonthResult(month=first, method=method)
    if lower > upper:
        return result
    cut: list[tuple[date, date, Decimal]] = []
    for valid_from, valid_to, amount in sorted(periods, key=lambda p: p[0]):
        s = max(valid_from, lower)
        e = min(valid_to, upper) if valid_to else upper
        if s <= e:
            cut.append((s, e, amount))
    if not cut:
        return result
    result.full_month = cut[0][0] == first and cut[-1][1] == last and len(cut) == 1
    if method == FULL_MONTH:
        s, e, amount = cut[-1]
        seg = Segment(s, e, amount, method, 1, 1, Decimal(1), q8(amount), q2(amount))
        result.segments = [seg]
        result.exact_total, result.total = seg.exact, seg.rounded
        return result
    for s, e, amount in cut:
        days, base, ratio = _fraction(method, s, e)
        exact = q8(amount * Decimal(days) / Decimal(base))
        result.segments.append(Segment(s, e, amount, method, days, base, ratio, exact, q2(exact)))
    result.exact_total = sum((s.exact for s in result.segments), Decimal(0))
    result.total = q2(result.exact_total)
    parts = sum((s.rounded for s in result.segments), Decimal("0.00"))
    diff = result.total - parts
    if diff:
        seg = result.segments[-1]
        seg.adjustment = diff
        seg.rounded = seg.rounded + diff
    return result


@dataclass
class Instalment:
    """One instalment of a non monthly schedule that falls due in the run month."""

    period_start: date
    period_end: date
    due_month: date
    mode: str
    amount_basis: str
    months: list[MonthResult] = field(default_factory=list)
    total: Decimal = Decimal("0.00")
    exact_total: Decimal = Decimal(0)

    def as_json(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "due_month": self.due_month.isoformat(),
            "payment_mode": self.mode,
            "amount_basis": self.amount_basis,
            "months": [m.as_json() for m in self.months],
            "exact_total": str(self.exact_total),
            "total": str(self.total),
        }


def instalment_period(anchor: date, interval: str, month: date) -> tuple[date, date, date, date]:
    """Instalment period containing ``month`` for a schedule anchored at ``anchor``.

    Returns (period_start, period_end, first_month, last_month). Periods are consecutive blocks
    of ``INTERVAL_MONTHS[interval]`` months counted from the month of ``anchor``.
    """
    n = INTERVAL_MONTHS[interval]
    offset = months_between(month_first(anchor), month_first(month))
    index = offset // n
    start = add_months(month_first(anchor), index * n)
    last_month = add_months(start, n - 1)
    return start, month_last(last_month), start, last_month


def instalment_for_month(
    month: date,
    *,
    interval: str,
    anchor: date,
    payment_mode: str,
    amount_basis: str,
    method: str,
    periods: Sequence[tuple[date, date | None, Decimal]],
    contract_start: date | None = None,
    contract_end: date | None = None,
) -> Instalment | None:
    """The instalment due in ``month`` or None when nothing falls due in this month.

    ``per_month``: the contract amount is per month, the instalment is the sum of the monthly
    (pro rata) amounts of the period. ``per_instalment``: the contract amount is the whole
    instalment; every month counts 1/n of it, pro rata within a month by the same method.
    """
    if payment_mode not in PAYMENT_MODES:
        raise ValueError(f"unknown payment mode {payment_mode}")
    if amount_basis not in AMOUNT_BASES:
        raise ValueError(f"unknown amount basis {amount_basis}")
    n = INTERVAL_MONTHS[interval]
    p_start, p_end, first_month, last_month = instalment_period(anchor, interval, month)
    due_month = first_month if payment_mode == ADVANCE else last_month
    if due_month != month_first(month):
        return None
    result = Instalment(p_start, p_end, due_month, payment_mode, amount_basis)
    divisor = Decimal(1) if amount_basis == PER_MONTH else Decimal(n)
    scaled = [(f, t, q8(a / divisor)) for f, t, a in periods]
    for k in range(n):
        m = add_months(first_month, k)
        result.months.append(
            prorate_month(
                m, method, scaled, contract_start=contract_start, contract_end=contract_end
            )
        )
    result.exact_total = sum((m.exact_total for m in result.months), Decimal(0))
    result.total = q2(result.exact_total)
    return result


def split_vat(net: Decimal, vat_percent: Decimal) -> dict[str, Decimal]:
    """Net, tax and gross for a receivable with the contract's tax rate (rounded half up)."""
    vat = q2(q8(net * vat_percent / Decimal(100))) if vat_percent else Decimal("0.00")
    return {"net": q2(net), "vat_percent": vat_percent, "vat": vat, "gross": q2(net) + vat}


def due_date_for(rule: str, day: int, month: date) -> date | None:
    """Due date in ``month`` (workday rule stays open, M13-02: no holiday calendar released)."""
    first = month_first(month)
    last = month_last(first)
    if rule == "day":
        return first.replace(day=min(day, last.day))
    if rule == "last_day":
        return last
    if rule == "day_next_month":
        nxt = add_months(first, 1)
        return nxt.replace(day=min(day, month_last(nxt).day))
    return None


def previous_day(day: date) -> date:
    return day - timedelta(days=1)
