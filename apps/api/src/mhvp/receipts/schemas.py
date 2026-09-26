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
    source: Literal["ai", "xml", "ai_estimate", "local", "none"]
    note: str | None = None


class ReceiptConflictOut(BaseModel):
    """D42: one contradiction between the structured part and another reading; ``other`` is
    None when the value is simply missing in the other source."""

    field: str
    xml: str | None
    other: str | None
    other_source: Literal["pdf_text", "ai"]
    note: str


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
    e_invoice_format: str
    xml_lines: list[dict[str, Any]] = Field(default_factory=list)
    xml_payment: dict[str, Any] | None = None
    conflicts: list[ReceiptConflictOut] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
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
    conflicts_acknowledged: bool = Field(
        default=False,
        description=(
            "Pflicht, wenn der Entwurf Widersprüche zwischen XML und PDF ausweist (D42): die "
            "prüfende Person hat die Widersprüche gesehen; sie bleiben als Prüfhinweis an der "
            "Rechnung."
        ),
    )
    note: str | None = Field(default=None, max_length=1000)


class ReceiptRejectIn(_In):
    reason: str | None = Field(default=None, max_length=1000)
