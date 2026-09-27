"""Messdienstleister module, stage 1 (master prompt "Messdienstleister" sections 2 to 10).

Tenant tables (RLS, ADR 0002). Business identifiers of the providers (customer number, billing
unit number, usage unit number, device number) are strings that keep leading zeros and are never
mixed up (section 5). Secrets of a connection are stored encrypted (``EncryptedText``, section 9)
and never leave the API. Consumption values and billing results are imported as reviewable
external data only (section 11): no posting, no receivable, no change of existing statements.
"""

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
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


class Environment(StrEnum):
    TEST = "test"
    PRODUCTION = "production"


class ConnectionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class ServiceScope(StrEnum):
    HEATING = "heating"
    HOT_WATER = "hot_water"
    COLD_WATER = "cold_water"
    SMOKE_DETECTORS = "smoke_detectors"
    OTHER = "other"


class AssignmentStatus(StrEnum):
    OPEN = "open"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    CONFLICT = "conflict"
    ARCHIVED = "archived"


class AssignmentOrigin(StrEnum):
    MANUAL = "manual"
    IMPORT = "import"
    PROVIDER = "provider"


class OccupancyStatus(StrEnum):
    OCCUPIED = "occupied"
    VACANT = "vacant"
    OWNER_USE = "owner_use"
    UNCLEAR = "unclear"


class DataKind(StrEnum):
    DOCUMENTS = "documents"
    CONSUMPTION = "consumption"
    BILLING_RESULT = "billing_result"
    BILLING_UNIT_DATA = "billing_unit_data"


class SyncStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_PROVIDER = "waiting_provider"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    UNCLEAR = "unclear"


class ClearingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ValueKind(StrEnum):
    ACTUAL = "actual"
    ESTIMATED = "estimated"
    MISSING = "missing"
    CORRECTED = "corrected"


class ReadingType(StrEnum):
    PERIOD_CONSUMPTION = "period_consumption"
    METER_READING = "meter_reading"


class ReviewStatus(StrEnum):
    IMPORTED = "imported"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


def _in(column: str, values: type[StrEnum], name: str) -> CheckConstraint:
    joined = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({joined})", name=name)


def _fk(target: str, *, ondelete: str = "RESTRICT", nullable: bool = False) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class MeteringConnection(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant connection to one provider account (section 4). Several connections per provider
    are allowed (different customer accounts); test and production never share a row."""

    __tablename__ = "metering_connection"
    __table_args__ = (
        _in("environment", Environment, "environment"),
        _in("status", ConnectionStatus, "status"),
        Index("ix_metering_connection_tenant_id_provider_code", "tenant_id", "provider_code"),
    )

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    # Regional contracting company of the provider, if relevant (section 3).
    contracting_company: Mapped[str | None] = mapped_column(String(200))
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # Customer and contract numbers as text (leading zeros preserved).
    customer_references: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Non secret technical configuration (base URL, API family, versions, ...).
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Secrets as an encrypted JSON object {name: value}; only the names are reported.
    secrets: Mapped[str | None] = mapped_column(EncryptedText())
    secret_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Capability matrix per function: {function: {documented_support, adapter_implemented,
    # supported_version, account_release, property_release, last_test_result}} (section 3).
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_test_status: Mapped[str | None] = mapped_column(String(32))
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_detail: Mapped[str | None] = mapped_column(Text)
    # Set after configuration changes: the previous test no longer proves anything (section 4).
    test_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scheduled_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    write_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Last successful sync per data kind: {data_kind: iso timestamp} (kept after later failures).
    last_sync: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MeteringExternalBillingUnit(IdMixin, TimestampMixin, TenantMixin, Base):
    """External Liegenschaft / Abrechnungseinheit of a connection (section 5). The external
    number is unique within connection and environment (the connection carries the environment)."""

    __tablename__ = "metering_external_billing_unit"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connection_id", "external_number"),
        CheckConstraint("length(external_number) > 0", name="external_number_not_empty"),
    )

    connection_id: Mapped[uuid.UUID] = _fk("metering_connection.id")
    external_number: Mapped[str] = mapped_column(String(64), nullable=False)
    external_name: Mapped[str | None] = mapped_column(String(200))
    external_address: Mapped[str | None] = mapped_column(String(400))
    expected_unit_count: Mapped[int | None] = mapped_column(Integer)
    # Set when the same external unit spans several CRM properties (explicit grouping).
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    remote_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class MeteringPropertyAssignment(IdMixin, TimestampMixin, TenantMixin, Base):
    """Assignment of a CRM property to an external billing unit for one service scope and a
    validity range (section 5). Ended assignments are never deleted while data references them;
    a provider change ends the old row and creates a new one."""

    __tablename__ = "metering_property_assignment"
    __table_args__ = (
        _in("service_scope", ServiceScope, "service_scope"),
        _in("status", AssignmentStatus, "status"),
        _in("origin", AssignmentOrigin, "origin"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
        Index("ix_metering_property_assignment_tenant_id_property_id", "tenant_id", "property_id"),
    )

    connection_id: Mapped[uuid.UUID] = _fk("metering_connection.id")
    property_id: Mapped[uuid.UUID] = _fk("property.id")
    external_billing_unit_id: Mapped[uuid.UUID] = _fk("metering_external_billing_unit.id")
    service_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Human confirmation (local) versus technical confirmation by the provider (remote).
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_basis: Mapped[str | None] = mapped_column(Text)
    remote_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cross property external unit: same group id on every member plus explicit unit scope.
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    unit_scope: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    conflict_reason: Mapped[str | None] = mapped_column(Text)
    error_hint: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MeteringUnitAssignment(IdMixin, TimestampMixin, TenantMixin, Base):
    """Internal unit to external Nutzeinheit inside a property assignment (section 7). The
    external unit number is neither a device number nor a tenant name; a change of occupant does
    not change this row. Recipients are contact references, no second user file."""

    __tablename__ = "metering_unit_assignment"
    __table_args__ = (
        _in("occupancy_status", OccupancyStatus, "occupancy_status"),
        _in("status", AssignmentStatus, "status"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
        CheckConstraint("length(external_unit_number) > 0", name="external_unit_number_not_empty"),
        Index("ix_metering_unit_assignment_tenant_id_unit_id", "tenant_id", "unit_id"),
    )

    property_assignment_id: Mapped[uuid.UUID] = _fk("metering_property_assignment.id")
    unit_id: Mapped[uuid.UUID] = _fk("unit.id")
    external_unit_number: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    billing_recipient_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True)
    consumption_info_recipient_contact_id: Mapped[uuid.UUID | None] = _fk(
        "contact.id", nullable=True
    )
    occupancy_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unclear")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # External partner/user id of the provider account, if known (account bound, section 7).
    external_partner_ref: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MeteringSyncJob(IdMixin, TimestampMixin, TenantMixin, Base):
    """Persistent sync order (section 10): manual "Jetzt abrufen" only in stage 1."""

    __tablename__ = "metering_sync_job"
    __table_args__ = (
        _in("data_kind", DataKind, "data_kind"),
        _in("status", SyncStatus, "status"),
        Index("ix_metering_sync_job_tenant_id_connection_id", "tenant_id", "connection_id"),
    )

    connection_id: Mapped[uuid.UUID] = _fk("metering_connection.id")
    property_assignment_id: Mapped[uuid.UUID | None] = _fk(
        "metering_property_assignment.id", nullable=True
    )
    # Scope: {"property_ids": [...], "unit_ids": [...]} as strings.
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    data_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)
    assignment_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    # Per part results: [{"part": str, "status": str, "error": str | None}].
    parts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    error_summary: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last success of this connection and data kind before this job (kept for display).
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MeteringClearingItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """External data that could not be assigned (section 11: protected clearing area)."""

    __tablename__ = "metering_clearing_item"
    __table_args__ = (
        _in("status", ClearingStatus, "status"),
        Index("ix_metering_clearing_item_tenant_id_status", "tenant_id", "status"),
    )

    connection_id: Mapped[uuid.UUID] = _fk("metering_connection.id")
    sync_job_id: Mapped[uuid.UUID | None] = _fk("metering_sync_job.id", nullable=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    property_assignment_id: Mapped[uuid.UUID | None] = _fk(
        "metering_property_assignment.id", nullable=True
    )


class MeteringConsumptionValue(IdMixin, TimestampMixin, TenantMixin, Base):
    """Structured consumption value (section 11). ``value`` is NULL only for ``missing``; a
    missing value is never coerced to zero. Meter readings and period consumption are separate
    rows (``reading_type``), units of measure are never mixed."""

    __tablename__ = "metering_consumption_value"
    __table_args__ = (
        _in("value_kind", ValueKind, "value_kind"),
        _in("reading_type", ReadingType, "reading_type"),
        CheckConstraint(
            "(value_kind = 'missing' AND value IS NULL) "
            "OR (value_kind <> 'missing' AND value IS NOT NULL)",
            name="value_matches_kind",
        ),
        CheckConstraint("period_to >= period_from", name="period_range"),
        UniqueConstraint(
            "tenant_id",
            "property_assignment_id",
            "unit_assignment_id",
            "period_from",
            "period_to",
            "kind",
            "reading_type",
            "source",
            "version",
        ),
    )

    property_assignment_id: Mapped[uuid.UUID] = _fk("metering_property_assignment.id")
    unit_assignment_id: Mapped[uuid.UUID | None] = _fk("metering_unit_assignment.id", nullable=True)
    sync_job_id: Mapped[uuid.UUID | None] = _fk("metering_sync_job.id", nullable=True)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(16), nullable=False)
    reading_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    value_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(128))


class MeteringBillingResult(IdMixin, TimestampMixin, TenantMixin, Base):
    """Imported billing result (section 11): exact decimal amount and currency, versioned,
    reviewable external data. Never posted, never a receivable, never a statement change."""

    __tablename__ = "metering_billing_result"
    __table_args__ = (
        _in("review_status", ReviewStatus, "review_status"),
        CheckConstraint("period_to >= period_from", name="period_range"),
        UniqueConstraint(
            "tenant_id",
            "property_assignment_id",
            "unit_assignment_id",
            "period_from",
            "period_to",
            "external_document_ref",
            "version",
        ),
    )

    property_assignment_id: Mapped[uuid.UUID] = _fk("metering_property_assignment.id")
    unit_assignment_id: Mapped[uuid.UUID | None] = _fk("metering_unit_assignment.id", nullable=True)
    sync_job_id: Mapped[uuid.UUID | None] = _fk("metering_sync_job.id", nullable=True)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    external_document_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="imported")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


METERING_TABLES: tuple[str, ...] = (
    MeteringConnection.__tablename__,
    MeteringExternalBillingUnit.__tablename__,
    MeteringPropertyAssignment.__tablename__,
    MeteringUnitAssignment.__tablename__,
    MeteringSyncJob.__tablename__,
    MeteringClearingItem.__tablename__,
    MeteringConsumptionValue.__tablename__,
    MeteringBillingResult.__tablename__,
)
