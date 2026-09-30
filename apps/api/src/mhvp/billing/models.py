"""Statements with snapshots (6.9.3, A01) for operating costs of rentals (7.6, M17)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.billing.status import StatementStatus
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class StatementKind(StrEnum):
    OPERATING_COSTS = "operating_costs"


class Statement(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "statement"
    __table_args__ = (
        # A05: an interim statement (Sonderzeitraum) only with its stated purpose.
        CheckConstraint("NOT interim OR purpose IS NOT NULL", name="interim_purpose"),
    )

    kind: Mapped[StatementKind] = mapped_column(
        Enum(
            StatementKind,
            name="statement_kind_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    property_id: Mapped[uuid.UUID] = _fk("property.id")
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StatementStatus] = mapped_column(
        Enum(
            StatementStatus, name="statement_status", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
        default=StatementStatus.DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("statement.id", nullable=True)
    # Current snapshot; no FK because the snapshot references the statement (cycle).
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    delivered_at: Mapped[date | None] = mapped_column(Date)
    deadline_exception: Mapped[str | None] = mapped_column(Text)
    # 6.5 operating_cost_statement (M17-04): interim statement with purpose, heating switch and
    # letter settings (texts for Guthaben/Nachzahlung, format, bundled output).
    interim: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    purpose: Mapped[str | None] = mapped_column(Text)
    include_heating: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # M17-01: draft journal entries of the result (Forderung/Gutschrift) created behind G3.
    result_entry_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


DELIVERY_METHODS = ("post", "registered_mail", "hand_delivery", "email", "portal")


class StatementResult(IdMixin, TimestampMixin, TenantMixin, Base):
    """Result per contract (6.5 statement_result, M17-03): document and access per tenant.
    Amounts stay in the snapshot; this row carries delivery and evidence only (A04)."""

    __tablename__ = "statement_result"
    __table_args__ = (
        UniqueConstraint("statement_id", "contract_id", name="uq_statement_result_contract"),
        CheckConstraint(
            "delivery_method IS NULL OR delivery_method IN "
            "('post', 'registered_mail', 'hand_delivery', 'email', 'portal')",
            name="delivery_method",
        ),
        CheckConstraint(
            "delivered_at IS NULL OR (delivery_method IS NOT NULL AND evidence IS NOT NULL)",
            name="delivery_evidence",
        ),
        Index("ix_statement_result_statement_id", "statement_id"),
    )

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    contract_id: Mapped[uuid.UUID] = _fk("contract.id")
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")
    delivery_method: Mapped[str | None] = mapped_column(String(16))
    delivered_at: Mapped[date | None] = mapped_column(Date)
    evidence: Mapped[str | None] = mapped_column(Text)
    evidence_document_id: Mapped[uuid.UUID | None] = _fk(
        "document.id", nullable=True, ondelete="SET NULL"
    )


class StatementInspection(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant request for inspection of the receipts (Belegeinsicht, PÜ11, M17-06) with the
    provision, the redaction note and a received objection. The objection deadline is shown as
    orientation only."""

    __tablename__ = "statement_inspection"
    __table_args__ = (
        CheckConstraint("status IN ('requested', 'provided', 'closed')", name="status"),
        CheckConstraint(
            "provision IS NULL OR provision IN ('electronic', 'copies', 'appointment')",
            name="provision",
        ),
        CheckConstraint(
            "status = 'requested' OR (provision IS NOT NULL AND provided_at IS NOT NULL)",
            name="provided",
        ),
        Index("ix_statement_inspection_statement_id", "statement_id"),
    )

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    contract_id: Mapped[uuid.UUID] = _fk("contract.id")
    requested_at: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", server_default="requested"
    )
    provision: Mapped[str | None] = mapped_column(String(16))
    provided_at: Mapped[date | None] = mapped_column(Date)
    document_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    redaction_note: Mapped[str | None] = mapped_column(Text)
    objection_received_at: Mapped[date | None] = mapped_column(Date)
    objection_text: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class StatementCostItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """A cost position chosen by a person with its contractual basis (A02); never inferred from
    the account name. Heating costs come as external amounts per unit (H01)."""

    __tablename__ = "statement_cost_item"

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id", nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    allocation_key_id: Mapped[uuid.UUID | None] = _fk("allocation_key.id", nullable=True)
    # {unit_id: amount} for external calculations (heating, water); sum must equal amount.
    external_amounts: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    basis: Mapped[str] = mapped_column(Text, nullable=False)  # contract clause / source
    heating: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StatementSnapshot(IdMixin, TenantMixin, Base):
    """Immutable result of a calculation: inputs, keys, rule version, results, hash (6.9.3)."""

    __tablename__ = "statement_snapshot"

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class StatementEvent(IdMixin, TenantMixin, Base):
    __tablename__ = "statement_event"

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class HeatingRuleTableKind(StrEnum):
    CO2_STEPS = "co2_steps"
    DEGREE_DAYS = "degree_days"


class HeatingRuleTable(IdMixin, TimestampMixin, TenantMixin, Base):
    """Configurable tables for the draft heating statement (M17-02): CO2 step model
    (rows ``[{"from_kg_m2": "12", "tenant_percent": 90}, ...]``) and degree days
    (rows ``{"1": "170", ..., "12": "160"}`` in promille, sum 1000). Values carry a source and
    ``review_status``; nothing here is a released legal rule."""

    __tablename__ = "heating_rule_table"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "kind", "valid_from", name="uq_heating_rule_table_kind_valid"
        ),
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    rows: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="zu_pruefen")
    note: Mapped[str | None] = mapped_column(Text)


class StatementHeating(IdMixin, TimestampMixin, TenantMixin, Base):
    """Heating and hot water inputs of one operating cost statement and the last draft result
    (M17-02). ``consumptions`` holds one entry per occupancy key; ``result`` is the JSON
    trace of ``heating_calc.calculate``; ``applied_item_id`` links the fed cost item."""

    __tablename__ = "statement_heating"
    __table_args__ = (
        UniqueConstraint("tenant_id", "statement_id", name="uq_statement_heating_statement"),
    )

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    total_costs: Mapped[Decimal | None] = mapped_column(MONEY)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    co2: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    consumptions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    unit_totals: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    applied_item_id: Mapped[uuid.UUID | None] = _fk(
        "statement_cost_item.id", nullable=True, ondelete="SET NULL"
    )


class ConsumptionInfo(IdMixin, TimestampMixin, TenantMixin, Base):
    """Monthly consumption information per unit (§ 6a HeizkostenV, rule H03, D26). One row per
    tenant, unit and month (``month`` is the first day). ``values`` holds the computed figures
    with their origin, ``data_basis`` the source rows of ``mhvp.metering``, ``missing`` the
    flags of what could not be determined. The snapshot (HTML and the stored PDF document) is
    frozen with the row; a rerun of the month never overwrites it (rule 0.1.7)."""

    __tablename__ = "consumption_info"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_id", "month", name="uq_consumption_info_unit_month"),
        CheckConstraint("extract(day from month) = 1", name="month_first_day"),
        Index("ix_consumption_info_property_month", "tenant_id", "property_id", "month"),
        CheckConstraint(
            "delivered_on IS NULL OR (delivery_channel IN ('post', 'email', 'hand_delivery') "
            "AND delivery_evidence IS NOT NULL)",
            name="delivery",
        ),
    )

    property_id: Mapped[uuid.UUID] = _fk("property.id")
    unit_id: Mapped[uuid.UUID] = _fk("unit.id")
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    data_basis: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    missing: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, default="job", server_default="job"
    )
    snapshot_html: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # D26 substitute process without portal: delivery recorded by a person with evidence.
    delivery_channel: Mapped[str | None] = mapped_column(String(16))
    delivered_on: Mapped[date | None] = mapped_column(Date)
    delivery_evidence: Mapped[str | None] = mapped_column(Text)
    delivery_recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
