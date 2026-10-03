"""Read only history of the switch from Immoware24 (13.1, M8-04, M8-06, M8-07).

Three tables, all per tenant (RLS), none of them part of the live ledger, the live bank
workflow or the live ticket system:

* ``migrated_bank_link``: assignment of a historical ``bank_transaction`` (status ignored, no
  posting) to the ``migrated_journal_entry`` of the Immoware24 journal it was booked in.
* ``migrated_ticket``: historical ticket of the old system, shown read only.
* ``migrated_open_item``: one open item, credit, deposit, reserve, loan or special levy of the
  cut off date with original due date and partial payments. Single items next to the opening
  balance sums (``migration_opening_balance``); never an ``open_item`` of the live ledger, so
  nothing is dunned, collected or posted (G1 closed).
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)
SOURCE = "immoware24"


class OpenItemHistoryKind(StrEnum):
    RECEIVABLE = "receivable"  # Forderung (offener Posten, auch teilbezahlt)
    CREDIT = "credit"  # Guthaben
    DEPOSIT = "deposit"  # gesondert geführte Kaution
    RESERVE = "reserve"  # Rücklagenstand
    LOAN = "loan"  # Darlehensstand
    SPECIAL_LEVY = "special_levy"  # Sonderumlage


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class MigratedBankLink(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migrated_bank_link"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "bank_transaction_id", name="uq_migrated_bank_link_tenant_id"
        ),
    )

    bank_transaction_id: Mapped[uuid.UUID] = _fk(
        "bank_transaction.id", nullable=False, ondelete="CASCADE"
    )
    journal_entry_id: Mapped[uuid.UUID | None] = _fk(
        "migrated_journal_entry.id", ondelete="SET NULL"
    )
    # Identifier of the journal entry as the bank export names it; kept when the journal of
    # that ledger is not imported yet, so a repeated run can complete the link.
    source_entry_id: Mapped[str | None] = mapped_column(String(100))
    source_file_id: Mapped[uuid.UUID | None] = _fk("import_source_file.id", ondelete="SET NULL")
    row_number: Mapped[int | None] = mapped_column(Integer)


class MigratedTicket(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migrated_ticket"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source", "source_ticket_id", name="uq_migrated_ticket_tenant_id"
        ),
        Index("ix_migrated_ticket_property", "tenant_id", "property_id", "created_on"),
    )

    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=SOURCE, server_default=SOURCE
    )
    source_ticket_id: Mapped[str] = mapped_column(String(100), nullable=False)
    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False, ondelete="CASCADE")
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", ondelete="SET NULL")
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", ondelete="SET NULL")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status_text: Mapped[str | None] = mapped_column(String(100))
    created_on: Mapped[date] = mapped_column(Date, nullable=False)
    closed_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    source_file_id: Mapped[uuid.UUID | None] = _fk("import_source_file.id", ondelete="SET NULL")
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )


class MigratedOpenItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migrated_open_item"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "ledger_id",
            "source",
            "kind",
            "source_item_id",
            name="uq_migrated_open_item_tenant_id",
        ),
        CheckConstraint("paid_amount >= 0", name="paid_non_negative"),
        CheckConstraint(
            "kind IN ('receivable','credit','deposit','reserve','loan','special_levy')",
            name="kind_values",
        ),
        Index("ix_migrated_open_item_ledger", "tenant_id", "ledger_id", "kind"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False, ondelete="CASCADE")
    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=SOURCE, server_default=SOURCE
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False, ondelete="CASCADE")
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", ondelete="SET NULL")
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", ondelete="SET NULL")
    original_due_date: Mapped[date | None] = mapped_column(Date)
    original_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal(0), server_default=sql_text("0")
    )
    open_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    # Resolution reference (Beschlussversion) of a special levy as the export names it.
    resolution_ref: Mapped[str | None] = mapped_column(String(200))
    cutoff_date: Mapped[date | None] = mapped_column(Date)
    source_file_id: Mapped[uuid.UUID | None] = _fk("import_source_file.id", ondelete="SET NULL")


# GAJ-501 (AM09, migration 0450): historical statements and resolutions of the old system.
# Filed as evidence and checked, never posted, never sent, never a live statement or a live
# resolution of the platform (G3, G4 closed). Versions are kept side by side.

STATEMENT_KINDS = (
    "hoa_annual",  # WEG Jahresabrechnung
    "hoa_budget",  # WEG Wirtschaftsplan
    "operating_costs",  # Betriebskostenabrechnung Miete
    "heating_costs",  # Heizkostenabrechnung
    "other",
)
RESOLUTION_RESULTS = ("accepted", "rejected", "postponed", "unknown")
RESOLUTION_FORMS = ("meeting", "circular", "unknown")


class MigratedStatement(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migrated_statement"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "property_id",
            "kind",
            "period_start",
            "period_end",
            "unit_number",
            "version",
            name="uq_migrated_statement_tenant_id",
        ),
        CheckConstraint("period_end >= period_start", name="period"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "kind IN ('hoa_annual', 'hoa_budget', 'operating_costs', 'heating_costs', 'other')",
            name="kind",
        ),
        Index("ix_migrated_statement_property", "tenant_id", "property_id", "period_end"),
    )

    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=SOURCE, server_default=SOURCE
    )
    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=sql_text("1")
    )
    # Empty string: statement of the whole property (keeps the unique key total).
    unit_number: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", server_default=""
    )
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", ondelete="SET NULL")
    recipient: Mapped[str | None] = mapped_column(String(300))
    # Result as the source states it (positive: back payment, negative: credit); information
    # only, no receivable is derived from it.
    result_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    sent_on: Mapped[date | None] = mapped_column(Date)
    resolution_ref: Mapped[str | None] = mapped_column(String(200))
    document_ref: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)
    source_file_id: Mapped[uuid.UUID | None] = _fk("import_source_file.id", ondelete="SET NULL")
    row_number: Mapped[int | None] = mapped_column(Integer)


class MigratedResolution(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migrated_resolution"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "property_id",
            "resolved_on",
            "item_number",
            name="uq_migrated_resolution_tenant_id",
        ),
        CheckConstraint(
            "result IN ('accepted', 'rejected', 'postponed', 'unknown')",
            name="result",
        ),
        CheckConstraint("form IN ('meeting', 'circular', 'unknown')", name="form"),
        Index("ix_migrated_resolution_property", "tenant_id", "property_id", "resolved_on"),
    )

    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=SOURCE, server_default=SOURCE
    )
    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False, ondelete="CASCADE")
    resolved_on: Mapped[date] = mapped_column(Date, nullable=False)
    item_number: Mapped[str] = mapped_column(String(50), nullable=False)  # TOP
    reference: Mapped[str | None] = mapped_column(String(200))  # Beschlussnummer der Sammlung
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    wording: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", server_default="unknown"
    )
    form: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", server_default="unknown"
    )
    note: Mapped[str | None] = mapped_column(Text)
    source_file_id: Mapped[uuid.UUID | None] = _fk("import_source_file.id", ondelete="SET NULL")
    row_number: Mapped[int | None] = mapped_column(Integer)
