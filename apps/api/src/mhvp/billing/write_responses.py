"""AL04 (GAI-304): typed responses of writing billing routes without money amounts.

``extra="allow"`` keeps fields a handler adds later (no silent field loss). Routes that
return amounts stay untyped until the JSON format of Decimal amounts is decided (AK11).
"""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class BillingAllocationBasisSettingOut(_Open):
    block_output: bool


class BillingIdOut(_Open):
    id: uuid.UUID


class BillingHeatingRuleTableOut(_Open):
    id: uuid.UUID
    kind: str
    valid_from: date


class BillingConsumptionInfoRunOut(_Open):
    month: date


class BillingConsumptionInfoSettingsOut(_Open):
    property_id: uuid.UUID
    enabled: bool
    tenant_enabled: bool
    notifications_enabled: bool
    template_verified: bool
    rule_version: str


class BillingResultEntriesOut(_Open):
    statement_id: uuid.UUID
    entry_ids: list[uuid.UUID]
    status: str


class BillingInspectionOut(_Open):
    id: uuid.UUID
    statement_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    requested_at: datetime | date | None = None
    channel: str | None = None
    scope: str | None = None
    status: str
    provision: str | None = None
    provided_at: datetime | date | None = None
    document_ids: list[Any] | None = None
    redaction_note: str | None = None
    objection_received_at: datetime | date | None = None
    objection_text: str | None = None
    note: str | None = None


class BillingDeadlineSettingOut(_Open):
    policy: str
    watch_enabled: bool
    warn_days_first: int | None = None
    warn_days_second: int | None = None
    notice: str


class BillingAdvanceRuleOut(_Open):
    surcharge_percent: str
    months: int
    rule_version: str
    formula: str
    open_advance_mode: str
    open_advance_modes: list[str]
    open_advance_decision: str


class BillingAiCheckStateOut(_Open):
    statement_id: uuid.UUID
    latest_run: dict[str, Any] | None = None
    latest: dict[str, Any] | None = None
    proposals: list[dict[str, Any]]


class BillingInfoSheetFiledOut(_Open):
    statement_id: uuid.UUID
    document_id: uuid.UUID
    snapshot_hash: str | None = None
    text_status: str
    texts_status: dict[str, Any] | list[Any] | None = None


class BillingOwnerOutputsFiledOut(_Open):
    statement_id: uuid.UUID
    items: list[dict[str, Any]]
    text_status: str
    texts_status: dict[str, Any] | list[Any] | None = None
