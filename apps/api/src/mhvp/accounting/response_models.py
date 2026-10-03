"""AN11 (GAI-304): documented responses of accounting routes, most of them with amounts.

Each model only documents and validates; the JSON bytes stay what the handler returned
(``RawJsonOut``, ADR 0037: ``Decimal`` is serialized as a JSON string).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mhvp.accounting.write_responses import RawJsonOut


class AccountingAuditExportRunOut(RawJsonOut):
    id: uuid.UUID
    ledger_id: uuid.UUID
    format: str
    status: str
    period_from: date | None = None
    period_to: date | None = None
    rows: int | None = None
    sha256: str | None = None
    document_id: uuid.UUID | None = None
    params: dict[str, Any] | None = None
    note: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    created_by: uuid.UUID | None = None
    finished_at: datetime | None = None


class AccountingReportHeaderOut(RawJsonOut):
    report: str
    legal_entity_id: uuid.UUID | None = None
    legal_entity_name: str | None = None
    legal_entity_kind: str | None = None
    ledger_id: uuid.UUID
    ledger_name: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    as_of: date | None = None
    generated_at: datetime | None = None
    filters: dict[str, Any] | None = None
    status: str
    status_note: str | None = None


class AccountingSheetMovementOut(RawJsonOut):
    entry_id: uuid.UUID
    number: str
    booking_date: date
    text: str | None = None
    kind: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class AccountingAccountSheetOut(RawJsonOut):
    account_id: uuid.UUID
    number: str
    name: str
    start: date
    end: date
    opening_balance: Decimal
    debit: Decimal
    credit: Decimal
    closing_balance: Decimal
    movements: list[AccountingSheetMovementOut]


class AccountingTrialBalanceRowOut(RawJsonOut):
    account_id: uuid.UUID
    number: str
    name: str
    category: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class AccountingTrialBalanceOut(RawJsonOut):
    as_of: date
    start: date | None = None
    accounts: list[AccountingTrialBalanceRowOut]
    debit: Decimal
    credit: Decimal
    balanced: bool


class AccountingOpenItemOut(RawJsonOut):
    id: uuid.UUID
    account_id: uuid.UUID
    account_number: str | None = None
    kind: str
    journal_entry_id: uuid.UUID | None = None
    booking_date: date | None = None
    due_date: date | None = None
    amount: Decimal
    remaining: Decimal
    contract_id: uuid.UUID | None = None
    notice_received_on: date | None = None


class AccountingReportAccountSheetOut(AccountingAccountSheetOut):
    header: AccountingReportHeaderOut


class AccountingReportTrialBalanceOut(AccountingTrialBalanceOut):
    header: AccountingReportHeaderOut


class AccountingReportOpenItemsOut(RawJsonOut):
    header: AccountingReportHeaderOut
    rows: list[AccountingOpenItemOut]


class AccountingReportRowsOut(RawJsonOut):
    """Report with the common header and a list of rows (revenue, payments by debtor)."""

    header: AccountingReportHeaderOut
    rows: list[Any]


class AccountingReportMonthlyMatrixOut(RawJsonOut):
    header: AccountingReportHeaderOut
    months: list[Any]
    accounts: list[Any]
    totals_by_category: Any = None
    sign_note: str | None = None


class AccountingReportTargetActualOut(RawJsonOut):
    header: AccountingReportHeaderOut
    rows: list[Any]
    total_target: Decimal
    total_actual_on_target: Decimal
    total_difference: Decimal
    total_receipts_in_period: Decimal
    note: str | None = None


class AccountingReportBankStatementOut(RawJsonOut):
    header: AccountingReportHeaderOut
    account: dict[str, Any] | None = None
    opening_balance: Decimal | None = None
    movements: list[Any] | None = None
    closing_balance: Decimal | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    reconciliation: Any = None


class AccountingReportVatOverviewOut(RawJsonOut):
    header: AccountingReportHeaderOut
    months: list[Any] | None = None
    by_month: Any = None
    by_rate: list[Any] | None = None
    total_output_vat: Decimal | None = None
    total_input_vat_before_deduction: Decimal | None = None
    ust_flagged_accounts: int | None = None
    mixed_use_review_accounts: list[Any] | None = None
    checkpoints: list[Any] | None = None
    note: str | None = None


class AccountingReportVatByPropertyOut(RawJsonOut):
    header: AccountingReportHeaderOut
    rows: list[Any] | None = None
    total_output_vat: Decimal | None = None
    total_input_vat_before_deduction: Decimal | None = None
    note: str | None = None


class AccountingReportIncomeExpenseOut(RawJsonOut):
    header: AccountingReportHeaderOut
    revenue: list[Any] | None = None
    cost: list[Any] | None = None
    total_revenue: Decimal | None = None
    total_cost: Decimal | None = None
    surplus: Decimal | None = None
    note: str | None = None


class AccountingReportLiquidityOut(RawJsonOut):
    header: AccountingReportHeaderOut
    as_of: date
    horizon: Any = None
    accounts: list[Any] | None = None
    free_funds: Decimal | None = None
    reserve_funds: Decimal | None = None
    segregated_deposits: Decimal | None = None
    expected_inflows: Decimal | None = None
    expected_outflows: Decimal | None = None
    debtor_credits: Decimal | None = None
    projected_free_funds: Decimal | None = None
    note: str | None = None


class AccountingReportLinePropertyDriftOut(RawJsonOut):
    header: AccountingReportHeaderOut


class AccountingEInvoiceCheckOut(RawJsonOut):
    """Structure check of an XRechnung, credit note or ZUGFeRD invoice (no official run)."""

    invoice_id: uuid.UUID
    number: str | None = None
    structure_ok: bool
    findings: list[dict[str, Any]]
    official_validation: str
    type_code: str | None = None
    corrects_invoice_id: uuid.UUID | None = None
    profile: str | None = None
    guideline_id: str | None = None
    attachment_name: str | None = None
    pdfa: dict[str, Any] | None = None


class AccountingZugferdStoredOut(RawJsonOut):
    document_id: uuid.UUID
    created: bool
    check: dict[str, Any] | None = None
