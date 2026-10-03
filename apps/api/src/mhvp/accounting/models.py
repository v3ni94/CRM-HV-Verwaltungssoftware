"""Ledger per legal entity, accounts, journal, open items (6.4, 6.9.1, 6.9.8, 6.9.10, 6.9.13).

Money is NUMERIC(14,2), rates NUMERIC(20,8). Posted entries are immutable (database triggers
in migration 0010); corrections only by reversal (B03). Balance per entry is checked by a
deferred constraint trigger and in the service (B02).
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)
RATE = Numeric(20, 8)


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class AccountCategory(StrEnum):
    BANK = "bank"
    CASH = "cash"
    RESERVE = "reserve"
    LOAN = "loan"
    TECHNICAL = "technical"
    REVENUE = "revenue"
    COST = "cost"
    DEBTOR = "debtor"
    CREDITOR = "creditor"
    TRANSIT = "transit"
    TAX = "tax"
    OPENING_BALANCE = "opening_balance"


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"


class AccountVatOption(StrEnum):
    NONE = "none"
    FULL = "full"
    REDUCED = "reduced"


class DeductibleVatRule(StrEnum):
    NONE = "none"
    FIXED_PERCENT = "fixed_percent"
    COMMERCIAL_SHARE = "commercial_share"


class AllocationCategory(StrEnum):
    ALLOCABLE_HEATING = "allocable_heating"
    ALLOCABLE_WATER = "allocable_water"
    ALLOCABLE_OTHER = "allocable_other"
    NON_ALLOCABLE_HEATING = "non_allocable_heating"
    NON_ALLOCABLE_WATER = "non_allocable_water"
    NON_ALLOCABLE_OTHER = "non_allocable_other"
    NONE = "none"


class StatementKind(StrEnum):
    HOA_FEE = "hoa_fee"
    RESERVE = "reserve"
    OPERATING_COSTS = "operating_costs"
    # SA-08 (migration 0278): further kinds of the statement (special levy, heating costs).
    SPECIAL_LEVY = "special_levy"
    HEATING = "heating"
    NONE = "none"


class VatMode(StrEnum):
    NONE = "none"  # no VAT option
    OPTION = "option"  # VAT option exercised for parts (commercial units)


class LeadingSystem(StrEnum):
    IMMOWARE24 = "immoware24"
    MHVP = "mhvp"


class EntryKind(StrEnum):
    RECEIVABLE = "receivable"
    INVOICE = "invoice"
    CUSTOM = "custom"
    BANK_TRANSFER = "bank_transfer"
    COST_TRANSFER = "cost_transfer"
    OPENING_BALANCE = "opening_balance"
    DEBTOR_PAYMENT = "debtor_payment"
    CREDITOR_PAYMENT = "creditor_payment"
    REVERSAL = "reversal"
    STATEMENT_RESULT = "statement_result"
    DUNNING_FEE = "dunning_fee"
    INTEREST = "interest"
    # AE22 (Q01-01 variant reclass): statement credit moved to a creditor account; posting
    # creates only the payable on the creditor line, never a receivable on the debtor debit.
    CREDIT_RECLASS = "credit_reclass"


class EntrySource(StrEnum):
    MANUAL = "manual"
    AUTO_RECEIVABLE = "auto_receivable"
    BANK_IMPORT = "bank_import"
    AI = "ai"
    STATEMENT = "statement"
    MIGRATION = "migration"


class EntryStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"


class ReversalReason(StrEnum):
    """Reason code of a reversal (B03, ADR 0014). The free text ``reversal_reason`` stays
    mandatory; the code makes corrections countable for the learning bookkeeper (an
    ``automation_error`` downgrades the rule that posted the entry, plan M12 S6). Codes are
    product standards, no tax or legal classification."""

    INPUT_ERROR = "input_error"  # Erfassungsfehler (Text, Beleg, Vorzeichen)
    WRONG_ASSIGNMENT = "wrong_assignment"  # falscher offener Posten oder falsches Konto
    WRONG_AMOUNT = "wrong_amount"
    WRONG_DATE = "wrong_date"  # falsches Buchungsdatum oder falsche Periode
    DUPLICATE = "duplicate"  # doppelt gebucht
    BANK_RETURN = "bank_return"  # Rückgabe oder Rücklastschrift durch die Bank
    RUN_REVERSAL = "run_reversal"  # Storno eines ganzen Laufs (Sollstellung)
    AUTOMATION_ERROR = "automation_error"  # Automatik hat falsch gebucht
    OTHER = "other"


class OpenItemKind(StrEnum):
    RECEIVABLE = "receivable"
    PAYABLE = "payable"


class ChartTemplate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant wide chart of accounts template (7.2). Unreleased until V8 is decided."""

    __tablename__ = "chart_of_accounts_template"
    __table_args__ = (UniqueConstraint("tenant_id", "code", "version"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    released: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Release workflow (M10-01/M10-02, V8, migration 0190): draft -> in_review -> released.
    # A released version is immutable; changes create a new version that supersedes it.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    review_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    release_comment: Mapped[str | None] = mapped_column(Text)
    release_document_id: Mapped[uuid.UUID | None] = _fk(
        "document.id", nullable=True, ondelete="SET NULL"
    )
    supersedes_id: Mapped[uuid.UUID | None] = _fk(
        "chart_of_accounts_template.id", nullable=True, ondelete="SET NULL"
    )
    # [{number, name, category, type, statement_kind, allocation_category, vat_option,
    #   relevant_for_cash_report, applies_to: [hoa, rental_owner, sev_owner, manager]}]
    accounts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # AE02 (M10-01, Produktschutz): release only by a person other than the one who asked for
    # the review. Default on; switching off needs accounting:approve and a reason (event).
    four_eyes_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class Ledger(IdMixin, TimestampMixin, TenantMixin, Base):
    """Exactly one ledger per legal entity (6.9.1, E01)."""

    __tablename__ = "ledger"
    __table_args__ = (
        UniqueConstraint("tenant_id", "legal_entity_id"),
        CheckConstraint(
            "fiscal_year_start_month BETWEEN 1 AND 12", name="fiscal_year_start_month_range"
        ),
    )

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True)
    name: Mapped[str] = mapped_column(String(400), nullable=False)
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    vat_mode: Mapped[VatMode] = mapped_column(
        _enum(VatMode, "ledger_vat_mode"), nullable=False, default=VatMode.NONE
    )
    locked_until: Mapped[date | None] = mapped_column(Date)
    template_id: Mapped[uuid.UUID | None] = _fk("chart_of_accounts_template.id", nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer)
    leading_system: Mapped[LeadingSystem] = mapped_column(
        _enum(LeadingSystem, "ledger_leading_system"),
        nullable=False,
        default=LeadingSystem.IMMOWARE24,
    )
    migration_cutoff: Mapped[date | None] = mapped_column(Date)


class LedgerAccount(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ledger_account"
    __table_args__ = (
        UniqueConstraint("tenant_id", "ledger_id", "number"),
        UniqueConstraint("ledger_id", "id", name="uq_ledger_account_ledger_id"),
        CheckConstraint("number ~ '^[0-9]{6}$'", name="number_six_digits"),
        CheckConstraint(
            "deductible_vat_percent IS NULL OR deductible_vat_percent BETWEEN 0 AND 100",
            name="deductible_vat_percent_range",
        ),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    number: Mapped[str] = mapped_column(String(6), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[AccountCategory] = mapped_column(
        _enum(AccountCategory, "account_category"), nullable=False
    )
    type: Mapped[AccountType] = mapped_column(_enum(AccountType, "account_type"), nullable=False)
    vat_option: Mapped[AccountVatOption] = mapped_column(
        _enum(AccountVatOption, "account_vat_option"), nullable=False, default=AccountVatOption.NONE
    )
    deductible_vat_rule: Mapped[DeductibleVatRule] = mapped_column(
        _enum(DeductibleVatRule, "deductible_vat_rule"),
        nullable=False,
        default=DeductibleVatRule.NONE,
    )
    deductible_vat_percent: Mapped[Decimal | None] = mapped_column(RATE)
    relevant_for_cash_report: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    booking_texts: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), nullable=False, default=list
    )
    allocation_category: Mapped[AllocationCategory] = mapped_column(
        _enum(AllocationCategory, "allocation_category"),
        nullable=False,
        default=AllocationCategory.NONE,
    )
    statement_kind: Mapped[StatementKind] = mapped_column(
        _enum(StatementKind, "statement_kind"), nullable=False, default=StatementKind.NONE
    )
    section_35a_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # SA-07 (A.1 Kontoattribute): relevance for the EÜR and for the VAT return as plain flags.
    # Set by a person (tax advisor release V8 open); no tax treatment is derived from them.
    eur_relevant: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ust_relevant: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # S711-05 check point only: input services used for mixed purposes (allocation open) and
    # need a manual review of Vorsteuerberichtigung. Not evaluated anywhere (P03 open).
    mixed_use_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # M17-01: code of the system catalogue of operating cost types (mhvp.billing.betrkv,
    # § 2 BetrKV numbers 1 to 17, "V" administration, "I" maintenance); a person assigns it.
    operating_cost_type: Mapped[str | None] = mapped_column(String(4))
    # Template review marker (M10-01): "none" or "entwurf" (proposal, tax adviser release open).
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    review_note: Mapped[str | None] = mapped_column(String(200))
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True)
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    party_id: Mapped[uuid.UUID | None] = _fk("party.id", nullable=True)
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", nullable=True)
    property_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "property_bank_account.id", nullable=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class LedgerAccountAllocation(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ledger_account_allocation"
    __table_args__ = (
        UniqueConstraint("tenant_id", "ledger_account_id", "allocation_key_id"),
        CheckConstraint("share_percent > 0 AND share_percent <= 100", name="share_range"),
    )

    ledger_account_id: Mapped[uuid.UUID] = _fk("ledger_account.id", ondelete="CASCADE")
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id")
    share_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False)


class JournalNumberCounter(TenantMixin, Base):
    """Gapless numbering per ledger and fiscal year (B04): the row is locked while posting."""

    __tablename__ = "journal_number_counter"

    ledger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger.id", ondelete="CASCADE"), primary_key=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class JournalEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "journal_entry"
    # GAL-101: platform is EUR only (ADR 0038); column documents the currency per record.
    currency: Mapped[str] = mapped_column(
        String(3),
        CheckConstraint("currency = 'EUR'", name="currency_eur"),
        nullable=False,
        default="EUR",
        server_default="EUR",
    )
    __table_args__ = (
        UniqueConstraint("tenant_id", "ledger_id", "fiscal_year", "number"),
        UniqueConstraint("ledger_id", "id", name="uq_journal_entry_ledger_id"),
        Index(
            "uq_journal_entry_idempotency",
            "tenant_id",
            "ledger_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_journal_entry_reverses",
            "reverses_id",
            unique=True,
            postgresql_where=text("reverses_id IS NOT NULL"),
        ),
        CheckConstraint(
            "(status = 'draft' AND number IS NULL) OR (status = 'posted' AND number IS NOT NULL)",
            name="number_when_posted",
        ),
        CheckConstraint("kind <> 'reversal' OR reverses_id IS NOT NULL", name="reversal_ref"),
        # Journal filters: status and booking date per ledger (performance review 26.09.2026).
        Index("ix_journal_entry_ledger_status", "tenant_id", "ledger_id", "status"),
        Index("ix_journal_entry_ledger_booking_date", "tenant_id", "ledger_id", "booking_date"),
        # Postings per bank transaction (history and reversal lookup of the learning
        # bookkeeper, ADR 0014, migration 0232).
        Index(
            "ix_journal_entry_bank_transaction",
            "tenant_id",
            "bank_transaction_id",
            postgresql_where=text("bank_transaction_id IS NOT NULL"),
        ),
        Index(
            "ix_journal_entry_auto_review_pending",
            "tenant_id",
            "ledger_id",
            postgresql_where=text("auto_review_pending"),
        ),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    status: Mapped[EntryStatus] = mapped_column(
        _enum(EntryStatus, "journal_entry_status"), nullable=False, default=EntryStatus.DRAFT
    )
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    number: Mapped[int | None] = mapped_column(Integer)
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    accrual_date: Mapped[date | None] = mapped_column(Date)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[EntryKind] = mapped_column(_enum(EntryKind, "journal_entry_kind"), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    bank_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    reverses_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    reversed_by_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text)
    # Reason code of a reversal entry (``ReversalReason``, B03); set on the reversal, not on
    # the reversed entry. Free text stays mandatory.
    reversal_reason_code: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[EntrySource] = mapped_column(
        _enum(EntrySource, "journal_entry_source"), nullable=False, default=EntrySource.MANUAL
    )
    ai_proposal_id: Mapped[uuid.UUID | None] = _fk("ai_proposal.id", nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    # Draft only: explicit settlement of open items [{open_item_id, amount}] (7.4 Tilgung).
    settlement_plan: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Automatic posting of the bank runner whose review item is still open (rule M12-05):
    # dunning, settlement proposal and direct debit runs leave the affected debtor accounts
    # alone until a person closed the review. No financial content; the guard trigger of
    # posted entries ignores this column (migration 0243).
    auto_review_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Opening balances need a second person (geprüfte Anfangsbestände, M10).
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class JournalEntryNote(IdMixin, TenantMixin, Base):
    """Supplementary note on a posted entry, kept apart from the financial content and
    versioned (B03 sentence 3, GA05-02). Append only (trigger ``forbid_mutation``, migration
    0303): a new version references its predecessor, the chain shares ``note_key``."""

    __tablename__ = "journal_entry_note"
    __table_args__ = (
        UniqueConstraint("tenant_id", "note_key", "version"),
        UniqueConstraint("supersedes_id"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(version = 1 AND supersedes_id IS NULL) OR (version > 1 AND supersedes_id IS NOT "
            "NULL)",
            name="version_chain",
        ),
        CheckConstraint("length(body) BETWEEN 1 AND 4000", name="body_length"),
        Index("ix_journal_entry_note_tenant_id_journal_entry_id", "tenant_id", "journal_entry_id"),
    )

    journal_entry_id: Mapped[uuid.UUID] = _fk("journal_entry.id")
    note_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("journal_entry_note.id", nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class JournalLine(IdMixin, TenantMixin, Base):
    __tablename__ = "journal_line"
    __table_args__ = (
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="one_side_positive"
        ),
        Index("ix_journal_line_journal_entry_id", "journal_entry_id"),
        Index("ix_journal_line_account_id", "account_id"),
        # Q15-01 (AE21, migration 0377): a line with a unit always carries its object; the
        # trigger ``journal_line_property`` fills it from the unit and refuses a mismatch.
        CheckConstraint("unit_id IS NULL OR property_id IS NOT NULL", name="property_with_unit"),
        Index("ix_journal_line_property_id", "property_id"),
    )

    journal_entry_id: Mapped[uuid.UUID] = _fk("journal_entry.id", ondelete="CASCADE")
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    debit: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    vat_percent: Mapped[Decimal | None] = mapped_column(RATE)
    vat_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    net_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_center: Mapped[str | None] = mapped_column(String(50))
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", nullable=True)
    allocation_key_override_id: Mapped[uuid.UUID | None] = _fk("allocation_key.id", nullable=True)
    text: Mapped[str | None] = mapped_column(String(500))
    # Object of the line (Q15-01, AE21): explicit, else from the unit, else from the contract of
    # the entry (``mhvp.accounting.line_property``). Reports per object read this column.
    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True)


class OpenItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """Remaining amount is computed from settlements as of a date (6.9.13, B07)."""

    __tablename__ = "open_item"
    # GAL-101: platform is EUR only (ADR 0038); column documents the currency per record.
    currency: Mapped[str] = mapped_column(
        String(3),
        CheckConstraint("currency = 'EUR'", name="currency_eur"),
        nullable=False,
        default="EUR",
        server_default="EUR",
    )
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        UniqueConstraint("journal_entry_id", "account_id"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    journal_entry_id: Mapped[uuid.UUID] = _fk("journal_entry.id")
    kind: Mapped[OpenItemKind] = mapped_column(
        _enum(OpenItemKind, "open_item_kind"), nullable=False
    )
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    component: Mapped[str | None] = mapped_column(String(63))  # payment type code
    written_off: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # AN15 (GAK-104, migration 0454): set only by an approved write off
    # (``mhvp.accounting.write_offs``); ``written_off_on`` makes the flag date aware (B07).
    written_off_on: Mapped[date | None] = mapped_column(Date)
    written_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    written_off_reason: Mapped[str | None] = mapped_column(String(500))
    written_off_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Date the debtor received the demand (Rechnung, Abrechnung, Zahlungsaufforderung) as
    # recorded by a person; needed for default mode ``after_notice_30_days`` (M16-03).
    notice_received_on: Mapped[date | None] = mapped_column(Date)


class OpenItemWriteOff(IdMixin, TenantMixin, Base):
    """AN15 (GAK-104): write off of an open item as its own procedure with reason, author,
    effective date and voucher. Proposed first; approval by a second person only with the
    tenant switch and gate G1 open. Approval sets the flag on the item; nothing is posted."""

    __tablename__ = "open_item_write_off"
    __table_args__ = (
        CheckConstraint("status IN ('proposed', 'approved', 'rejected')", name="status"),
        CheckConstraint("amount > 0", name="amount"),
        Index("ix_open_item_write_off_item", "tenant_id", "open_item_id"),
        Index(
            "uq_open_item_write_off_active",
            "open_item_id",
            unique=True,
            postgresql_where=text("status IN ('proposed', 'approved')"),
        ),
    )

    open_item_id: Mapped[uuid.UUID] = _fk("open_item.id")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed", server_default="proposed"
    )
    effective_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))


class OpenItemSettlement(IdMixin, TenantMixin, Base):
    """Settlement of an open item by a posted entry. Negative amounts undo a settlement when the
    settling entry is reversed; history stays reproducible (B07, B08)."""

    __tablename__ = "open_item_settlement"
    __table_args__ = (CheckConstraint("amount <> 0", name="amount_non_zero"),)

    open_item_id: Mapped[uuid.UUID] = _fk("open_item.id")
    journal_entry_id: Mapped[uuid.UUID] = _fk("journal_entry.id")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class RunStatus(StrEnum):
    PREVIEW = "preview"
    POSTED = "posted"
    REVERSED = "reversed"


class ItemStatus(StrEnum):
    READY = "ready"  # can be posted
    MANUAL = "manual"  # needs a released rule (proration, interval, VAT)
    BLOCKED = "blocked"  # configuration missing (ledger, account mapping)
    POSTED = "posted"
    REVERSED = "reversed"


class PaymentTypeAccount(IdMixin, TimestampMixin, TenantMixin, Base):
    """Revenue account per payment type and ledger (7.2: revenue per payment type)."""

    __tablename__ = "payment_type_account"
    __table_args__ = (UniqueConstraint("tenant_id", "ledger_id", "payment_type_code"),)

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    payment_type_code: Mapped[str] = mapped_column(String(63), nullable=False)
    account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")


class ReceivableRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "receivable_run"

    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "receivable_run_status"), nullable=False, default=RunStatus.PREVIEW
    )
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    totals: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # M13-01 to M13-03 (migration 0177): calculation path of the run (rules applied, segments,
    # fractions, rounding, instalment periods, VAT split) per item; empty for legacy runs.
    calculation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ReceivableItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "receivable_item"
    __table_args__ = (
        # Once per legal basis, period, debtor and component (7.3 Sollstellung, B08).
        Index(
            "uq_receivable_item_posted",
            "tenant_id",
            "contract_id",
            "payment_type_code",
            "period_month",
            unique=True,
            postgresql_where=text("status = 'posted'"),
        ),
    )

    run_id: Mapped[uuid.UUID] = _fk("receivable_run.id", ondelete="CASCADE")
    contract_id: Mapped[uuid.UUID] = _fk("contract.id")
    contract_payment_id: Mapped[uuid.UUID | None] = _fk("contract_payment.id", nullable=True)
    ledger_id: Mapped[uuid.UUID | None] = _fk("ledger.id", nullable=True)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    payment_type_code: Mapped[str] = mapped_column(String(63), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal(0))
    # M13-03 (migration 0177): net and tax part of ``amount`` (gross) when the VAT rule is
    # released; M13-01/02: the period the item covers (a part of the month or an instalment).
    net_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    vat_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ItemStatus] = mapped_column(
        _enum(ItemStatus, "receivable_item_status"), nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text)
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    # Evidence of the legal basis (7.5, migration 0251): contract version, applied payment plan,
    # start of validity of the applied amount and its reason with the source document
    # (resolution, economic plan, rent change letter) as stored on ``ContractPayment``.
    contract_version: Mapped[int | None] = mapped_column(Integer)
    payment_schedule_id: Mapped[uuid.UUID | None] = _fk("payment_schedule.id", nullable=True)
    basis_valid_from: Mapped[date | None] = mapped_column(Date)
    basis_reason: Mapped[str | None] = mapped_column(String(32))
    basis_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Difference item (7.5, migration 0251): the plan changed after the month was posted. The
    # item stays manual; the correction is a reversal and a new receivable (rule 0.1.7).
    difference_of_item_id: Mapped[uuid.UUID | None] = _fk("receivable_item.id", nullable=True)
    difference_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    # M24-01 (migration 0278): earmarked reserve of the standing amount (contract payment).
    reserve_id: Mapped[uuid.UUID | None] = _fk("hoa_reserve.id", nullable=True, ondelete="SET NULL")


class AdminFeeSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Management fee per property (6.4, 6.9.11). Invoices are drafts until tax data is set."""

    __tablename__ = "admin_fee_setting"

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    contract_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    invoice_debtor_party_id: Mapped[uuid.UUID | None] = _fk("party.id", nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    interval: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    vat_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal(0))
    min_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    max_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    # net amount per unit and interval by unit type, e.g. {"apartment": "25.00"}
    amounts_per_unit_type: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    # GA03-06 (migration 0312): manager contact, termination, due rule, revenue account and a
    # separate net fee per SE unit (replaces ``amounts_per_unit_type`` for an SE fee).
    manager_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date)
    due_day_rule: Mapped[str | None] = mapped_column(String(16))
    due_day: Mapped[int | None] = mapped_column(Integer)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id", nullable=True)
    sev_fee_amount: Mapped[Decimal | None] = mapped_column(MONEY)


class InvoiceKind(StrEnum):
    INVOICE = "invoice"
    PARTIAL = "partial"  # Abschlagsrechnung
    FINAL = "final"  # Schlussrechnung
    CREDIT_NOTE = "credit_note"
    RECURRING = "recurring"  # Dauerrechnung


class ReviewStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_REVIEWED = "partially_reviewed"
    QUERY = "query"
    OBJECTED = "objected"
    CLOSED_WITH_RESERVATION = "closed_with_reservation"
    CLOSED_OK = "closed_ok"


class PostingStatus(StrEnum):
    UNPOSTED = "unposted"
    POSTED = "posted"
    REVERSED = "reversed"


class Invoice(IdMixin, TimestampMixin, TenantMixin, Base):
    """Incoming invoice (6.4, 7.9.1). Review, posting and payment release are separate (6.9.9)."""

    __tablename__ = "invoice"
    # GAL-101: platform is EUR only (ADR 0038); column documents the currency per record.
    currency: Mapped[str] = mapped_column(
        String(3),
        CheckConstraint("currency = 'EUR'", name="currency_eur"),
        nullable=False,
        default="EUR",
        server_default="EUR",
    )
    __table_args__ = (
        Index("ix_invoice_creditor_number", "tenant_id", "provider_contact_id", "number"),
        Index("ix_invoice_tenant_ledger_id", "tenant_id", "ledger_id"),
        Index("ix_invoice_tenant_review_status_date", "tenant_id", "review_status", "invoice_date"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    creditor_account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id", nullable=True)
    provider_contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    kind: Mapped[InvoiceKind] = mapped_column(_enum(InvoiceKind, "invoice_kind"), nullable=False)
    number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    service_from: Mapped[date | None] = mapped_column(Date)
    service_to: Mapped[date | None] = mapped_column(Date)
    net: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    gross: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_percent: Mapped[Decimal | None] = mapped_column(RATE)
    discount_until: Mapped[date | None] = mapped_column(Date)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False, default="transfer")
    payee_iban: Mapped[str | None] = mapped_column(EncryptedText())
    payee_iban_fingerprint: Mapped[str | None] = mapped_column(String(64))
    iban_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    e_invoice_format: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    order_reference: Mapped[str | None] = mapped_column(String(100))
    recipient_name: Mapped[str | None] = mapped_column(String(400))  # as printed (PÜ01)
    # Final invoice: [{invoice_id, gross}] of deducted partial invoices (D12).
    deductions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "invoice_review_status"), nullable=False, default=ReviewStatus.OPEN
    )
    posting_status: Mapped[PostingStatus] = mapped_column(
        _enum(PostingStatus, "invoice_posting_status"),
        nullable=False,
        default=PostingStatus.UNPOSTED,
    )
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_hash: Mapped[str | None] = mapped_column(String(64))
    duplicate_of_id: Mapped[uuid.UUID | None] = _fk("invoice.id", nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("invoice.id", nullable=True)
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    findings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Migration 0252 (M14-01 to M14-09, docs/rules/M14-PU.md): order/contract link, PÜ01
    # mandatory data, PÜ03 amounts and tax markers, PÜ05 reference of credit notes.
    service_contract_id: Mapped[uuid.UUID | None] = _fk("service_contract.id", nullable=True)
    recurring_plan_id: Mapped[uuid.UUID | None] = _fk("recurring_invoice_plan.id", nullable=True)
    reference_invoice_id: Mapped[uuid.UUID | None] = _fk("invoice.id", nullable=True)
    service_place: Mapped[str | None] = mapped_column(String(200))
    issuer_vat_id: Mapped[str | None] = mapped_column(String(20))
    issuer_tax_number: Mapped[str | None] = mapped_column(String(30))
    attachment_document_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    discount_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    prepaid_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    retention_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    reverse_charge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    construction_withholding: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    input_tax_deductible: Mapped[bool | None] = mapped_column(Boolean)
    # M14-02 (migration 0291, rule PU02-SACHLICH): structured links of the factual review
    # (work order, resolution, economic plan item); the free text order_reference stays.
    work_order_id: Mapped[uuid.UUID | None] = _fk("work_order.id", nullable=True)
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id", nullable=True)
    plan_item_id: Mapped[uuid.UUID | None] = _fk("economic_plan_item.id", nullable=True)


class InvoiceLine(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "invoice_line"
    __table_args__ = (Index("ix_invoice_line_invoice_id", "invoice_id"),)

    invoice_id: Mapped[uuid.UUID] = _fk("invoice.id", ondelete="CASCADE")
    account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    net: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal(0))
    vat: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    accrual_date: Mapped[date | None] = mapped_column(Date)
    section_35a_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", nullable=True)
    text: Mapped[str | None] = mapped_column(String(500))
    # M14-02 (migration 0291): quantity and unit price for the price and quantity comparison.
    quantity: Mapped[Decimal | None] = mapped_column(RATE)
    unit_price: Mapped[Decimal | None] = mapped_column(RATE)


class InvoiceCheckSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """M14-02 (migration 0291): tolerances of the factual review per tenant, in percent;
    default 0 means exact match. Findings only, never a release."""

    __tablename__ = "invoice_check_setting"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    price_tolerance_percent: Mapped[Decimal] = mapped_column(
        RATE, nullable=False, default=Decimal(0), server_default="0"
    )
    quantity_tolerance_percent: Mapped[Decimal] = mapped_column(
        RATE, nullable=False, default=Decimal(0), server_default="0"
    )


class InvoiceReview(IdMixin, TenantMixin, Base):
    """PÜ05: person, time, reviewed version, scope, result and reason per review step."""

    __tablename__ = "invoice_review"
    __table_args__ = (Index("ix_invoice_review_invoice_id", "invoice_id"),)

    invoice_id: Mapped[uuid.UUID] = _fk("invoice.id", ondelete="CASCADE")
    step: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # completeness, factual, arithmetic_tax
    invoice_version: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # ok, query, objected, reservation
    scope: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    # M14-07 (migration 0252): delegation proof and structured scope of the review step.
    delegated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    delegation_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class RecurringInvoicePlan(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "recurring_invoice_plan"

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    provider_contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    gross: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interval_months: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    next_due: Mapped[date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    # M14-01 (migration 0252): contract link, VAT, anchor day (month end), end of the plan.
    service_contract_id: Mapped[uuid.UUID | None] = _fk("service_contract.id", nullable=True)
    order_reference: Mapped[str | None] = mapped_column(String(100))
    vat_percent: Mapped[Decimal] = mapped_column(
        RATE, nullable=False, default=Decimal(0), server_default="0"
    )
    anchor_day: Mapped[int | None] = mapped_column(Integer)
    ended_at: Mapped[date | None] = mapped_column(Date)
    # GA03-07 (migration 0312): request for automatic posting. Default off; effective only with
    # ``tenant_settings.auto_posting_enabled``, released G1 and an active 7.4 rule. Generation
    # still creates drafts only (OPEN_QUESTIONS AA10-01).
    auto_post: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class DunningSettings(IdMixin, TimestampMixin, TenantMixin, Base):
    """Levels per tenant, optional override per property (6.4). Fee amount per level is
    nullable and inactive until a value is entered (operator decision 25.09.2026, V7); no
    default amount is ever assumed. Interest stays disabled until ``interest_base_rate`` is
    maintained by the operator (Basiszinssatz changes half yearly, no value is hardcoded)."""

    __tablename__ = "dunning_settings"
    __table_args__ = (
        Index(
            "uq_dunning_settings_scope",
            "tenant_id",
            text("coalesce(property_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
        ),
    )

    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True)
    # [{level, min_days_overdue, text, fee_amount|null, payment_days|null, letter_text|null}].
    # On an object row (property_id set) every field below may be NULL: NULL means "inherit
    # from the tenant default" (M16-10, migration 0078). The tenant default row is complete.
    levels: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    threshold_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    # Fees are inactive below this level even with a fee_amount set (V7: "ab der 1. Mahnung").
    fee_from_level: Mapped[int | None] = mapped_column(Integer)
    interest_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Gesetzlicher Verzugszins = Basiszinssatz + Aufschlag (§ 288 BGB, Anhang C zu verifizieren).
    # Basiszinssatz has no in-repo source register entry; the operator maintains the current
    # value here. The run stays disabled while this is empty.
    interest_base_rate: Mapped[Decimal | None] = mapped_column(RATE)
    interest_spread: Mapped[Decimal | None] = mapped_column(RATE)
    # How the start of default (Verzug) is determined for the debtors of this scope (M16-03,
    # docs/rules/M16-03.md): ``after_notice_30_days`` (30 days after due date and receipt of
    # the demand, only with a recorded receipt date), ``calendar_due_date`` (due date fixed by
    # the contract) or ``after_reminder`` (receipt of the dunning letter). NULL: not decided,
    # no default start is shown and no interest is computed. Object rows inherit (M16-10).
    default_start_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)


class DunningRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "dunning_run"

    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="preview")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    totals: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # M9-01: status ``failed`` marks a scheduled run that raised; ``error`` holds the cause.
    error: Mapped[str | None] = mapped_column(Text)


class DunningCase(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "dunning_case"
    # AP25 (AP10-03, migration 0469): one sent case per debtor account and level.
    __table_args__ = (
        Index(
            "uq_dunning_case_sent_level",
            "tenant_id",
            "debtor_account_id",
            "level",
            unique=True,
            postgresql_where=text("status = 'sent'"),
        ),
    )

    run_id: Mapped[uuid.UUID] = _fk("dunning_run.id", ondelete="CASCADE")
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    debtor_account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    open_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    interest_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # proposed, excluded, sent
    reason: Mapped[str | None] = mapped_column(Text)
    letter_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    delivery_channel: Mapped[str | None] = mapped_column(String(16))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Draft receivable for the fee (Sollstellung beim Forderungsinhaber), created on approval.
    fee_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    # Draft HVM outgoing invoice for the fee, only when the claim holder is not HVM itself.
    fee_invoice_draft_id: Mapped[uuid.UUID | None] = _fk(
        "dunning_fee_invoice_draft.id", nullable=True
    )
    # Due date and default (Verzug) are kept apart (M16-03): ``due_date`` is the oldest due
    # date of the open items, ``default_start`` the computed start of default under
    # ``default_mode`` (NULL when it cannot be determined from stored facts).
    due_date: Mapped[date | None] = mapped_column(Date)
    default_start: Mapped[date | None] = mapped_column(Date)
    default_mode: Mapped[str | None] = mapped_column(String(32))
    # Receipt of this dunning letter by the debtor as recorded by a person (mode
    # ``after_reminder`` starts default from here, never from ``delivered_at``).
    received_on: Mapped[date | None] = mapped_column(Date)
    # Payment account printed in the letter: the default account of the claim holder
    # (M16-13). NULL with ``bank_warning`` set blocks the letter.
    bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "property_bank_account.id", nullable=True, ondelete="SET NULL"
    )
    bank_warning: Mapped[str | None] = mapped_column(Text)
    # Draft receivable for the Verzugszinsen (M16-05), created only on an explicit request of
    # a person after approval, never automatically; released on the normal four eyes path.
    interest_entry_id: Mapped[uuid.UUID | None] = _fk(
        "journal_entry.id", nullable=True, ondelete="SET NULL"
    )
    # Calculation periods of the interest (M16-02): one entry per Basiszinssatz period with
    # from, to, days, rate and amount; NULL for cases without interest.
    interest_detail: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)


class DunningDeliveryProof(IdMixin, TimestampMixin, TenantMixin, Base):
    """Evidence of the dispatch or receipt of a dunning letter (M16-01): Einschreiben,
    Post, E-Mail or Portal receipt with reference and optional document. A person records it;
    the platform itself sends nothing (dispatch stays locked)."""

    __tablename__ = "dunning_delivery_proof"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('registered_mail', 'postal_receipt', 'email_receipt', 'portal_receipt',"
            " 'other')",
            name="kind",
        ),
        Index("ix_dunning_delivery_proof_case_id", "tenant_id", "case_id"),
    )

    case_id: Mapped[uuid.UUID] = _fk("dunning_case.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    proof_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200))
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")
    note: Mapped[str | None] = mapped_column(Text)


class DunningItemBlock(IdMixin, TimestampMixin, TenantMixin, Base):
    """Structured dunning block per open item (M16-03, decision 3 a): Ratenplan, bestrittener
    Posten, Aufrechnung, Prozess or Insolvenz. An active block (``released_at`` NULL) keeps
    the item out of every dunning run; release is recorded, the row is never deleted."""

    __tablename__ = "dunning_item_block"
    __table_args__ = (
        CheckConstraint(
            "reason_code IN ('installment_plan', 'disputed', 'set_off', 'litigation',"
            " 'insolvency')",
            name="reason_code",
        ),
        Index("ix_dunning_item_block_open_item_id", "tenant_id", "open_item_id"),
    )

    open_item_id: Mapped[uuid.UUID] = _fk("open_item.id", ondelete="CASCADE")
    reason_code: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DunningInterestRate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Basiszinssatz with period of validity and source (M16-02, 7.5, R10): a row is valid from
    ``valid_from`` until the day before the next row. Values are maintained by the operator
    from an official source; nothing is hardcoded."""

    __tablename__ = "dunning_interest_rate"
    __table_args__ = (UniqueConstraint("tenant_id", "valid_from"),)

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    base_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    source: Mapped[str] = mapped_column(String(400), nullable=False)


class DunningFeeInvoiceDraft(IdMixin, TimestampMixin, TenantMixin, Base):
    """Draft outgoing invoice of Hausverwaltung Müller GmbH to the claim holder (Gemeinschaft
    or Eigentümer/Vermieter) for a dunning fee (operator decision 25.09.2026, V7). Draft only,
    behind G1 and the four eyes release; no invoice number is issued here (7.9, M13 pattern:
    the fee calculation itself already stays a proposal until amounts and the contractual
    basis are confirmed by Rechtsberatung)."""

    __tablename__ = "dunning_fee_invoice_draft"

    case_id: Mapped[uuid.UUID] = _fk("dunning_case.id", ondelete="CASCADE")
    issuer_ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    recipient_legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    text: Mapped[str] = mapped_column(String(400), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DunningMahnbescheidPrep(IdMixin, TimestampMixin, TenantMixin, Base):
    """Preparation record for a gerichtliches Mahnverfahren (7.5, M16). Data only; no filing.
    Always exported marked ``Vorbereitung, Prüfung durch Rechtsanwalt``; deadline hints are
    informational and marked ``zu prüfen`` (0.1.3, never a computed Notfrist)."""

    __tablename__ = "dunning_mahnbescheid_prep"
    __table_args__ = (UniqueConstraint("tenant_id", "case_id"),)

    case_id: Mapped[uuid.UUID] = _fk("dunning_case.id", ondelete="CASCADE")
    antragsteller_legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    antragsgegner_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hauptforderung: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    nebenforderungen: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    zustelladresse: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    aktenzeichen_intern: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="in_vorbereitung", server_default="in_vorbereitung"
    )


class ExportRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """Export with period, format, checksum and file (6.4, 7.7)."""

    __tablename__ = "export_run"

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    # Export log remark, e.g. "Kontenzuordnung zu prüfen" for a DATEV export (M18-01): the CRM
    # account numbers are emitted unmapped, no Kontenrahmen assignment is invented.
    note: Mapped[str | None] = mapped_column(String(200))
    # Audit export (A26, 7.7, D55): queued -> running -> done | failed. Journal and DATEV runs
    # are written complete and therefore start as "done" (migration 0096).
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="done", server_default="done"
    )
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # DATEV batch self check (M18-01, migration 0190): the written file and the last report.
    content: Mapped[str | None] = mapped_column(Text)
    check_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminFeeInvoiceStatus(StrEnum):
    ISSUED = "issued"
    RELEASED = "released"
    # M13-05 (migration 0290): set together with ``cancelled_at`` by the credit note.
    CANCELLED = "cancelled"


class AdminFeeInvoice(IdMixin, TimestampMixin, TenantMixin, Base):
    """Issued Verwalterhonorar invoice of the tenant (M13-04, A12, 13.5 E-Rechnung).

    Written by ``POST /accounting/admin-fees/{id}/invoice-issue`` once the gapless number is
    allocated; the amounts and lines are frozen here so that the XRechnung XML
    (``mhvp.accounting.xrechnung``) is reproducible. Tax identifiers are never copied: the XML
    reads them from ``TenantBillingSettings`` at generation time (encrypted at rest). Rows are
    not posted anywhere: the revenue posting of the fee stays behind G1.
    """

    __tablename__ = "admin_fee_invoice"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_admin_fee_invoice_number"),
        Index("ix_admin_fee_invoice_tenant_id", "tenant_id"),
        Index(
            "uq_admin_fee_invoice_period",
            "tenant_id",
            "fee_setting_id",
            "period_start",
            unique=True,
            postgresql_where=text(
                "kind = 'invoice' AND cancelled_at IS NULL AND period_start IS NOT NULL"
            ),
        ),
    )

    fee_setting_id: Mapped[uuid.UUID] = _fk("admin_fee_setting.id")
    property_id: Mapped[uuid.UUID] = _fk("property.id")
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[AdminFeeInvoiceStatus] = mapped_column(
        _enum(AdminFeeInvoiceStatus, "admin_fee_invoice_status"),
        nullable=False,
        default=AdminFeeInvoiceStatus.ISSUED,
        server_default="issued",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default="EUR"
    )
    net: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    vat: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    gross: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # [{"text", "quantity", "unit_price", "amount"}]; the sum of "amount" equals net (B06),
    # a minimum or maximum fee is an explicit adjustment line, never a hidden difference.
    lines: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Debtor of the fee (E13, D58): the legal entity the fee is a cost in and, for an SE fee,
    # the owner party. Both nullable when the entity is not yet created.
    debtor_legal_entity_id: Mapped[uuid.UUID | None] = _fk("legal_entity.id", nullable=True)
    invoice_debtor_party_id: Mapped[uuid.UUID | None] = _fk("party.id", nullable=True)
    # Leitweg-ID as entered in TenantBillingSettings at issue time (BT-10 BuyerReference).
    buyer_reference: Mapped[str | None] = mapped_column(String(64))
    xml_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    # M13-05 (migration 0282): readable invoice document (PDF on the letterhead) in the index.
    pdf_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    # S13-03 (migration 0381): ZUGFeRD / Factur-X hybrid (PDF with CII EN 16931) in the index
    # and the result of the own checks at filing time (CII structure, PDF/A pre-check; the
    # PDF/A conformance itself stays unverified, mhvp.accounting.zugferd).
    zugferd_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    zugferd_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # M13-05/M13-06 (migration 0251): service period, kind (invoice or credit note), the
    # corrected invoice of a credit note, release and cancellation trail. One invoice per
    # setting and period while it is not cancelled (uq_admin_fee_invoice_period).
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="invoice", server_default="invoice"
    )
    corrects_invoice_id: Mapped[uuid.UUID | None] = _fk("admin_fee_invoice.id", nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    # M13-07 (migration 0290): revenue posting drafts of the fee, one per ledger (E01): the
    # payer side in the debtor ledger, the revenue side in the ledger of the manager. Only
    # drafts are written here (behind G1); posting uses the regular path (B03 to B09).
    payer_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    manager_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)


class AdminFeePostingConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    """Account assignment of the fee revenue posting per tenant (M13-07, migration 0290).

    No default exists: without this row (or without a ledger of the debtor) no draft is
    created. The manager side names concrete accounts of the manager ledger; the payer side
    names account numbers, resolved in each debtor ledger (one ledger per legal entity, E01).
    The VAT accounts are optional; with VAT on the invoice and no VAT account on a side the
    gross amount stays on the expense or revenue account of that side as configured by the
    operator (tax treatment open, docs/OPEN_QUESTIONS.md T04-01).
    """

    __tablename__ = "admin_fee_posting_config"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_admin_fee_posting_config_tenant_id"),
        CheckConstraint(
            "payer_expense_account_number ~ '^[0-9]{6}$' "
            "AND payer_payable_account_number ~ '^[0-9]{6}$' "
            "AND (payer_vat_account_number IS NULL "
            "OR payer_vat_account_number ~ '^[0-9]{6}$')",
            name="payer_numbers_six_digits",
        ),
    )

    manager_ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    manager_receivable_account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    manager_revenue_account_id: Mapped[uuid.UUID] = _fk("ledger_account.id")
    manager_vat_account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id", nullable=True)
    payer_expense_account_number: Mapped[str] = mapped_column(String(6), nullable=False)
    payer_payable_account_number: Mapped[str] = mapped_column(String(6), nullable=False)
    payer_vat_account_number: Mapped[str | None] = mapped_column(String(6))


class DatevAccountMapping(IdMixin, TimestampMixin, TenantMixin, Base):
    """Operator maintained assignment of a CRM ledger account number to a DATEV Sachkonto
    (A36, M18-01). Pure master data: no chart of accounts (SKR03/SKR04) is preloaded, every
    row is entered or imported by the operator (rule M18-04).

    ``ledger_id`` empty means the row applies to every ledger of the tenant; a row with a
    ledger wins over the tenant wide row. ``valid_from`` empty means "since ever"; among
    several rows the latest ``valid_from`` not after the booking date wins. Uniqueness per
    (tenant, ledger or none, account_code, valid_from or none) is enforced by an expression
    index in migration 0099.
    """

    __tablename__ = "datev_account_mapping"
    __table_args__ = (
        Index("ix_datev_account_mapping_tenant_id", "tenant_id"),
        Index("ix_datev_account_mapping_ledger_id", "ledger_id"),
        Index(
            "ux_datev_account_mapping_key",
            "tenant_id",
            text("COALESCE(ledger_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "account_code",
            text("COALESCE(valid_from, '0001-01-01'::date)"),
            unique=True,
        ),
    )

    ledger_id: Mapped[uuid.UUID | None] = _fk("ledger.id", nullable=True, ondelete="CASCADE")
    account_code: Mapped[str] = mapped_column(String(32), nullable=False)
    datev_account: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)


class G1AcceptanceStatus(StrEnum):
    OPEN = "open"
    PASSED = "passed"
    FAILED = "failed"


class G1AcceptanceItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """Operator's result per item of the G1 opening checklist (M12-09, migration 0242).

    ``item_key`` is an annex D case id (``D04``) or a manual checklist key (``vat_review``).
    The row records who accepted what and when for the opening page; it opens no gate and
    replaces no domain check (ADR 0003).
    """

    __tablename__ = "g1_acceptance"
    __table_args__ = (UniqueConstraint("tenant_id", "item_key", name="uq_g1_acceptance_tenant_id"),)

    item_key: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(8), nullable=False, default=G1AcceptanceStatus.OPEN.value, server_default="open"
    )
    confirmed_on: Mapped[date | None] = mapped_column(Date)
    confirmed_by_name: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    # AE03 (migration 0359): responsible person and evidence per item.
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(500))


class RuleVersion(IdMixin, TimestampMixin, TenantMixin, Base):
    """Register of versions of a domain rule with effective date and affected case groups
    (S711-11, 7.12). A register only: no calculation reads it, and an entry is no legal
    release. ``expert_confirmed_*`` records a person's confirmation, never an automatic one."""

    __tablename__ = "rule_version"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_id", "version"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="period"),
        CheckConstraint("status IN ('draft', 'confirmed', 'withdrawn')", name="status_valid"),
        Index("ix_rule_version_rule_effective", "tenant_id", "rule_id", "effective_from"),
    )

    rule_id: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    case_groups: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list, server_default=text("'{}'")
    )
    source_status: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="draft", server_default=text("'draft'")
    )
    expert_confirmed_by: Mapped[str | None] = mapped_column(String(200))
    expert_confirmed_on: Mapped[date | None] = mapped_column(Date)


class ApprovalDecision(IdMixin, TenantMixin, Base):
    """Central approval record bound to a hash of the approved subject (6.9.9, E09, S69-02).
    Written next to the existing records (``payment_approval``, ``invoice.released_hash``,
    ``invoice_second_approval``), which stay authoritative for the current checks. A change of
    the subject persists ``status='invalidated'`` instead of only failing a hash comparison."""

    __tablename__ = "approval_decision"
    __table_args__ = (
        CheckConstraint("subject_type IN ('payment_order', 'invoice')", name="subject_type_valid"),
        CheckConstraint("status IN ('valid', 'invalidated')", name="status_valid"),
        Index("ix_approval_decision_subject", "tenant_id", "subject_type", "subject_id"),
    )

    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    step: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="valid", server_default=text("'valid'")
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(String(200))
    # Id of the legacy record (payment_approval, invoice_second_approval), if any.
    legacy_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # S69-03: warnings of the person identity check (same name and birth date etc.).
    warnings: Mapped[list[str]] = mapped_column(
        ARRAY(String(300)), nullable=False, default=list, server_default=text("'{}'")
    )


class OpenItemBalance(IdMixin, TenantMixin, Base):
    """Maintained table of open item remainders as of a cut-off date (6.9.13, E15, B07,
    S69-04). A read copy for lists and reports; ``services.remaining`` from the settlements
    stays the source of truth and every refresh recomputes from it."""

    __tablename__ = "open_item_balance"
    __table_args__ = (
        UniqueConstraint("open_item_id", "as_of", name="uq_open_item_balance_item_as_of"),
        CheckConstraint("source IN ('job', 'manual')", name="source_valid"),
        Index("ix_open_item_balance_ledger_as_of", "tenant_id", "ledger_id", "as_of"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    open_item_id: Mapped[uuid.UUID] = _fk("open_item.id", ondelete="CASCADE")
    account_id: Mapped[uuid.UUID] = _fk("ledger_account.id", ondelete="CASCADE")
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    remaining: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(
        String(8), nullable=False, default="job", server_default=text("'job'")
    )
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class LedgerInterestTaxConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tax accounts per ledger for withholdings on credit interest (P01-01, AE05, migration
    0361). No row or an empty account means the withholding cannot be entered: no tax rate is
    stored, amounts always come from the bank document."""

    __tablename__ = "ledger_interest_tax_config"
    __table_args__ = (UniqueConstraint("ledger_id"),)

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    capital_gains_tax_account_id: Mapped[uuid.UUID | None] = _fk(
        "ledger_account.id", nullable=True, ondelete="RESTRICT"
    )
    solidarity_tax_account_id: Mapped[uuid.UUID | None] = _fk(
        "ledger_account.id", nullable=True, ondelete="RESTRICT"
    )
    church_tax_account_id: Mapped[uuid.UUID | None] = _fk(
        "ledger_account.id", nullable=True, ondelete="RESTRICT"
    )


class InterestTaxWithholding(IdMixin, TimestampMixin, TenantMixin, Base):
    """Withholdings of one interest entry as stated on the bank document (P01-01, AE05).
    Written with the draft and immutable afterwards (the entry lines carry the booking)."""

    __tablename__ = "interest_tax_withholding"
    __table_args__ = (
        UniqueConstraint("journal_entry_id"),
        CheckConstraint(
            "capital_gains_tax >= 0 AND solidarity_tax >= 0 AND church_tax >= 0",
            name="non_negative",
        ),
        CheckConstraint(
            "capital_gains_tax + solidarity_tax + church_tax < gross_amount", name="below_gross"
        ),
    )

    journal_entry_id: Mapped[uuid.UUID] = _fk("journal_entry.id", ondelete="RESTRICT")
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="RESTRICT")
    bank_account_id: Mapped[uuid.UUID] = _fk("ledger_account.id", ondelete="RESTRICT")
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    capital_gains_tax: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    solidarity_tax: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    church_tax: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )


class PeriodLock(IdMixin, TimestampMixin, TenantMixin, Base):
    """Period lock per property and period (P06-02, migration 0376). It restricts postings
    whose lines belong to the property; a release keeps the row (``released_at``)."""

    __tablename__ = "period_lock"
    __table_args__ = (
        CheckConstraint("period_from <= period_to", name="period"),
        CheckConstraint(
            "source IN ('manual', 'statement', 'owner_statement', 'hoa_statement')",
            name="source",
        ),
        Index("ix_period_lock_property", "tenant_id", "ledger_id", "property_id"),
        Index(
            "uq_period_lock_statement_active",
            "tenant_id",
            "source",
            "statement_id",
            unique=True,
            postgresql_where=text("statement_id IS NOT NULL AND released_at IS NULL"),
        ),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    property_id: Mapped[uuid.UUID] = _fk("property.id")
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", server_default="manual"
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(String(500))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    release_reason: Mapped[str | None] = mapped_column(String(500))
    release_requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    release_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_request_reason: Mapped[str | None] = mapped_column(String(500))


class PeriodLockSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant switches of the period lock; no row means the defaults (all conservative):
    ledger wide lock only, no automatic lock on closing, no release (AA08-01 open)."""

    __tablename__ = "period_lock_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint("lock_mode IN ('ledger_only', 'object_period')", name="lock_mode"),
    )

    lock_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ledger_only", server_default="ledger_only"
    )
    auto_lock_on_close: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    reopen_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class LedgerLeadingSwitch(IdMixin, TimestampMixin, TenantMixin, Base):
    """Leading system per ledger, optional property, process kind and valid-from date
    (13.1 Ergänzung, GAC-05). Requested by one person, decided by another; an approved row
    is never changed, a later switch is a new row. Without approved rows the ledger flag
    ``leading_system`` applies unchanged."""

    __tablename__ = "ledger_leading_switch"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('receivable_posting', 'dunning', 'direct_debit', 'payment_order')",
            name="kind_valid",
        ),
        CheckConstraint("leading_system IN ('immoware24', 'mhvp')", name="leading_valid"),
        CheckConstraint("status IN ('requested', 'approved', 'rejected')", name="status_valid"),
        Index("ix_ledger_leading_switch_lookup", "tenant_id", "ledger_id", "kind", "valid_from"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", ondelete="CASCADE")
    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    leading_system: Mapped[str] = mapped_column(String(16), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", server_default=text("'requested'")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)
