"""M29 Stufe 4 (docs/plans/M29-dms.md): tables of the objektakte service connection.

* ``ObjektakteWebhookReceipt``: every accepted webhook delivery of objektakte, unique per
  (event, object number, objektakte document id) so that a repeated delivery (objektakte retries
  up to three times) changes nothing. Filed documents themselves become ``document`` rows (M6),
  this table only records the delivery and its outcome.
* ``ObjektaktePersonProposal``: an owner or tenant list of one object fetched from objektakte as
  an import proposal (M8 pattern: test run, reconciliation, release). Rows hold only the name,
  unit labels, share or lease dates, never e-mail or IBAN, and nothing is written into the master
  data from here.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

WEBHOOK_OUTCOMES = ("created", "linked", "updated", "unchanged", "recorded", "ignored")
PROPOSAL_KINDS = ("owners", "tenants")
PROPOSAL_STATUSES = ("tested", "approved", "rejected")


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
