"""Deposit settlement drafts (Kautionsabrechnung) and the reference interest rate table.

Operator decision of 26.09.2026 (docs/OPEN_QUESTIONS.md M5-02, rule M5-02): the deposit is
held separately, interest is recorded per year as a movement, and the settlement at contract
end is a draft. The settlement lets the user choose the interest mode:

- ``individual``: interest amounts per year entered by the user (for example from the bank
  statement of the deposit account);
- ``reference_rate``: interest computed per year from the tenant maintained reference rate
  table ("Referenzzinssatz je Jahr", ``deposit_interest_reference_rate``), day exact on the
  deposit balance;
- ``deposit_rates``: interest computed per year from the rate history of the deposit itself
  (``deposit_interest_rate``, rate with valid from date per deposit account, B15);
- ``none``: no interest.

All arithmetic uses ``Decimal`` (rule 6.9.8, no float). The settlement is a record, never a
posting or a payment: nothing here creates receivables or payments (G1, G3 stay closed).

Reference rate computation (documented in docs/rules/M5-02-kautionsabrechnung.md):

- The balance basis is the sum of recorded payments minus offsets and payouts by date.
  Recorded interest movements are shown for reconciliation but are neither part of the basis
  nor added again (no compounding inside the settlement; recording the computed interest as a
  yearly movement is the user's step).
- A balance counts from the day of the movement (inclusive) until the day before the next
  movement; the last interval ends on the settlement date (inclusive).
- Per calendar year: sum over intervals of ``balance * rate / 100 * days / days_in_year``
  with 365 or 366 days, then rounded to the cent (ROUND_HALF_UP) once per year.
- A year without a rate in the table refuses the computation (no invented rate).
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from itertools import pairwise
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)
RATE = Numeric(8, 5)  # percent per year, e.g. 0.50000
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class DepositInterestMode(StrEnum):
    INDIVIDUAL = "individual"
    REFERENCE_RATE = "reference_rate"
    # B15: rate history per deposit account (``deposit_interest_rate``), see rule B15.
    DEPOSIT_RATES = "deposit_rates"
    NONE = "none"


class DepositSettlementStatus(StrEnum):
    DRAFT = "draft"
    RELEASED = "released"  # only reachable behind release gate G3


class DepositInterestReferenceRate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Reference interest rate per calendar year, maintained by the tenant (percent)."""

    __tablename__ = "deposit_interest_reference_rate"
    __table_args__ = (UniqueConstraint("tenant_id", "year"),)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class DepositInterestRate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Interest rate (percent per year) of one deposit account from ``valid_from`` on (B15).

    The rate in force on a day is the one with the latest ``valid_from`` on or before that day.
    No rate is fetched or invented; the operator maintains the history (bank confirmation)."""

    __tablename__ = "deposit_interest_rate"
    __table_args__ = (UniqueConstraint("deposit_id", "valid_from"),)

    deposit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit.id", ondelete="CASCADE"), nullable=False
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class DepositInterestDraft(IdMixin, TimestampMixin, TenantMixin, Base):
    """Yearly interest credit as a draft (B15). ``confirmed`` creates a deposit movement of kind
    interest (a record, never a posting or payment); ``discarded`` drafts stay for the trail."""

    __tablename__ = "deposit_interest_draft"
    __table_args__ = (
        UniqueConstraint("deposit_id", "year"),
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'discarded')", name="deposit_interest_draft_status"
        ),
    )

    deposit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[Decimal | None] = mapped_column(RATE)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    movement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_movement.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)


class DepositSettlement(IdMixin, TimestampMixin, TenantMixin, Base):
    """Settlement draft of one deposit at contract end (record, no posting, no payment)."""

    __tablename__ = "deposit_settlement"

    deposit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit.id", ondelete="CASCADE"), nullable=False, index=True
    )
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    interest_mode: Mapped[DepositInterestMode] = mapped_column(
        Enum(
            DepositInterestMode,
            name="deposit_interest_mode",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    status: Mapped[DepositSettlementStatus] = mapped_column(
        Enum(
            DepositSettlementStatus,
            name="deposit_settlement_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=DepositSettlementStatus.DRAFT,
    )
    # [{"year": 2025, "rate": "0.50000" | null, "days": 365, "amount": "6.00"}]
    interest_years: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    # [{"label": "Schaden Bad", "amount": "120.00"}]
    deductions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    principal_paid: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    offsets_recorded: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payouts_recorded: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interest_recorded: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interest_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    deductions_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payout_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    number: Mapped[str | None] = mapped_column(String(40))
    # Generated settlement letter (M5-02 follow up, PDF): set once the document is created.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )


# Pure computation ------------------------------------------------------------------------


class SettlementError(ValueError):
    """Domain refusal with a German detail; the router maps it to 422."""


@dataclass(frozen=True)
class BalanceChange:
    """Signed change of the deposit balance basis on a day (payment +, offset/payout -)."""

    on: date
    amount: Decimal


@dataclass(frozen=True)
class YearInterest:
    year: int
    rate: Decimal | None
    days: int
    amount: Decimal

    def as_json(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "rate": None if self.rate is None else str(self.rate),
            "days": self.days,
            "amount": str(self.amount),
        }


@dataclass(frozen=True)
class Deduction:
    label: str
    amount: Decimal

    def as_json(self) -> dict[str, Any]:
        return {"label": self.label, "amount": str(self.amount)}


@dataclass(frozen=True)
class SettlementResult:
    settlement_date: date
    interest_mode: DepositInterestMode
    principal_paid: Decimal
    offsets_recorded: Decimal
    payouts_recorded: Decimal
    interest_recorded: Decimal
    years: list[YearInterest]
    deductions: list[Deduction]

    @property
    def balance_before_interest(self) -> Decimal:
        return self.principal_paid - self.offsets_recorded - self.payouts_recorded

    @property
    def interest_total(self) -> Decimal:
        return sum((y.amount for y in self.years), ZERO)

    @property
    def deductions_total(self) -> Decimal:
        return sum((d.amount for d in self.deductions), ZERO)

    @property
    def payout_amount(self) -> Decimal:
        return self.balance_before_interest + self.interest_total - self.deductions_total


def days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def balance_intervals(
    changes: list[BalanceChange], until: date
) -> list[tuple[date, date, Decimal]]:
    """Half open intervals ``(start, end_exclusive, balance)`` from the first change until
    ``until`` inclusive. Changes on the same day are merged."""
    by_day: dict[date, Decimal] = {}
    for change in changes:
        by_day[change.on] = by_day.get(change.on, ZERO) + change.amount
    days = sorted(d for d in by_day if d <= until)
    intervals: list[tuple[date, date, Decimal]] = []
    balance = ZERO
    for index, day in enumerate(days):
        balance += by_day[day]
        end = days[index + 1] if index + 1 < len(days) else until + timedelta(days=1)
        if end > day:
            intervals.append((day, end, balance))
    return intervals


def year_span(changes: list[BalanceChange], until: date) -> list[int]:
    """Calendar years from the first balance change to the settlement date."""
    starts = [c.on for c in changes if c.on <= until]
    if not starts:
        return []
    return list(range(min(starts).year, until.year + 1))


def interest_by_reference_rate(
    changes: list[BalanceChange], rates: dict[int, Decimal], until: date
) -> list[YearInterest]:
    """Day exact interest per calendar year on the balance basis (see module docstring)."""
    years = year_span(changes, until)
    missing = [str(y) for y in years if y not in rates]
    if missing:
        raise SettlementError(
            "Für folgende Jahre ist kein Referenzzinssatz hinterlegt: " + ", ".join(missing)
        )
    intervals = balance_intervals(changes, until)
    result: list[YearInterest] = []
    for year in years:
        year_start = date(year, 1, 1)
        year_end_exclusive = date(year + 1, 1, 1)
        rate = rates[year]
        basis = days_in_year(year)
        total = Decimal(0)
        counted_days = 0
        for start, end, balance in intervals:
            lo = max(start, year_start)
            hi = min(end, year_end_exclusive)
            days = (hi - lo).days
            if days <= 0:
                continue
            counted_days += days
            total += balance * rate / Decimal(100) * Decimal(days) / Decimal(basis)
        result.append(
            YearInterest(
                year=year, rate=rate, days=counted_days, amount=total.quantize(CENT, ROUND_HALF_UP)
            )
        )
    return result


def interest_by_rate_history(
    changes: list[BalanceChange],
    history: list[tuple[date, Decimal]],
    until: date,
    years: list[int] | None = None,
) -> list[YearInterest]:
    """Day exact interest per calendar year with the rate history of one deposit (B15).

    Same basis and rounding as ``interest_by_reference_rate``; the rate of a day is the latest
    entry of ``history`` with ``valid_from`` on or before the day. An interval without a rate
    (before the first entry) refuses the computation, no rate is assumed."""
    steps = sorted(history)
    span = year_span(changes, until)
    selected = span if years is None else [y for y in years if y in span]
    intervals = balance_intervals(changes, until)
    result: list[YearInterest] = []
    for year in selected:
        year_start = date(year, 1, 1)
        year_end_exclusive = date(year + 1, 1, 1)
        basis = days_in_year(year)
        total = Decimal(0)
        counted_days = 0
        used: set[Decimal] = set()
        for start, end, balance in intervals:
            lo = max(start, year_start)
            hi = min(end, year_end_exclusive)
            if hi <= lo:
                continue
            cuts = sorted({lo, hi} | {d for d, _ in steps if lo < d < hi})
            for seg_start, seg_end in pairwise(cuts):
                rate = next((r for d, r in reversed(steps) if d <= seg_start), None)
                if rate is None:
                    raise SettlementError(
                        f"Für die Kaution ist ab {seg_start.strftime('%d.%m.%Y')} kein Zinssatz "
                        "hinterlegt."
                    )
                days = (seg_end - seg_start).days
                counted_days += days
                used.add(rate)
                total += balance * rate / Decimal(100) * Decimal(days) / Decimal(basis)
        result.append(
            YearInterest(
                year=year,
                rate=next(iter(used)) if len(used) == 1 else None,
                days=counted_days,
                amount=total.quantize(CENT, ROUND_HALF_UP),
            )
        )
    return result


def interest_individual(
    changes: list[BalanceChange], entered: dict[int, Decimal], until: date
) -> list[YearInterest]:
    """Interest per year as entered; years outside the deposit span are refused."""
    years = year_span(changes, until)
    outside = [str(y) for y in entered if y not in years]
    if outside:
        raise SettlementError(
            "Zinsen für Jahre außerhalb der Kautionslaufzeit: " + ", ".join(sorted(outside))
        )
    intervals = balance_intervals(changes, until)
    result: list[YearInterest] = []
    for year in years:
        counted = 0
        for start, end, _ in intervals:
            lo = max(start, date(year, 1, 1))
            hi = min(end, date(year + 1, 1, 1))
            counted += max((hi - lo).days, 0)
        amount = entered.get(year, ZERO).quantize(CENT, ROUND_HALF_UP)
        result.append(YearInterest(year=year, rate=None, days=counted, amount=amount))
    return result


def compute_settlement(
    *,
    settlement_date: date,
    interest_mode: DepositInterestMode,
    payments: list[tuple[date, Decimal]],
    offsets: list[tuple[date, Decimal]],
    payouts: list[tuple[date, Decimal]],
    interest_recorded: Decimal,
    deductions: list[Deduction],
    rates: dict[int, Decimal] | None = None,
    entered_interest: dict[int, Decimal] | None = None,
    rate_history: list[tuple[date, Decimal]] | None = None,
) -> SettlementResult:
    """Build the settlement result from recorded movements and the chosen interest mode."""
    if not payments:
        raise SettlementError("Für die Kaution ist keine Einzahlung erfasst.")
    latest = max(d for d, _ in payments + offsets + payouts)
    if latest > settlement_date:
        raise SettlementError("Es gibt Kautionsbewegungen nach dem Abrechnungsdatum.")
    changes = (
        [BalanceChange(d, a) for d, a in payments]
        + [BalanceChange(d, -a) for d, a in offsets]
        + [BalanceChange(d, -a) for d, a in payouts]
    )
    if interest_mode is DepositInterestMode.REFERENCE_RATE:
        years = interest_by_reference_rate(changes, rates or {}, settlement_date)
    elif interest_mode is DepositInterestMode.DEPOSIT_RATES:
        if not rate_history:
            raise SettlementError("Für die Kaution ist kein Zinssatz hinterlegt.")
        years = interest_by_rate_history(changes, rate_history, settlement_date)
    elif interest_mode is DepositInterestMode.INDIVIDUAL:
        years = interest_individual(changes, entered_interest or {}, settlement_date)
    else:
        years = []
    for deduction in deductions:
        if deduction.amount <= ZERO:
            raise SettlementError("Ein Einbehalt braucht einen positiven Betrag.")
    result = SettlementResult(
        settlement_date=settlement_date,
        interest_mode=interest_mode,
        principal_paid=sum((a for _, a in payments), ZERO),
        offsets_recorded=sum((a for _, a in offsets), ZERO),
        payouts_recorded=sum((a for _, a in payouts), ZERO),
        interest_recorded=interest_recorded,
        years=years,
        deductions=deductions,
    )
    if result.payout_amount < ZERO:
        raise SettlementError(
            "Die Einbehalte übersteigen das Kautionsguthaben. Eine Forderung gegen den Mieter "
            "ist nicht Teil des Entwurfs."
        )
    return result
