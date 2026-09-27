"""M29 Stufe 4 (docs/plans/M29-dms.md): tables of the objektakte service connection.

* ``ObjektakteWebhookReceipt``: every accepted webhook delivery of objektakte, unique per
  (event, object number, objektakte document id) so that a repeated delivery (objektakte retries
  up to three times) changes nothing. Filed documents themselves become ``document`` rows (M6),
  this table only records the delivery and its outcome.
* ``ObjektaktePersonProposal``: an owner or tenant list of one object fetched from objektakte as
  an import proposal (M8 pattern: test run, reconciliation, release). Rows hold only the name,
  unit labels, share or lease dates, never e-mail or IBAN, and nothing is written into the master
  data from here.
* ``ObjektakteUpload`` (26.09.2026): a CRM document handed to objektakte for filing (Drive with
  owner and tenant files, Paperless). One row per document; the job ``mhvp.objektakte.upload``
  uploads it (pending, submitted) and polls endpoint 7 until objektakte has filed it (done) or
  rejects it (failed). While a row exists, the CRM's own Paperless and Drive mirrors are not
  queued for that document, so it lands in each system exactly once.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

WEBHOOK_OUTCOMES = ("created", "linked", "updated", "unchanged", "recorded", "ignored")
PROPOSAL_KINDS = ("owners", "tenants")
PROPOSAL_STATUSES = ("tested", "approved", "rejected")
UPLOAD_STATUSES = ("pending", "submitted", "done", "failed")


class ObjektakteWebhookReceipt(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "objektakte_webhook_receipt"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "event",
            "object_number",
            "source_document_id",
            name="uq_objektakte_webhook_receipt_key",
        ),
        CheckConstraint(
            "outcome IN ('created', 'linked', 'updated', 'unchanged', 'recorded', 'ignored')",
            name="outcome",
        ),
    )

    event: Mapped[str] = mapped_column(String(64), nullable=False)
    object_number: Mapped[str] = mapped_column(String(16), nullable=False)
    # objektakte document id as text; "" when the event carries no document (object.taken_over)
    source_document_id: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="SET NULL")
    )


class ObjektaktePersonProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "objektakte_person_proposal"
    __table_args__ = (
        CheckConstraint("kind IN ('owners', 'tenants')", name="kind"),
        CheckConstraint(
            "status IN ('tested', 'approved', 'rejected')",
            name="status",
        ),
        CheckConstraint(
            "(status = 'tested') = (decided_at IS NULL)",
            name="decision",
        ),
    )

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("property.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    object_number: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="tested")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class ObjektakteUpload(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "objektakte_upload"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", name="uq_objektakte_upload_document"),
        CheckConstraint(
            "status IN ('pending', 'submitted', 'done', 'failed')",
            name="status",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="SET NULL")
    )
    object_number: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Identifiers and labels from the CRM only (unit labels, contact ids, ticket number), never
    # names or contact data; objektakte keeps them for the owner and tenant file assignment.
    hints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    objektakte_document_id: Mapped[int | None] = mapped_column(Integer)
    # Last state reported by objektakte (status, category, subfolder, Drive and Paperless ids)
    remote: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
