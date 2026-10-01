"""Staging tables of the Immoware24 import assistant (13.1): source files, staged rows, mappings.

Column names of Immoware24 exports are not specified (13.1): every file is mapped by the user,
and mappings are stored as versioned templates per report type.
"""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ReportType(StrEnum):
    PROPERTIES = "properties"  # Objektliste
    UNITS = "units"  # Belegungsliste / Einheiten
    CONTACTS = "contacts"  # Adressbuch
    TENANCIES = "tenancies"  # Mietverträge
    OWNERSHIPS = "ownerships"  # Eigentümerverträge
    PAYMENTS = "payments"  # Liste vereinbarter Zahlungen
    JOURNAL = "journal"  # staged only until the ledger exists (M10)
    BANK_TRANSACTIONS = "bank_transactions"  # staged only until M11
    # Welle 3 (M8-02 to M8-07): reports with target fields and their own apply handler
    # (``mhvp.imports.w3_reports``); nothing of them posts or collects money.
    SEPA_OVERVIEW = "sepa_overview"  # SEPA-Übersicht je Objekt (Mandate, Zahlungsplan)
    CHART_OF_ACCOUNTS = "chart_of_accounts"  # Konten-Export je Objekt
    BANK_HISTORY = "bank_history"  # historische Bankumsätze mit Journalzuordnung
    DOCUMENT_INDEX = "document_index"  # DMS-Dokumente mit Objekt- und Vertragsbezug
    TICKET_HISTORY = "ticket_history"  # historische Tickets, nur lesend
    OPEN_ITEMS = "open_items"  # offene Posten, Guthaben, Kautionen, Rücklagen, Darlehen


class FileStatus(StrEnum):
    UPLOADED = "uploaded"
    MAPPED = "mapped"
    VALIDATED = "validated"
    APPLIED = "applied"


class RowStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    UNCHANGED = "unchanged"  # already present with the same values
    CONFLICT = "conflict"  # present with different values; never overwritten
    CREATED = "created"
    STAGED_ONLY = "staged_only"


class ImportMapping(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "import_mapping"
    __table_args__ = (UniqueConstraint("tenant_id", "report_type", "name", "version"),)

    report_type: Mapped[ReportType] = mapped_column(
        _enum(ReportType, "import_report_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # target field -> source column header
    columns: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    # target field -> {source value -> platform value}, e.g. management types
    value_maps: Mapped[dict[str, dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ImportSourceFile(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "import_source_file"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="RESTRICT"), nullable=False
    )
    report_type: Mapped[ReportType] = mapped_column(
        _enum(ReportType, "import_report_type"), nullable=False
    )
    sheet: Mapped[str | None] = mapped_column(String(100))
    header_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    headers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mapping_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_mapping.id", ondelete="RESTRICT")
    )
    status: Mapped[FileStatus] = mapped_column(
        _enum(FileStatus, "import_file_status"), nullable=False, default=FileStatus.UPLOADED
    )
    import_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_run.id", ondelete="RESTRICT")
    )
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class StagingRow(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "import_staging_row"
    __table_args__ = (UniqueConstraint("tenant_id", "source_file_id", "row_number"),)

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_source_file.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[RowStatus] = mapped_column(
        _enum(RowStatus, "import_row_status"), nullable=False, default=RowStatus.PENDING
    )
    errors: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    entity_type: Mapped[str | None] = mapped_column(String(63))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FullRunStatus(StrEnum):
    PREVIEW = "preview"  # dry run, nothing written (not stored)
    APPLIED = "applied"  # import written and reconciled
    RECONCILED = "reconciled"  # reconciliation only, nothing written


class ImportFullRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """One full import or reconciliation of the Immoware24 exports (M8-01, M8-02, V9).

    ``cutoff_date`` marks the migration cut-off the files were exported for; ``files`` keeps
    name, kind, SHA-256 and row count of every upload (proof of what was compared);
    ``report`` holds the per entity target/actual comparison with the difference list;
    ``opening_balances`` holds the balance proposals per contract as a draft only (G1 closed,
    never posted). Repeating the run with the same files updates nothing twice: the keys are
    the Immoware24 object number, unit number and contact id."""

    __tablename__ = "import_full_run"
    __table_args__ = (Index("ix_import_full_run_tenant_created", "tenant_id", "created_at"),)

    status: Mapped[FullRunStatus] = mapped_column(
        _enum(FullRunStatus, "import_full_run_status"), nullable=False
    )
    cutoff_date: Mapped[Any] = mapped_column(Date, nullable=False)
    files: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    report: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    opening_balances: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    differences: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    import_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_run.id", ondelete="SET NULL")
    )


class ImportExternalKey(IdMixin, TimestampMixin, TenantMixin, Base):
    """Key of a source system for a platform record the full import created or matched
    (M8-01): for example the Immoware24 contract number of a contract. A repeated import
    finds the record by this key and creates nothing twice; the record itself carries no
    column for it (``mhvp.imports.vollimport_vertraege``)."""

    __tablename__ = "import_external_key"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_system", "entity_type", "external_key"),
        Index("ix_import_external_key_entity", "tenant_id", "entity_type", "entity_id"),
    )

    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    external_key: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
