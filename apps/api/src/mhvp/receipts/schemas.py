"""API schemas of the Belegeingang (M14)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mhvp.ai.schemas import InvoiceApplyIn


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReceiptDraftFromDocumentIn(_In):
    document_id: uuid.UUID
    source: Literal["upload", "mail_attachment"] = "upload"
    message_id: uuid.UUID | None = Field(
        default=None, description="Pflicht bei source=mail_attachment: Nachricht des Anhangs"
    )


class ReceiptDraftFromPaperlessIn(_In):
    paperless_document_id: int = Field(ge=1)


class ReceiptFieldOut(BaseModel):
    value: str | None
    confidence: float = Field(ge=0, le=1)
    source: Literal["ai", "local", "none"]
    note: str | None = None


class ReceiptIbanCandidateOut(BaseModel):
    masked: str
    checksum_ok: bool
    source: Literal["local"]


class ReceiptDraftOut(_Out):
    id: uuid.UUID
    document_id: uuid.UUID
    source: str
    message_id: uuid.UUID | None
    task_run_id: uuid.UUID | None
    status: str
    fields: dict[str, ReceiptFieldOut]
    iban_candidates: list[ReceiptIbanCandidateOut] = Field(default_factory=list)
    supplier_candidates: list[dict[str, Any]]
    property_suggestions: list[dict[str, Any]]
    warnings: list[str]
    questions: list[str]
    masked_excerpt: str | None
    error: str | None
    invoice_id: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReceiptDraftListOut(BaseModel):
    items: list[ReceiptDraftOut]
    total: int


class ReceiptConfirmIn(_In):
    """Reviewed values. ``invoice`` is what the reviewer confirmed; an IBAN is accepted only
    together with ``iban_confirmed=true`` (rule 0.1.6: no IBAN from a proposal without a
    human confirmation)."""

    invoice: InvoiceApplyIn
    iban_confirmed: bool = False
    note: str | None = Field(default=None, max_length=1000)


class ReceiptRejectIn(_In):
    reason: str | None = Field(default=None, max_length=1000)
