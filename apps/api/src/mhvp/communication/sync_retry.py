"""Retry queue of the Gmail sync (review 26.09.2026, H1) and the indexes of ``message`` that
the review M4 and M2 asked for.

``MailboxSyncRetry``: a Gmail message whose ingest failed once (parse error, storage error,
constraint violation) is remembered per mailbox and tried again on the next sync runs until
``MAX_ATTEMPTS`` is reached; the history cursor moves on regardless, so one broken mail never
blocks the mailbox. The indexes live here instead of ``communication.models`` only because that
module is being changed in parallel (ticket mail thread work); they attach to the same table.
"""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.communication.models import Message
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MAX_ATTEMPTS = 5


class MailboxSyncRetry(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "mailbox_sync_retry"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "gmail_message_id", name="uq_mailbox_sync_retry_message"),
    )

    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailbox.id", ondelete="CASCADE"), nullable=False
    )
    gmail_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error: Mapped[str | None] = mapped_column(Text)


# Indexes on message (M4): ticket detail, thread view, mailbox listing with status filter.
Index("ix_message_ticket", Message.__table__.c.tenant_id, Message.__table__.c.ticket_id)
Index("ix_message_thread", Message.__table__.c.tenant_id, Message.__table__.c.thread_id)
Index(
    "ix_message_mailbox_status",
    Message.__table__.c.tenant_id,
    Message.__table__.c.mailbox_id,
    Message.__table__.c.status,
)
# Deduplication of inbound mails (M2): one inbound message per Message-ID and tenant. The
# ingest still checks first (returns the known row); the index only closes the race between
# two syncs or a parallel .eml upload.
Index(
    "uq_message_inbound_header_id",
    Message.__table__.c.tenant_id,
    Message.__table__.c.header_message_id,
    unique=True,
    postgresql_where=text("direction = 'in' AND header_message_id IS NOT NULL"),
)
