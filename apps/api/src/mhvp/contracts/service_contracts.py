"""Service provider contracts (M9-06, A41 Fristenliste): term, notice period and automatic
renewal of contracts with service providers (Hausmeister, Wartung, Reinigung, ...).

The computed dates (next possible contract end, latest notice date) are orientation only and
must be checked against the contract document; they are no legal deadline calculation
(M1-09). Rules of the orientation calculation:

- Notice periods in months are counted back from the contract end calendar month wise; when the
  contract end is the last day of a month, the notice date is the last day of the target month
  (end 30.06., three months, notice date 31.03.). Otherwise the day is clamped to the month end.
- Without an agreed end (``ends_at`` empty) the contract runs open ended; the next possible end
  is today plus the notice period and there is no fixed notice date to track.
- With automatic renewal the end moves by ``auto_renewal_months`` as long as the notice date of
  the current end lies before the reference day.
- A cancelled contract (``cancelled_at``) ends at the first end whose notice date is not before
  the cancellation day; there is no further notice date.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

NOTICE_UNITS = ("days", "months")
MAX_RENEWALS = 1200


class ServiceContract(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "service_contract"
    __table_args__ = (
        Index("ix_service_contract_provider", "tenant_id", "provider_contact_id"),
        Index("ix_service_contract_property", "tenant_id", "property_id"),
        CheckConstraint("notice_period_unit IN ('days', 'months')", name="notice_unit"),
        CheckConstraint("notice_period_days >= 0", name="notice_period"),
        CheckConstraint(
            "auto_renewal_months IS NULL OR auto_renewal_months > 0",
            name="renewal",
        ),
        CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="term"),
    )

    provider_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="RESTRICT"), nullable=False
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    starts_at: Mapped[date] = mapped_column(Date, nullable=False)
    ends_at: Mapped[date | None] = mapped_column(Date)
    # Amount of the notice period; the unit says whether it counts days or months.
    notice_period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    notice_period_unit: Mapped[str] = mapped_column(
        String(8), nullable=False, default="months", server_default="months"
    )
    auto_renewal_months: Mapped[int | None] = mapped_column(Integer)
    cancelled_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


# Orientation calculation ---------------------------------------------------------------


def _is_month_end(day: date) -> bool:
    return day.day == calendar.monthrange(day.year, day.month)[1]


def add_months(day: date, months: int, *, keep_month_end: bool | None = None) -> date:
    """Shift by whole months; a month end stays a month end (``keep_month_end`` default)."""
    keep = _is_month_end(day) if keep_month_end is None else keep_month_end
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last if keep else min(day.day, last))


def notice_date_for(end: date, amount: int, unit: str) -> date:
    """Latest day on which the notice must be received for the given contract end."""
    if unit == "months":
        return add_months(end, -amount)
    return end - timedelta(days=amount)


@dataclass(frozen=True)
class ContractTerms:
    next_end: date | None
    notice_deadline: date | None
    status: str  # running | open_ended | cancelled | expired


def compute_terms(
    *,
    starts_at: date,
    ends_at: date | None,
    notice_amount: int,
    notice_unit: str,
    auto_renewal_months: int | None,
    cancelled_at: date | None,
    today: date,
) -> ContractTerms:
    """Next possible contract end and latest notice date seen from ``today`` (orientation)."""
    if ends_at is None:
        if cancelled_at is not None:
            base = max(cancelled_at, starts_at)
            end = (
                add_months(base, notice_amount, keep_month_end=False)
                if notice_unit == "months"
                else base + timedelta(days=notice_amount)
            )
            return ContractTerms(end, None, "cancelled" if end >= today else "expired")
        base = max(today, starts_at)
        end = (
            add_months(base, notice_amount, keep_month_end=False)
            if notice_unit == "months"
            else base + timedelta(days=notice_amount)
        )
        return ContractTerms(end, None, "open_ended")

    reference = cancelled_at if cancelled_at is not None else today
    end = ends_at
    keep = _is_month_end(ends_at)
    renewals = 0
    while notice_date_for(end, notice_amount, notice_unit) < reference and auto_renewal_months:
        renewals += 1
        if renewals > MAX_RENEWALS:
            break
        end = add_months(end, auto_renewal_months, keep_month_end=keep)
    if cancelled_at is not None:
        return ContractTerms(end, None, "cancelled" if end >= today else "expired")
    if end < today:
        return ContractTerms(None, None, "expired")
    deadline = notice_date_for(end, notice_amount, notice_unit)
    return ContractTerms(end, deadline if deadline >= today else None, "running")


def terms_of(contract: ServiceContract, today: date) -> ContractTerms:
    return compute_terms(
        starts_at=contract.starts_at,
        ends_at=contract.ends_at,
        notice_amount=contract.notice_period_days,
        notice_unit=contract.notice_period_unit,
        auto_renewal_months=contract.auto_renewal_months,
        cancelled_at=contract.cancelled_at,
        today=today,
    )


__all__ = [
    "NOTICE_UNITS",
    "ContractTerms",
    "ServiceContract",
    "add_months",
    "compute_terms",
    "notice_date_for",
    "terms_of",
]
