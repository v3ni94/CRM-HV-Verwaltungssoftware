"""Staging tables of the Immoware24 import assistant (13.1): source files, staged rows, mappings.

Column names of Immoware24 exports are not specified (13.1): every file is mapped by the user,
and mappings are stored as versioned templates per report type.
"""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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
