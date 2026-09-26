"""Letting (M26): rent increase cases, prospects. Vacancies and exposés are derived views."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, text
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


class Listing(IdMixin, TimestampMixin, TenantMixin, Base):
    """Listing for rent or sale (M28-01 stage 2). Handover to FLOWFACT is a placeholder
    field only; no external interface exists until the FLOWFACT documentation is provided
    (rule 0.1.3, docs/plans/M28-makler.md)."""

    __tablename__ = "listing"
    __table_args__ = (
        Index("ix_listing_tenant_status", "tenant_id", "status"),
        Index(
            "ux_listing_tenant_external_uuid",
            "tenant_id",
            "external_uuid",
            unique=True,
            postgresql_where=text("external_uuid IS NOT NULL"),
        ),
    )

    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False, ondelete="CASCADE")
    unit_id: Mapped[uuid.UUID] = _fk("unit.id", nullable=False, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # rental, sale
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    additional_costs: Mapped[Decimal | None] = mapped_column(MONEY)
    deposit: Mapped[Decimal | None] = mapped_column(MONEY)
    available_from: Mapped[date | None] = mapped_column(Date)
    commission_note: Mapped[str | None] = mapped_column(String(200))
    energy_note: Mapped[str | None] = mapped_column(String(200))
    living_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    rooms: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    floor: Mapped[str | None] = mapped_column(String(20))
    # Placeholder for the future FLOWFACT handover (stage 3); no adapter exists yet.
    publication_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_published"
    )
    publication_ref: Mapped[str | None] = mapped_column(String(100))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    # M28-01 stage 3 preparation (FLOW data contract, docs/rules/M28-01.md)
    object_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="wohnung", server_default=text("'wohnung'")
    )
    address_release: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="vollstaendig",
        server_default=text("'vollstaendig'"),
    )
    heating_type: Mapped[str | None] = mapped_column(String(32))
    energy_source: Mapped[str | None] = mapped_column(String(32))
    heating_costs: Mapped[Decimal | None] = mapped_column(MONEY)
    heating_in_additional_costs: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=text("false")
    )
    warm_rent: Mapped[Decimal | None] = mapped_column(MONEY)
    hoa_fee: Mapped[Decimal | None] = mapped_column(MONEY)
    parking_price: Mapped[Decimal | None] = mapped_column(MONEY)
    # String(24): "nicht_erforderlich" has 18 characters (widened in migration 0112).
    energy_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="in_erstellung",
        server_default=text("'in_erstellung'"),
    )
    energy_type: Mapped[str | None] = mapped_column(String(16))
    energy_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    energy_class: Mapped[str | None] = mapped_column(String(4))
    energy_year_of_installation: Mapped[int | None] = mapped_column(sa.Integer)
    energy_valid_until: Mapped[date | None] = mapped_column(Date)
    energy_includes_hot_water: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=text("false")
    )
    # A63: issue date of the certificate and construction year of the building as shown on
    # the certificate; copied from the property on creation, editable per listing.
    energy_issued_on: Mapped[date | None] = mapped_column(Date)
    energy_building_year: Mapped[int | None] = mapped_column(sa.Integer)
    features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    commission_type: Mapped[str | None] = mapped_column(String(16))
    external_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    external_ref: Mapped[str | None] = mapped_column(String(64))
    flowfact_entity_id: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="crm", server_default=text("'crm'")
    )


class FlowImportRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """FLOW import run (M28 stage 4, docs/rules/M28-01.md): one uploaded SQL dump with the
    parsed preview rows. No FLOWFACT call; the rows column holds the preview and, after
    apply, the per-row outcome."""

    __tablename__ = "flow_import_run"

    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="previewed", server_default=text("'previewed'")
    )
    row_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=text("0")
    )
    skipped_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=text("0")
    )
    rows: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
