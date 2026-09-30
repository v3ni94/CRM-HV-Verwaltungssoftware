"""Migration journal and opening balances of the switch from Immoware24 (6.9.10, D11, M8-03).

Four tables, all per tenant (RLS) and per ledger (legal entity, E01):

* ``migrated_journal_entry`` and ``migrated_journal_line``: the rows of the Immoware24 journal
  export with their original identifiers. They are a readable prior period, never part of
  the live journal: nothing here gets a journal number, an open item or a posting.
* ``migration_opening_balance`` with ``migration_opening_balance_line``: the balances as of
  the cut off date (balance sheet accounts, open items per debtor and creditor, bank
  balances, reserve). Entered by import or form by one person, released by a second person,
  posted as one ``EntrySource.migration`` journal entry only after the release and only
  into a ledger whose cut off date is set.
* ``migration_reconciliation_report``: the zero difference check per property with the
  stored report document.
* ``migration_switch_request``: the request to switch the leading system of a ledger to the
  platform, decided by a second person, refused while G1 is closed.
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
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)
SOURCE_IMMOWARE24 = "immoware24"


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class OpeningBalanceStatus(StrEnum):
    DRAFT = "draft"
    RELEASED = "released"
    POSTED = "posted"


class OpeningBalanceKind(StrEnum):
    """What a balance line stands for; decides the reconciliation metric."""

    ACCOUNT = "account"  # balance sheet account (cash, loan, transit, tax, technical)
    DEBTOR = "debtor"  # open item of a debtor (receivable, debit)
    CREDITOR = "creditor"  # open item of a creditor (payable, credit)
    BANK = "bank"  # bank account balance
    RESERVE = "reserve"  # reserve (Erhaltungsrücklage), credit balance


class SwitchRequestStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"


class MigratedJournalEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    """One journal entry of the Immoware24 export (6.9.10). ``source_entry_id`` is the
    original identifier; a second import of the same identifier updates nothing."""

    __tablename__ = "migrated_journal_entry"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "ledger_id",
            "source",
            "source_entry_id",
            name="uq_migrated_journal_entry_tenant_id",
        ),
        Index("ix_migrated_journal_entry_ledger_date", "tenant_id", "ledger_id", "booking_date"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=SOURCE_IMMOWARE24, server_default=SOURCE_IMMOWARE24
    )
    source_entry_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_file_id: Mapped[uuid.UUID | None] = _fk(
        "import_source_file.id", nullable=True, ondelete="SET NULL"
    )
    row_numbers: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default=sql_text("''")
    )
    reference: Mapped[str | None] = mapped_column(String(100))
    # Document reference of the source (Belegnummer or file reference, 6.9.10 Belegverweise).
    document_ref: Mapped[str | None] = mapped_column(String(200))
    # Complete calendar year of the takeover confirmed by the importing person (6.9.10).
    year_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    # Reconciliation marker (Überleitungskennzeichen): set when a zero difference report
    # covered this entry's ledger and year.
    reconciled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    reconciled_report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    debit_total: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default=sql_text("0")
    )
    credit_total: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default=sql_text("0")
    )


class MigratedJournalLine(IdMixin, TenantMixin, Base):
    __tablename__ = "migrated_journal_line"
    __table_args__ = (
        UniqueConstraint("entry_id", "line_no", name="uq_migrated_journal_line_entry_id"),
        CheckConstraint("debit >= 0 AND credit >= 0", name="non_negative"),
        Index("ix_migrated_journal_line_account", "tenant_id", "account_number"),
    )

    entry_id: Mapped[uuid.UUID] = _fk("migrated_journal_entry.id", ondelete="CASCADE")
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # Account number as exported; the platform account is matched by number, never invented.
    account_number: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[uuid.UUID | None] = _fk(
        "ledger_account.id", nullable=True, ondelete="SET NULL"
    )
    debit: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default=sql_text("0")
    )
    credit: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default=sql_text("0")
    )
    text: Mapped[str | None] = mapped_column(String(500))
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )


class MigrationOpeningBalance(IdMixin, TimestampMixin, TenantMixin, Base):
    """Opening balances of one ledger as of its cut off date (one set per ledger and date)."""

    __tablename__ = "migration_opening_balance"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "ledger_id", "cutoff_date", name="uq_migration_opening_balance_tenant_id"
        ),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    cutoff_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=OpeningBalanceStatus.DRAFT.value,
        server_default=sql_text("'draft'"),
    )
    entered_via: Mapped[str] = mapped_column(
        String(16), nullable=False, default="form", server_default=sql_text("'form'")
    )
    source_file_id: Mapped[uuid.UUID | None] = _fk(
        "import_source_file.id", nullable=True, ondelete="SET NULL"
    )
    note: Mapped[str | None] = mapped_column(Text)
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_comment: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    journal_entry_id: Mapped[uuid.UUID | None] = _fk(
        "journal_entry.id", nullable=True, ondelete="SET NULL"
    )


class MigrationOpeningBalanceLine(IdMixin, TenantMixin, Base):
    """One balance: ``amount`` is the balance debit minus credit (asset and debtor positive,
    liability, creditor and reserve negative), as it appears on the Immoware24 balance list."""

    __tablename__ = "migration_opening_balance_line"
    __table_args__ = (
        UniqueConstraint(
            "opening_balance_id",
            "account_id",
            name="uq_migration_opening_balance_line_opening_balance_id",
        ),
        CheckConstraint("amount <> 0", name="amount_non_zero"),
    )

    opening_balance_id: Mapped[uuid.UUID] = _fk("migration_opening_balance.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    text: Mapped[str | None] = mapped_column(String(500))
    # Bank balance lines: the property bank account the balance belongs to (statement check).
    property_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "property_bank_account.id", nullable=True, ondelete="SET NULL"
    )
    due_date: Mapped[date | None] = mapped_column(Date)


class MigrationReconciliationReport(IdMixin, TimestampMixin, TenantMixin, Base):
    """Zero difference check of one property as of the cut off date; the HTML report is
    stored as a document (``document_id``)."""

    __tablename__ = "migration_reconciliation_report"
    __table_args__ = (
        Index("ix_migration_reconciliation_report_property", "tenant_id", "property_id"),
    )

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    zero_difference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    compared: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    deviations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sql_text("0")
    )
    total_difference: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default=sql_text("0")
    )
    lines: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")


class MigrationSwitchRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """Switch of ``ledger.leading_system`` to the platform: requested by one person,
    decided by another (pattern ``release_gate_request``), only with G1 open."""

    __tablename__ = "migration_switch_request"
    __table_args__ = (
        Index(
            "uq_migration_switch_request_open",
            "tenant_id",
            "ledger_id",
            unique=True,
            postgresql_where=sql_text("status = 'requested'"),
        ),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    report_id: Mapped[uuid.UUID] = _fk("migration_reconciliation_report.id")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SwitchRequestStatus.REQUESTED.value,
        server_default=sql_text("'requested'"),
    )
    comment: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)


class AcceptanceStatus(StrEnum):
    DRAFT = "draft"
    SIGNED = "signed"


class MigrationAcceptance(IdMixin, TimestampMixin, TenantMixin, Base):
    """Acceptance record of the migration per property (13.1 Dokumentation der Abnahme, M8-09):
    scope of the check, responsible persons, data that cannot be migrated, fallback plan and
    archive and information concept before the old access is shut down. A signed record is
    never changed; a correction is a new record."""

    __tablename__ = "migration_acceptance"
    __table_args__ = (Index("ix_migration_acceptance_property", "tenant_id", "property_id"),)

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AcceptanceStatus.DRAFT.value,
        server_default=sql_text("'draft'"),
    )
    review_scope: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=sql_text("''")
    )
    responsible_persons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    non_migratable_data: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=sql_text("''")
    )
    fallback_plan: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=sql_text("''")
    )
    archive_concept: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=sql_text("''")
    )
    reconciliation_report_id: Mapped[uuid.UUID | None] = _fk(
        "migration_reconciliation_report.id", nullable=True, ondelete="SET NULL"
    )
    signed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
