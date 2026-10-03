"""AP22 (GAI-304, ADR 0037): documented banking responses that keep their bytes unchanged.

Generated from the observed handler results of the integration tests (generator in the AO08
and AP22 work notes). Every model is a ``TolerantRawJsonOut``: the declared fields document
the response for OpenAPI, the handler value is delivered unchanged, a mismatch is only logged.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mhvp.accounting.write_responses import TolerantRawJsonOut as _DocOut


class BankingReconciliationOutItem(_DocOut):
    statement_id: uuid.UUID | None = None
    statement_ref: str | None = None
    closing_date: date | None = None
    opening_balance: Decimal | None = None
    movements: Decimal | None = None
    closing_balance: Decimal | None = None
    statement_difference: Decimal | None = None
    ledger_balance: Decimal | None = None
    ledger_difference: Decimal | None = None
    date_basis: str | None = None
    ledger_status: str | None = None
    ledger_account_number: str | None = None
    timing_difference: Decimal | None = None
    from_date: Any = None
    to_date: Any = None
    status: str | None = None
    chain_status: str | None = None
    chain_difference: Any = None
    period_status: str | None = None
    gap_from: Any = None
    gap_to: Any = None


class BankingListReviewsOutItem(_DocOut):
    id: uuid.UUID | None = None
    posting_decision_id: uuid.UUID | None = None
    bank_transaction_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    journal_entry_id: uuid.UUID | None = None
    journal_number: str | None = None
    ledger_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    case_kind: str | None = None
    kind: str | None = None
    due_on: date | None = None
    overdue: bool | None = None
    status: str | None = None
    note: Any = None
    reviewed_by: Any = None
    reviewed_at: Any = None
    booking_date: date | None = None
    amount: Decimal | None = None
    counterpart_name: str | None = None
    purpose: str | None = None
    final: dict[str, Any] | None = None
    verifier_fingerprint: str | None = None
    reversed: bool | None = None
    return_transaction_id: uuid.UUID | None = None


class BankingAutomationComparisonOut(_DocOut):
    date_from: date | None = None
    date_to: date | None = None
    outcomes: list[str] | None = None
    totals: dict[str, Any] | None = None
    by_case_kind: dict[str, Any] | None = None
    compared_bookings: int | None = None
    match_rate: Any = None
    rows: list[Any] | None = None
    note: str | None = None


class BankingAutomationMetricsOut(_DocOut):
    window_from: date | None = None
    window_to: date | None = None
    levels: dict[str, Any] | None = None
    classes: list[dict[str, Any]] | None = None
    note: str | None = None


class BankingListClarificationsOutItem(_DocOut):
    id: uuid.UUID | None = None
    bank_transaction_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    status: str | None = None
    reasons: list[str] | None = None
    rule_id: Any = None
    reason: str | None = None
    document_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None
    assignee_user_id: Any = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None
    age_days: int | None = None
    booking_date: date | None = None
    amount: Decimal | None = None
    counterpart_name: str | None = None
    purpose: str | None = None
    transaction_status: str | None = None


class BankingListRuleProposalsOutItem(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    pattern_key: str | None = None
    status: str | None = None
    direction: str | None = None
    case_kind: str | None = None
    has_iban_key: bool | None = None
    creditor_id: Any = None
    account_number: str | None = None
    account_id: uuid.UUID | None = None
    action_kind: str | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    purpose_tokens: list[str] | None = None
    recurring: bool | None = None
    threshold: int | None = None
    evidence: dict[str, Any] | None = None
    evidence_count: Decimal | None = None
    reason: str | None = None
    rule_id: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None


class BankingTransactionsItemOut(_DocOut):
    pass


class BankingGetAiPostingOut(_DocOut):
    bank_transaction_id: uuid.UUID | None = None
    proposals: list[Any] | None = None
    note: str | None = None


class BankingTxCandidatesOut(_DocOut):
    candidates: list[dict[str, Any]] | None = None
    unambiguous_open_item_id: Any = None
    note: str | None = None


class BankingPostingProposalsOut(_DocOut):
    bank_transaction_id: uuid.UUID | None = None
    amount: Decimal | None = None
    ledger_id: uuid.UUID | None = None
    stage1: list[dict[str, Any]] | None = None
    ai: list[Any] | None = None
    ai_stage: dict[str, Any] | None = None
    learning: dict[str, Any] | None = None
    object_period_lock: dict[str, Any] | None = None
    note: str | None = None


class BankingDecideReviewOut(_DocOut):
    id: uuid.UUID | None = None
    posting_decision_id: uuid.UUID | None = None
    bank_transaction_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    journal_entry_id: uuid.UUID | None = None
    journal_number: str | None = None
    ledger_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    case_kind: str | None = None
    kind: str | None = None
    due_on: date | None = None
    overdue: bool | None = None
    status: str | None = None
    note: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    booking_date: date | None = None
    amount: Decimal | None = None
    counterpart_name: str | None = None
    purpose: str | None = None
    final: dict[str, Any] | None = None
    verifier_fingerprint: str | None = None
    reversed: bool | None = None
    return_transaction_id: Any = None


class BankingBulkConfirmOut(_DocOut):
    preview: bool | None = None
    count: int | None = None
    total: str | None = None
    legal_entities: list[str] | None = None
    exceptions: list[str] | None = None
    totals_by_legal_entity: list[dict[str, Any]] | None = None
    preview_id: str | None = None
    preview_expires_at: str | None = None
    bookable_count: int | None = None
    bookable_transaction_ids: list[str] | None = None
    allocations: dict[str, Any] | None = None
    results: list[dict[str, Any]] | None = None


class BankingDecideClarificationOut(_DocOut):
    id: uuid.UUID | None = None
    bank_transaction_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    status: str | None = None
    reasons: list[str] | None = None
    rule_id: Any = None
    reason: str | None = None
    document_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None
    assignee_user_id: Any = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None
    age_days: int | None = None
    booking_date: date | None = None
    amount: Decimal | None = None
    counterpart_name: str | None = None
    purpose: str | None = None
    transaction_status: str | None = None


class BankingRejectRuleProposalOut(_DocOut):
    id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    pattern_key: str | None = None
    status: str | None = None
    direction: str | None = None
    case_kind: str | None = None
    has_iban_key: bool | None = None
    creditor_id: Any = None
    account_number: str | None = None
    account_id: uuid.UUID | None = None
    action_kind: str | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    purpose_tokens: list[str] | None = None
    recurring: bool | None = None
    threshold: int | None = None
    evidence: dict[str, Any] | None = None
    evidence_count: Decimal | None = None
    reason: str | None = None
    rule_id: Any = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None


class BankingAcceptProposalOut(_DocOut):
    journal_entry_id: uuid.UUID | None = None
    number: str | None = None
    case_kind: str | None = None
    level: str | None = None
    chosen: int | None = None


class BankingStartAiPostingOut(_DocOut):
    bank_transaction_id: uuid.UUID | None = None
    proposals: list[dict[str, Any]] | None = None
    note: str | None = None


class BankingBookOut(_DocOut):
    journal_entry_id: uuid.UUID | None = None
    number: str | None = None


class BankingOpenClarificationOut(_DocOut):
    id: uuid.UUID | None = None
    bank_transaction_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    status: str | None = None
    reasons: list[str] | None = None
    rule_id: Any = None
    reason: Any = None
    document_id: Any = None
    ticket_id: uuid.UUID | None = None
    assignee_user_id: Any = None
    decided_by: Any = None
    decided_at: Any = None
    created_at: datetime | None = None
    age_days: int | None = None
    booking_date: date | None = None
    amount: Decimal | None = None
    counterpart_name: str | None = None
    purpose: str | None = None
    transaction_status: str | None = None


class BankingCorrectTransactionOut(_DocOut):
    reversal_id: uuid.UUID | None = None
    reversal_number: str | None = None
    journal_entry_id: uuid.UUID | None = None
    number: str | None = None


class BankingLowerLevelOut(_DocOut):
    debtor_full: str | None = None
    debtor_collective: str | None = None
    creditor_invoice: str | None = None
    recurring_expense: str | None = None
    transfer_pair: str | None = None
    excluded: str | None = None
