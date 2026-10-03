"""AP22 (GAI-304, ADR 0037): documented billing responses that keep their bytes unchanged.

Generated from the observed handler results of the integration tests (generator in the AO08
and AP22 work notes). Every model is a ``TolerantRawJsonOut``: the declared fields document
the response for OpenAPI, the handler value is delivered unchanged, a mismatch is only logged.
"""

import uuid
from datetime import date
from typing import Any

from mhvp.accounting.write_responses import TolerantRawJsonOut as _DocOut


class BillingAdvanceGetRuleOut(_DocOut):
    surcharge_percent: str | None = None
    months: int | None = None
    rule_version: str | None = None
    formula: str | None = None
    open_advance_mode: str | None = None
    open_advance_modes: list[str] | None = None
    open_advance_decision: str | None = None


class BillingAllocationBasisGetSettingOut(_DocOut):
    block_output: bool | None = None


class BillingDeadlineGetSettingsOut(_DocOut):
    policy: str | None = None
    watch_enabled: bool | None = None
    warn_days_first: int | None = None
    warn_days_second: int | None = None
    notice: str | None = None


class BillingHeatingListRuleTablesOutItem(_DocOut):
    id: uuid.UUID | None = None
    kind: str | None = None
    valid_from: date | None = None
    rows: dict[str, Any] | None = None
    source: str | None = None
    review_status: str | None = None
    note: Any = None


class BillingAllocabilityListCatalogueOut(_DocOut):
    source: str | None = None
    items: list[dict[str, Any]] | None = None


class BillingAllocabilityListAccountsOutItem(_DocOut):
    account_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    number: str | None = None
    name: str | None = None
    allocation_category: str | None = None
    operating_cost_type: Any = None
    operating_cost_type_label: Any = None
    allocability: Any = None
    suggested_operating_cost_type: Any = None


class BillingAllocabilityMapAccountOut(_DocOut):
    account_id: uuid.UUID | None = None
    ledger_id: uuid.UUID | None = None
    number: str | None = None
    name: str | None = None
    allocation_category: str | None = None
    operating_cost_type: str | None = None
    operating_cost_type_label: str | None = None
    allocability: str | None = None
    suggested_operating_cost_type: Any = None
