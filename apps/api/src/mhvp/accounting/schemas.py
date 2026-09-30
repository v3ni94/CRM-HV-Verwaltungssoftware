"""API schemas of the ledger (6.4). Money as decimal strings, never float (6.9.8)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mhvp.accounting.models import (
    AccountCategory,
    AccountType,
    AccountVatOption,
    AllocationCategory,
    EntryKind,
    EntrySource,
    EntryStatus,
    LeadingSystem,
    ReversalReason,
    StatementKind,
    VatMode,
)

Money = Decimal


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChartTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    version: int
    released: bool
    released_at: datetime | None
    released_by: uuid.UUID | None = None
    status: str = "draft"
    review_requested_at: datetime | None = None
    review_requested_by: uuid.UUID | None = None
    release_comment: str | None = None
    release_document_id: uuid.UUID | None = None
    supersedes_id: uuid.UUID | None = None
    accounts: list[dict[str, Any]]


class LedgerIn(_In):
    legal_entity_id: uuid.UUID
    template_id: uuid.UUID | None = None
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    migration_cutoff: date | None = None


class LedgerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    property_id: uuid.UUID | None
    name: str
    fiscal_year_start_month: int
    vat_mode: VatMode
    locked_until: date | None
    template_id: uuid.UUID | None
    template_version: int | None
    leading_system: LeadingSystem
    migration_cutoff: date | None


class AccountIn(_In):
    number: str = Field(pattern=r"^[0-9]{6}$")
    name: str = Field(min_length=1, max_length=200)
    category: AccountCategory
    type: AccountType
    vat_option: AccountVatOption = AccountVatOption.NONE
    relevant_for_cash_report: bool = False
    allocation_category: AllocationCategory = AllocationCategory.NONE
    statement_kind: StatementKind = StatementKind.NONE
    section_35a_eligible: bool = False
    booking_texts: list[str] = Field(default_factory=list, max_length=3)
    property_bank_account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


class AccountPatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    visible: bool | None = None
    active: bool | None = None
    booking_texts: list[str] | None = Field(default=None, max_length=3)
    # M10-03: default VAT option and cash report flag are editable; VAT stays on the lines,
    # so a change only affects future drafts, never posted entries (B03).
    vat_option: AccountVatOption | None = None
    relevant_for_cash_report: bool | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: str
    name: str
    category: AccountCategory
    type: AccountType
    vat_option: AccountVatOption
    relevant_for_cash_report: bool
    visible: bool
    active: bool
    allocation_category: AllocationCategory
    statement_kind: StatementKind
    section_35a_eligible: bool
    eur_relevant: bool
    ust_relevant: bool
    mixed_use_review: bool
    review_status: str
    review_note: str | None
    party_id: uuid.UUID | None
    unit_id: uuid.UUID | None
    property_bank_account_id: uuid.UUID | None
    is_system: bool


class LineSchema(_In):
    account_id: uuid.UUID
    debit: Money = Money("0")
    credit: Money = Money("0")
    text: str | None = Field(default=None, max_length=500)
    vat_percent: Decimal | None = None
    vat_amount: Money | None = None
    net_amount: Money | None = None
    unit_id: uuid.UUID | None = None
    cost_center: str | None = Field(default=None, max_length=50)


class SettlementIn(_In):
    open_item_id: uuid.UUID
    amount: Money


class JournalEntryIn(_In):
    booking_date: date
    value_date: date | None = None
    due_date: date | None = None
    accrual_date: date | None = None
    text: str = Field(min_length=1, max_length=500)
    kind: EntryKind
    reference: str | None = Field(default=None, max_length=100)
    document_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    lines: list[LineSchema] = Field(min_length=2, max_length=500)
    settlements: list[SettlementIn] = Field(default_factory=list, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=200)


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    line_no: int
    account_id: uuid.UUID
    debit: Money
    credit: Money
    text: str | None
    vat_percent: Decimal | None
    vat_amount: Money | None
    net_amount: Money | None
    unit_id: uuid.UUID | None


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ledger_id: uuid.UUID
    status: EntryStatus
    fiscal_year: int | None
    number: int | None
    booking_date: date
    value_date: date | None
    due_date: date | None
    accrual_date: date | None
    text: str
    kind: EntryKind
    reference: str | None
    document_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    reverses_id: uuid.UUID | None
    reversed_by_id: uuid.UUID | None
    reversal_reason: str | None
    reversal_reason_code: str | None = None
    source: EntrySource
    settlement_plan: list[dict[str, Any]]
    posted_at: datetime | None
    posted_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    created_by: uuid.UUID | None
    lines: list[LineOut] = []


class ReverseIn(_In):
    reason: str = Field(min_length=3, max_length=2000)
    booking_date: date | None = None
    # B03 reason code (``ReversalReason``); default ``other`` keeps existing clients working.
    reason_code: ReversalReason = ReversalReason.OTHER


class LockIn(_In):
    until: date


class LeadingIn(_In):
    leading_system: LeadingSystem


# Open item settlement proposal in the statutory order (M10-03, 7.4 Nr. 5, D39) ----------


class DeterminationIn(_In):
    """Explicit Tilgungsbestimmung of the payer; without amount the whole rest of the item."""

    open_item_id: uuid.UUID
    amount: Money | None = None


class SettlementProposalIn(_In):
    account_id: uuid.UUID
    amount: Money
    as_of: date
    purpose: str | None = Field(default=None, max_length=500)
    determination: list[DeterminationIn] = Field(default_factory=list, max_length=100)


class SettlementConfirmIn(SettlementProposalIn):
    """Confirmation of a proposal: the fingerprint must equal the recomputed proposal."""

    fingerprint: str = Field(min_length=64, max_length=64)
    bank_account_id: uuid.UUID
    booking_date: date
    text: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=100)
    post_immediately: bool = False


# M10-01 cost account allocation, M10-05 creditor sync, M10-06 cost transfer and interest --


class AccountingAllocationItemIn(_In):
    allocation_key_id: uuid.UUID
    share_percent: Decimal = Field(gt=0, le=100, max_digits=12, decimal_places=4)


class AccountingAllocationIn(_In):
    items: list[AccountingAllocationItemIn] = Field(default_factory=list, max_length=50)


class AccountingAllocationItemOut(BaseModel):
    allocation_key_id: uuid.UUID
    code: str
    name: str
    share_percent: Decimal


class AccountingAllocationOut(BaseModel):
    ledger_account_id: uuid.UUID
    items: list[AccountingAllocationItemOut]
    total_percent: Decimal


class AccountingCreditorSyncOut(BaseModel):
    created: int
    linked: int


class AccountingCostTransferIn(_In):
    booking_date: date
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: Money = Field(gt=0, max_digits=14, decimal_places=2)
    text: str = Field(min_length=3, max_length=500)
    unit_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=100)
    document_id: uuid.UUID | None = None


class AccountingInterestIn(_In):
    booking_date: date
    bank_account_id: uuid.UUID
    interest_account_id: uuid.UUID
    amount: Money = Field(gt=0, max_digits=14, decimal_places=2)
    # credit: interest received (bank debit), debit: interest charged (bank credit)
    direction: str = Field(pattern=r"^(credit|debit)$")
    text: str = Field(min_length=3, max_length=500)
    value_date: date | None = None
    reference: str | None = Field(default=None, max_length=100)
    document_id: uuid.UUID | None = None
