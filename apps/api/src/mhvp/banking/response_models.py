"""AN11 (GAI-304): documented responses of banking routes, several of them with amounts.

Each model only documents and validates; the JSON bytes stay what the handler returned
(``RawJsonOut``, ADR 0037: ``Decimal`` is serialized as a JSON string).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mhvp.accounting.write_responses import RawJsonOut


class BankingSwitchStateOut(RawJsonOut):
    enabled: bool


class BankingSwitchRequestOut(RawJsonOut):
    id: uuid.UUID
    reason: str
    target: str
    status: str
    requested_by: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_comment: str | None = None
    created_at: datetime | None = None


class BankingSwitchRequestListOut(RawJsonOut):
    enabled: bool
    outgoing_enabled: bool
    g1_open: bool
    can_request: bool
    can_request_outgoing: bool
    items: list[BankingSwitchRequestOut]


class BankingLearningOut(RawJsonOut):
    enabled: bool
    engine_version: str | int | None = None
    rule_version: str | int | None = None
    note: str | None = None


class BankingLevelRequestOut(RawJsonOut):
    id: uuid.UUID
    case_kind: str
    level_from: str
    level_to: str
    reason: str
    evidence: dict[str, Any] | None = None
    status: str
    requested_by: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_comment: str | None = None
    created_at: datetime | None = None


class BankingLevelsOut(RawJsonOut):
    levels: dict[str, Any]
    caps: dict[str, Any] | None = None
    labels: dict[str, Any] | None = None
    auto_posting_enabled: bool
    auto_posting_outgoing_enabled: bool
    learning_enabled: bool
    blocked: Any = None
    thresholds: dict[str, Any] | None = None
    requests: list[BankingLevelRequestOut]
    note: str | None = None


class BankingMatchingMetricsOut(RawJsonOut):
    period_from: date | None = None
    period_to: date | None = None
    transactions: int
    incoming: int
    auto_matched: int
    manual_booked: int
    open: int
    ignored: int
    coverage: Decimal | None = None
    auto_reversed: int
    auto_corrected: int
    auto_cancelled: int
    error_rate: Decimal | None = None
    note: str | None = None


class BankingAutoMetricsOut(RawJsonOut):
    incoming: int
    auto_booked: int
    coverage: float | None = None
    auto_reversed: int
    error_rate: float | None = None


class BankingAutoPostRunOut(RawJsonOut):
    enabled: bool
    posted: Any = None


class BankingPaymentBatchOut(RawJsonOut):
    id: uuid.UUID
    message_id: str
    format: str
    status: str
    property_bank_account_id: uuid.UUID | None = None
    transaction_count: int
    control_sum: str
    file_sha256: str | None = None
    document_id: uuid.UUID | None = None
    submission_channel: str | None = None
    submission_reference: str | None = None
    submitted_at: datetime | None = None
    submitted_by: uuid.UUID | None = None
    created_at: datetime | None = None


class BankingPaymentBatchCreatedOut(BankingPaymentBatchOut):
    xml: str


class BankingPaymentBatchSubmittedOut(BankingPaymentBatchOut):
    channel: str | None = None
    submitted: bool | None = None


class BankingPaymentBatchDownloadOut(RawJsonOut):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    downloaded_at: datetime | None = None
    file_sha256: str | None = None
    purpose: str | None = None


class BankingPaymentBatchDetailOut(BankingPaymentBatchOut):
    downloads: list[BankingPaymentBatchDownloadOut]


class BankingPaymentBankConfigOut(RawJsonOut):
    property_bank_account_id: uuid.UUID
    pain001_version: str | None = None
    pain008_version: str | None = None
    submission_channel: str | None = None
    confirmed_with_bank_on: date | None = None
    notes: str | None = None
    supported: dict[str, list[str]]
