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


class VatOption(StrEnum):
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
    # [{number, name, category, type, statement_kind, allocation_category, vat_option,
    #   relevant_for_cash_report, applies_to: [hoa, rental_owner, sev_owner, manager]}]
    accounts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


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
    vat_option: Mapped[VatOption] = mapped_column(
        _enum(VatOption, "account_vat_option"), nullable=False, default=VatOption.NONE
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
    # Opening balances need a second person (geprüfte Anfangsbestände, M10).
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class JournalLine(IdMixin, TenantMixin, Base):
    __tablename__ = "journal_line"
    __table_args__ = (
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="one_side_positive"
        ),
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


class OpenItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """Remaining amount is computed from settlements as of a date (6.9.13, B07)."""

    __tablename__ = "open_item"
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
