"""Letting (M26): rent increase cases, prospects. Vacancies and exposés are derived views."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)
RATE = Numeric(20, 8)


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class RentIncreaseCase(IdMixin, TimestampMixin, TenantMixin, Base):
    """Rent increase process (6.3 rent_increase_case). Legal values (cap, comparison rent,
    effective date) are entered with their source; the system only computes (M26-01)."""

    __tablename__ = "rent_increase_case"

    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    basis: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # mietspiegel, comparison, modernization, index, graduated
    current_rent: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    target_rent: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reference_rent: Mapped[Decimal | None] = mapped_column(MONEY)
    cap_limit_percent: Mapped[Decimal | None] = mapped_column(RATE)
    comparison_rent_per_sqm: Mapped[Decimal | None] = mapped_column(RATE)
    living_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    source_note: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    earliest_effective_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    check: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    legal_review_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    new_payment_id: Mapped[uuid.UUID | None] = _fk("contract_payment.id")
    # Justification (M26-01): mietspiegel, gutachten, vergleichswohnungen
    justification: Mapped[str | None] = mapped_column(String(24))
    rent_index_name: Mapped[str | None] = mapped_column(String(300))
    rent_index_date: Mapped[date | None] = mapped_column(Date)
    expert_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    comparison_flats: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    received_on: Mapped[date | None] = mapped_column(Date)  # Zugang beim Mieter


class Prospect(IdMixin, TimestampMixin, TenantMixin, Base):
    """Prospective tenant for a unit; personal data with purpose and deletion date."""

    __tablename__ = "prospect"

    unit_id: Mapped[uuid.UUID] = _fk("unit.id", nullable=False, ondelete="CASCADE")
    contact_id: Mapped[uuid.UUID] = _fk("contact.id", nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    viewing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    delete_after: Mapped[date] = mapped_column(Date, nullable=False)
