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


class LockIn(_In):
    until: date


class LeadingIn(_In):
    leading_system: LeadingSystem
