"""Request/response schemas for /integrations/lexoffice (M13-lexoffice)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LexofficeConfigIn(_In):
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    base_url: str | None = Field(default=None, max_length=300)
    enabled: bool = False


class LexofficeConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: uuid.UUID
    base_url: str
    enabled: bool
    api_key_set: bool
    last_tested_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None


class LexofficeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    status: str
    counts: dict[str, int]
    errors: list[str]
    created_at: datetime
    finished_at: datetime | None


class LexofficeExportInvoiceItem(_In):
    invoice_id: uuid.UUID
    # Finished lexoffice voucher payload for this invoice (POST /v1/vouchers body), built and
    # reviewed outside this endpoint (docs/integrations/lexoffice.md, "offene Punkte": the exact
    # purchase-voucher schema is not fully documented, so this module never builds it itself).
    payload: dict[str, Any]
    force: bool = False


class LexofficeExportInvoicesIn(_In):
    items: list[LexofficeExportInvoiceItem] = Field(min_length=1, max_length=200)


class LexofficeExportContactItem(_In):
    contact_id: uuid.UUID
    payload: dict[str, Any]
    force: bool = False


class LexofficeExportContactsIn(_In):
    items: list[LexofficeExportContactItem] = Field(min_length=1, max_length=200)


class LexofficeExportResultItem(BaseModel):
    entity_id: uuid.UUID
    ok: bool
    lexoffice_id: str | None = None
    error: str | None = None
    skipped_duplicate: bool = False


class LexofficeExportResult(BaseModel):
    run_id: uuid.UUID
    items: list[LexofficeExportResultItem]


class LexofficeImportReceiptsIn(_In):
    updated_at_from: datetime | None = None
    max_pages: int = Field(default=1, ge=1, le=20)


class LexofficeImportedItem(BaseModel):
    lexoffice_voucher_id: str
    ok: bool
    receipt_draft_id: uuid.UUID | None = None
    duplicate: bool = False
    error: str | None = None


class LexofficeImportResult(BaseModel):
    run_id: uuid.UUID
    items: list[LexofficeImportedItem]
