"""AP22 (GAI-304, ADR 0037): documented accounting responses that keep their bytes unchanged.

Generated from the observed handler results of the integration tests (generator in the AO08
and AP22 work notes). Every model is a ``TolerantRawJsonOut``: the declared fields document
the response for OpenAPI, the handler value is delivered unchanged, a mismatch is only logged.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mhvp.accounting.write_responses import TolerantRawJsonOut as _DocOut


class AccountingAdminFeesPeriodPreviewOut(_DocOut):
    period_date: date | None = None
    rows: list[dict[str, Any]] | None = None


class AccountingDunningBlockListItemOut(_DocOut):
    pass


class AccountingDunningListDeliveryProofsOutItem(_DocOut):
    id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    kind: str | None = None
    proof_date: date | None = None
    reference: str | None = None
    document_id: Any = None
    note: Any = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None


class AccountingDunningInterestRatesOutItem(_DocOut):
    id: uuid.UUID | None = None
    valid_from: date | None = None
    base_rate: Decimal | None = None
    source: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    valid_to: date | None = None


class AccountingDunningRunsItemOut(_DocOut):
    pass


class AccountingDunningRunOut(_DocOut):
    id: uuid.UUID | None = None
    run_date: date | None = None
    status: str | None = None
    totals: dict[str, Any] | None = None
    cases: list[dict[str, Any]] | None = None


class AccountingGetDunningSettingsOut(_DocOut):
    id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    levels: list[dict[str, Any]] | None = None
    threshold_amount: Decimal | None = None
    fee_from_level: int | None = None
    interest_enabled: bool | None = None
    interest_base_rate: Any = None
    interest_spread: Decimal | None = None
    default_start_mode: Any = None
    default_start_modes: dict[str, Any] | None = None
    status: str | None = None
    sources: dict[str, Any] | None = None
    own: dict[str, Any] | None = None
    tenant_default_exists: bool | None = None


class AccountingListDunningOverridesOutItem(_DocOut):
    id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    overridden_fields: list[str] | None = None


class AccountingListInvoicesOutItem(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: Any = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: Any = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Any = None
    discount_until: Any = None
    payee_iban_suffix: str | None = None
    iban_confirmed: bool | None = None
    document_id: Any = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: Any = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: Any = None
    service_to: Any = None
    order_reference: Any = None
    service_contract_id: Any = None
    work_order_id: Any = None
    resolution_id: Any = None
    plan_item_id: Any = None
    recurring_plan_id: Any = None
    reference_invoice_id: Any = None
    service_place: Any = None
    issuer_vat_id: Any = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Any = None
    discount_expected: Any = None
    prepaid_amount: Any = None
    retention_amount: Any = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[Any] | None = None
    lines: list[Any] | None = None
    reviews: list[Any] | None = None


class AccountingGetInvoiceOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: Any = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: Any = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Any = None
    discount_until: Any = None
    payee_iban_suffix: str | None = None
    iban_confirmed: bool | None = None
    document_id: Any = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: Any = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: date | None = None
    service_to: date | None = None
    order_reference: Any = None
    service_contract_id: Any = None
    work_order_id: uuid.UUID | None = None
    resolution_id: Any = None
    plan_item_id: Any = None
    recurring_plan_id: Any = None
    reference_invoice_id: Any = None
    service_place: str | None = None
    issuer_vat_id: str | None = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Any = None
    discount_expected: Any = None
    prepaid_amount: Any = None
    retention_amount: Any = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    reviews: list[Any] | None = None


class AccountingInvoiceDiscountOut(_DocOut):
    discount: Decimal | None = None
    payable: Decimal | None = None


class AccountingChecksOut(_DocOut):
    ok: bool | None = None
    findings: list[Any] | None = None
    bank_ok: bool | None = None
    bank_findings: list[str] | None = None
    exclude_written_off: bool | None = None
    excluded: dict[str, Any] | None = None
    subledger: list[dict[str, Any]] | None = None
    subledger_differences: list[dict[str, Any]] | None = None
    constraint_ok: bool | None = None
    constraint_findings: list[dict[str, Any]] | None = None


class AccountingCreditorOpenItemsOutItem(_DocOut):
    id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    account_number: str | None = None
    kind: str | None = None
    journal_entry_id: uuid.UUID | None = None
    booking_date: date | None = None
    due_date: date | None = None
    amount: Decimal | None = None
    remaining: Decimal | None = None
    contract_id: Any = None
    notice_received_on: Any = None


class AccountingCreditorStatementOut(_DocOut):
    account_id: uuid.UUID | None = None
    number: str | None = None
    name: str | None = None
    start: date | None = None
    end: date | None = None
    opening_balance: Decimal | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    closing_balance: Decimal | None = None
    movements: list[dict[str, Any]] | None = None


class AccountingLiquidityOut(_DocOut):
    ledger_id: uuid.UUID | None = None
    as_of: date | None = None
    horizon: date | None = None
    accounts: list[dict[str, Any]] | None = None
    free_funds: Decimal | None = None
    reserve_funds: Decimal | None = None
    segregated_deposits: Decimal | None = None
    expected_inflows: Decimal | None = None
    expected_outflows: Decimal | None = None
    debtor_credits: Decimal | None = None
    projected_free_funds: Decimal | None = None
    note: str | None = None


class AccountingPaymentsByDebtorOutItem(_DocOut):
    number: str | None = None
    name: str | None = None
    settled: Decimal | None = None


class AccountingRevenueOutItem(_DocOut):
    number: str | None = None
    name: str | None = None
    amount: Decimal | None = None


class AccountingYearCarryoverPreviewOut(_DocOut):
    fiscal_year: int | None = None
    start: date | None = None
    end: date | None = None
    target_date: date | None = None
    carried: list[dict[str, Any]] | None = None
    not_carried: list[dict[str, Any]] | None = None
    already_drafted: bool | None = None
    note: str | None = None


class AccountingListRunsOutItem(_DocOut):
    id: uuid.UUID | None = None
    period_month: date | None = None
    scope: str | None = None
    scope_id: uuid.UUID | None = None
    status: str | None = None
    totals: dict[str, Any] | None = None
    created_at: datetime | None = None
    created_by: uuid.UUID | None = None
    posted_at: datetime | None = None


class AccountingGetRunOut(_DocOut):
    id: uuid.UUID | None = None
    period_month: date | None = None
    scope: str | None = None
    status: str | None = None
    totals: dict[str, Any] | None = None
    posted_at: datetime | None = None
    items: list[dict[str, Any]] | None = None
    calculation: dict[str, Any] | None = None


class AccountingFeeIssueOut(_DocOut):
    lines: list[dict[str, Any]] | None = None
    net: str | None = None
    vat_percent: str | None = None
    vat: str | None = None
    gross: str | None = None
    status: str | None = None
    invoice_debtor_party_id: Any = None
    debtor_legal_entity_id: str | None = None
    debtor_legal_entity_kind: str | None = None
    payee_role: str | None = None
    payee_party_id: Any = None
    id: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: Any = None
    xrechnung_url: str | None = None


class AccountingDunningInterestDraftOut(_DocOut):
    case_id: uuid.UUID | None = None
    entry_id: uuid.UUID | None = None
    status: Any = None
    amount: Decimal | None = None
    interest_detail: list[dict[str, Any]] | None = None
    hinweis: str | None = None


class AccountingDunningLetterCreateOut(_DocOut):
    ledger_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    property_number: str | None = None
    due_date: date | None = None
    default_start: Any = None
    default_mode: Any = None
    default_mode_label: Any = None
    received_on: Any = None
    bank_account: dict[str, Any] | None = None
    bank_warning: Any = None
    id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    debtor_account_id: uuid.UUID | None = None
    level: int | None = None
    total: Decimal | None = None
    fee_amount: Decimal | None = None
    interest_amount: Decimal | None = None
    status: str | None = None
    reason: str | None = None
    open_items: list[dict[str, Any]] | None = None
    fee_entry_id: Any = None
    fee_invoice_draft_id: Any = None
    delivery_channel: Any = None
    delivered_at: Any = None
    letter_document_id: uuid.UUID | None = None
    warnings: list[str] | None = None
    interest_detail: Any = None
    interest_entry_id: Any = None
    interest_spread_suggestion: dict[str, Any] | None = None
    check_hints: list[str] | None = None
    delivery_proofs: list[Any] | None = None
    hinweis: str | None = None
    letter_warnings: list[str] | None = None


class AccountingDunningMahnbescheidCreateOut(_DocOut):
    id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    antragsteller_legal_entity_id: uuid.UUID | None = None
    antragsgegner: dict[str, Any] | None = None
    hauptforderung: Decimal | None = None
    nebenforderungen: list[dict[str, Any]] | None = None
    zustelladresse: dict[str, Any] | None = None
    aktenzeichen_intern: str | None = None
    status: str | None = None
    hinweis: str | None = None
    document_id: uuid.UUID | None = None


class AccountingDunningPrepareMahnbescheidOut(_DocOut):
    id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    antragsteller_legal_entity_id: uuid.UUID | None = None
    antragsgegner: dict[str, Any] | None = None
    hauptforderung: Decimal | None = None
    nebenforderungen: list[dict[str, Any]] | None = None
    zustelladresse: dict[str, Any] | None = None
    aktenzeichen_intern: str | None = None
    status: str | None = None
    hinweis: str | None = None


class AccountingDunningMarkSentOut(_DocOut):
    ledger_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    property_number: str | None = None
    due_date: date | None = None
    default_start: date | None = None
    default_mode: str | None = None
    default_mode_label: str | None = None
    received_on: Any = None
    bank_account: dict[str, Any] | None = None
    bank_warning: str | None = None
    id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    debtor_account_id: uuid.UUID | None = None
    level: int | None = None
    total: Decimal | None = None
    fee_amount: Decimal | None = None
    interest_amount: Decimal | None = None
    status: str | None = None
    reason: str | None = None
    open_items: list[dict[str, Any]] | None = None
    fee_entry_id: uuid.UUID | None = None
    fee_invoice_draft_id: Any = None
    delivery_channel: str | None = None
    delivered_at: datetime | None = None
    letter_document_id: Any = None
    warnings: list[str] | None = None
    interest_detail: Any = None
    interest_entry_id: Any = None
    interest_spread_suggestion: dict[str, Any] | None = None
    check_hints: list[str] | None = None
    delivery_proofs: list[Any] | None = None


class AccountingDunningInterestRateCreateOut(_DocOut):
    id: uuid.UUID | None = None
    valid_from: date | None = None
    base_rate: Decimal | None = None
    source: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None


class AccountingDunningPreviewOut(_DocOut):
    id: uuid.UUID | None = None
    run_date: date | None = None
    status: str | None = None
    totals: dict[str, Any] | None = None
    cases: list[dict[str, Any]] | None = None


class AccountingDunningApproveOut(_DocOut):
    id: uuid.UUID | None = None
    run_date: date | None = None
    status: str | None = None
    totals: dict[str, Any] | None = None
    cases: list[dict[str, Any]] | None = None


class AccountingDunningLetterTextPreviewOut(_DocOut):
    level: int | None = None
    letter_date: date | None = None
    paragraphs: list[str] | None = None
    table: dict[str, Any] | None = None
    standard_request: str | None = None
    placeholders: dict[str, Any] | None = None
    hinweis: str | None = None


class AccountingPostDunningSettingsPresetsOut(_DocOut):
    id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    levels: list[dict[str, Any]] | None = None
    threshold_amount: Decimal | None = None
    fee_from_level: int | None = None
    interest_enabled: bool | None = None
    interest_base_rate: Any = None
    interest_spread: Any = None
    default_start_mode: Any = None
    default_start_modes: dict[str, Any] | None = None
    status: str | None = None
    sources: dict[str, Any] | None = None
    own: dict[str, Any] | None = None
    tenant_default_exists: bool | None = None
    note: str | None = None


class AccountingCreateInvoiceOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: Any = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Decimal | None = None
    discount_until: date | None = None
    payee_iban_suffix: str | None = None
    iban_confirmed: bool | None = None
    document_id: uuid.UUID | None = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: Any = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: date | None = None
    service_to: date | None = None
    order_reference: str | None = None
    service_contract_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    resolution_id: uuid.UUID | None = None
    plan_item_id: uuid.UUID | None = None
    recurring_plan_id: uuid.UUID | None = None
    reference_invoice_id: uuid.UUID | None = None
    service_place: str | None = None
    issuer_vat_id: str | None = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Decimal | None = None
    discount_expected: Decimal | None = None
    prepaid_amount: Decimal | None = None
    retention_amount: Decimal | None = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    reviews: list[Any] | None = None


class AccountingPostInvoiceOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: uuid.UUID | None = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Any = None
    discount_until: Any = None
    payee_iban_suffix: str | None = None
    iban_confirmed: bool | None = None
    document_id: Any = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: uuid.UUID | None = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: date | None = None
    service_to: date | None = None
    order_reference: str | None = None
    service_contract_id: Any = None
    work_order_id: Any = None
    resolution_id: Any = None
    plan_item_id: Any = None
    recurring_plan_id: Any = None
    reference_invoice_id: Any = None
    service_place: str | None = None
    issuer_vat_id: str | None = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Any = None
    discount_expected: Any = None
    prepaid_amount: Any = None
    retention_amount: Any = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    reviews: list[dict[str, Any]] | None = None


class AccountingReleaseInvoiceOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: Any = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Any = None
    discount_until: Any = None
    payee_iban_suffix: str | None = None
    iban_confirmed: bool | None = None
    document_id: Any = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: Any = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: date | None = None
    service_to: date | None = None
    order_reference: str | None = None
    service_contract_id: Any = None
    work_order_id: Any = None
    resolution_id: Any = None
    plan_item_id: Any = None
    recurring_plan_id: Any = None
    reference_invoice_id: uuid.UUID | None = None
    service_place: str | None = None
    issuer_vat_id: str | None = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Any = None
    discount_expected: Any = None
    prepaid_amount: Any = None
    retention_amount: Any = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    reviews: list[dict[str, Any]] | None = None


class AccountingReviewInvoiceOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: Any = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Any = None
    discount_until: Any = None
    payee_iban_suffix: str | None = None
    iban_confirmed: bool | None = None
    document_id: Any = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: Any = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: date | None = None
    service_to: date | None = None
    order_reference: str | None = None
    service_contract_id: Any = None
    work_order_id: Any = None
    resolution_id: Any = None
    plan_item_id: Any = None
    recurring_plan_id: Any = None
    reference_invoice_id: uuid.UUID | None = None
    service_place: str | None = None
    issuer_vat_id: str | None = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Any = None
    discount_expected: Any = None
    prepaid_amount: Any = None
    retention_amount: Any = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    reviews: list[dict[str, Any]] | None = None


class AccountingPreviewRunOut(_DocOut):
    id: uuid.UUID | None = None
    period_month: date | None = None
    scope: str | None = None
    status: str | None = None
    totals: dict[str, Any] | None = None
    posted_at: Any = None
    items: list[dict[str, Any]] | None = None
    calculation: dict[str, Any] | None = None


class AccountingPostRunOut(_DocOut):
    id: uuid.UUID | None = None
    period_month: date | None = None
    scope: str | None = None
    status: str | None = None
    totals: dict[str, Any] | None = None
    posted_at: datetime | None = None
    items: list[dict[str, Any]] | None = None
    calculation: dict[str, Any] | None = None


class AccountingGeneratePlanOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: Any = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Any = None
    discount_until: Any = None
    payee_iban_suffix: Any = None
    iban_confirmed: bool | None = None
    document_id: Any = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: Any = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: date | None = None
    service_to: date | None = None
    order_reference: str | None = None
    service_contract_id: Any = None
    work_order_id: Any = None
    resolution_id: Any = None
    plan_item_id: Any = None
    recurring_plan_id: uuid.UUID | None = None
    reference_invoice_id: Any = None
    service_place: Any = None
    issuer_vat_id: Any = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Any = None
    discount_expected: Any = None
    prepaid_amount: Any = None
    retention_amount: Any = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    reviews: list[Any] | None = None
    draft_number: bool | None = None
    g1_open: bool | None = None
    auto_post_requested: bool | None = None
    auto_post_state: str | None = None


class AccountingPutDunningSettingsOut(_DocOut):
    id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    levels: list[dict[str, Any]] | None = None
    threshold_amount: Decimal | None = None
    fee_from_level: int | None = None
    interest_enabled: bool | None = None
    interest_base_rate: Decimal | None = None
    interest_spread: Decimal | None = None
    default_start_mode: str | None = None
    default_start_modes: dict[str, Any] | None = None
    status: str | None = None
    sources: dict[str, Any] | None = None
    own: dict[str, Any] | None = None
    tenant_default_exists: bool | None = None


class AccountingUpdateInvoiceOut(_DocOut):
    id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    creditor_account_id: Any = None
    kind: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    discount_percent: Any = None
    discount_until: Any = None
    payee_iban_suffix: str | None = None
    iban_confirmed: bool | None = None
    document_id: uuid.UUID | None = None
    deductions: list[Any] | None = None
    review_status: str | None = None
    posting_status: str | None = None
    released: bool | None = None
    duplicate_of_id: Any = None
    supersedes_id: Any = None
    journal_entry_id: Any = None
    version: int | None = None
    findings: list[str] | None = None
    service_from: date | None = None
    service_to: Any = None
    order_reference: Any = None
    service_contract_id: Any = None
    work_order_id: Any = None
    resolution_id: Any = None
    plan_item_id: Any = None
    recurring_plan_id: Any = None
    reference_invoice_id: Any = None
    service_place: Any = None
    issuer_vat_id: Any = None
    issuer_tax_number: Any = None
    attachment_document_ids: list[Any] | None = None
    discount_amount: Any = None
    discount_expected: Any = None
    prepaid_amount: Any = None
    retention_amount: Any = None
    payable_amount: Decimal | None = None
    reverse_charge: bool | None = None
    construction_withholding: bool | None = None
    input_tax_deductible: Any = None
    mandatory_checklist: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    reviews: list[dict[str, Any]] | None = None
