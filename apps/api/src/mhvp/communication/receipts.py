"""Delivery and read indications on ``message`` (GA04-09).

``delivered_at``: the transport (Gmail API or SMTP) or the dispatch evidence reported the
mail as handed over or delivered. ``read_at``: the recipient opened a document of the mail in
the portal. Both are indications only, no legal proof of receipt (11.3, D34); they never
overwrite an earlier value (first event wins).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Message


def mark_delivered(message: Message, at: datetime | None = None) -> None:
    if message.delivered_at is None:
        message.delivered_at = at or datetime.now(UTC)


async def mark_read_for_document(
    session: AsyncSession, contact_id: uuid.UUID, document_id: uuid.UUID
) -> int:
    """Set ``read_at`` on sent mails to this contact that carry the opened document."""
    rows = (
        await session.scalars(
            select(Message).where(
                Message.contact_id == contact_id,
                Message.direction == "out",
                Message.status == "sent",
                Message.read_at.is_(None),
                Message.attachment_document_ids.contains([document_id]),
            )
        )
    ).all()
    now = datetime.now(UTC)
    for m in rows:
        m.read_at = now
    return len(rows)
