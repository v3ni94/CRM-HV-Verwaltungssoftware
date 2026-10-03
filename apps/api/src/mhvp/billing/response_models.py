"""AN11 (GAI-304): documented responses of billing routes that return money amounts.

Each model only documents and validates; the JSON bytes stay what the handler returned
(``RawJsonOut``, ADR 0037: ``Decimal`` is serialized as a JSON string).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mhvp.accounting.write_responses import RawJsonOut


class BillingHeatingCostImportOut(RawJsonOut):
    id: uuid.UUID
    property_id: uuid.UUID
    statement_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    provider_name: str
    period_from: date
    period_to: date
    document_total: Decimal
    co2: dict[str, Any] | None = None
    user_mapping: dict[str, Any] | None = None
    rows: list[Any] | None = None
    csv_meta: dict[str, Any] | None = None
    status: str
    check_result: dict[str, Any] | None = None
    duplicate_ack_reason: str | None = None
    checked_by: uuid.UUID | None = None
    checked_at: datetime | None = None
    applied_item_id: uuid.UUID | None = None
    applied_at: datetime | None = None
    item: dict[str, Any] | None = None


class BillingOwnerStatementOut(RawJsonOut):
    id: uuid.UUID
    kind: str
    ledger_id: uuid.UUID
    legal_entity_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    period_from: date
    period_to: date
    status: str
    rule_version: str | None = None
    snapshot_hash: str | None = None
    calculated_at: datetime | None = None
    approved_at: datetime | None = None
    approved_by: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    status_log: list[Any] | None = None
    posted_entry_ids: list[Any] | None = None
    attach_receipts: bool | None = None
    results: Any = None
    findings: list[Any] | None = None
    settlement: Any = None


class BillingOwnerStatementOutputsOut(RawJsonOut):
    statement_id: uuid.UUID
    items: list[Any]
