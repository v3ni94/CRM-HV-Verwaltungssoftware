"""M14 Belegeingang: `ReceiptDraft`, the reviewable result of one AI extraction run over one
document (6.4, rule 0.1.6). A draft is never a posting and never an invoice by itself: only
`confirm` creates an `Invoice` (open, unposted, review not started) from the values the
reviewer entered, and only `reject` closes it without one.

Field values live in ``fields`` as ``{name: {"value", "confidence", "source", "note"}}`` with
``source`` ``ai`` (model output), ``xml`` (structured part of an e-invoice, `receipts.einvoice`),
``ai_estimate`` (a model value that is explicitly not evidence, e.g. a § 35a share without a
documented split, D44), ``local`` (deterministic detection in the CRM, e.g. the IBAN candidates
or the property match) or ``none`` (no value). IBAN candidates never enter ``fields``; they
are stored encrypted in ``iban_candidates`` and exposed masked.

E-invoices (13.5, D41, D42): ``e_invoice_format`` (``none``, ``xrechnung``, ``zugferd``),
``xml_lines`` and ``xml_payment`` (masked) keep the structured part; ``conflicts`` lists every
contradiction between the XML and the PDF text or the AI reading; ``findings`` are the
deterministic hints of the intake (formal completeness, arithmetic, unproven estimates).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


class ReceiptDraftStatus(StrEnum):
    EXTRACTING = "extracting"  # run queued or running
    PROPOSED = "proposed"  # fields available for review
    FAILED = "failed"  # run failed or blocked (reason in ``error``)
    CONFIRMED = "confirmed"  # invoice draft created from the reviewed values
    REJECTED = "rejected"


class ReceiptDraftSource(StrEnum):
    MAIL_ATTACHMENT = "mail_attachment"
    PAPERLESS = "paperless"
    UPLOAD = "upload"


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class ReceiptDraft(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "receipt_draft"
    __table_args__ = (Index("ix_receipt_draft_status", "tenant_id", "status"),)

    document_id: Mapped[uuid.UUID] = _fk("document.id")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    message_id: Mapped[uuid.UUID | None] = _fk("message.id", nullable=True)
    task_run_id: Mapped[uuid.UUID | None] = _fk("ai_task_run.id", nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReceiptDraftStatus.EXTRACTING.value
    )
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Encrypted JSON list of normalised IBAN strings found deterministically in the text.
    iban_candidates: Mapped[str | None] = mapped_column(EncryptedText())
    supplier_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    property_suggestions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    questions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # What was sent to the provider (masked) so a reviewer can verify the masking (0.1.13).
    masked_excerpt: Mapped[str | None] = mapped_column(Text)
    e_invoice_format: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    xml_lines: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    xml_payment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    conflicts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    findings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    invoice_id: Mapped[uuid.UUID | None] = _fk("invoice.id", nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
