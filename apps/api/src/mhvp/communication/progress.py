""" "In Bearbeitung" marker of the mail overview (operator 27.09.2026).

A mail counts as in progress as soon as somebody answered it (outgoing reply in its thread
that was submitted for approval, is being sent or was sent), an internal ticket comment
exists or a ticket assignee is set. The handler shown in the list is the ticket assignee,
otherwise the user of the latest reply or comment, whichever is younger. Names come from
``User.display_name`` ("Vorname Nachname"). Computed per page of the list, never stored.

Unsubmitted drafts do not count (nobody answered yet); see docs/ASSUMPTIONS.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Message

REPLY_STATUSES = ("pending", "sending", "sent")


@dataclass(frozen=True)
class Progress:
    in_progress: bool
    handler_user_id: uuid.UUID | None
    handler_display_name: str | None


NONE = Progress(False, None, None)


async def progress_for(session: AsyncSession, rows: list[Message]) -> dict[uuid.UUID, Progress]:
    """Marker per message of ``rows`` (inbound; outgoing rows get ``NONE``)."""
    from mhvp.platform.models import User
    from mhvp.tickets.models import Ticket, TicketComment

    inbound = [r for r in rows if r.direction == "in"]
    result: dict[uuid.UUID, Progress] = {r.id: NONE for r in rows}
    if not inbound:
        return result
    ticket_ids = {r.ticket_id for r in inbound if r.ticket_id}
    roots = {r.thread_id or r.id for r in inbound}
    header_ids = {r.header_message_id for r in inbound if r.header_message_id}

    assignee: dict[uuid.UUID, uuid.UUID] = {}
    latest_comment: dict[uuid.UUID, tuple[datetime, uuid.UUID | None]] = {}
    if ticket_ids:
        for tid, uid in await session.execute(
            select(Ticket.id, Ticket.assignee_user_id).where(Ticket.id.in_(ticket_ids))
        ):
            if uid is not None:
                assignee[tid] = uid
        for tid, uid, at in await session.execute(
            select(TicketComment.ticket_id, TicketComment.author_user_id, TicketComment.created_at)
            .where(TicketComment.ticket_id.in_(ticket_ids), TicketComment.internal.is_(True))
            .order_by(TicketComment.created_at.desc())
        ):
            latest_comment.setdefault(tid, (at, uid))

    latest_reply_by_root: dict[uuid.UUID, tuple[datetime, uuid.UUID | None]] = {}
    latest_reply_by_header: dict[str, tuple[datetime, uuid.UUID | None]] = {}
    conditions = [Message.thread_id.in_(roots)]
    if header_ids:
        conditions.append(Message.in_reply_to.in_(header_ids))
    for thread_id, in_reply_to, created_by, submitted_by, at in await session.execute(
        select(
            Message.thread_id,
            Message.in_reply_to,
            Message.created_by,
            Message.submitted_by,
            Message.created_at,
        )
        .where(Message.direction == "out", Message.status.in_(REPLY_STATUSES), or_(*conditions))
        .order_by(Message.created_at.desc())
    ):
        who = submitted_by or created_by
        if thread_id is not None:
            latest_reply_by_root.setdefault(thread_id, (at, who))
        if in_reply_to:
            latest_reply_by_header.setdefault(in_reply_to, (at, who))

    wanted: set[uuid.UUID] = set()
    raw: dict[uuid.UUID, tuple[bool, uuid.UUID | None]] = {}
    for r in inbound:
        reply = latest_reply_by_root.get(r.thread_id or r.id)
        if r.header_message_id and r.header_message_id in latest_reply_by_header:
            by_header = latest_reply_by_header[r.header_message_id]
            reply = by_header if reply is None or by_header[0] > reply[0] else reply
        comment = latest_comment.get(r.ticket_id) if r.ticket_id else None
        assigned = assignee.get(r.ticket_id) if r.ticket_id else None
        active = assigned is not None or reply is not None or comment is not None
        handler: uuid.UUID | None = assigned
        if handler is None:
            events = [e for e in (reply, comment) if e is not None]
            if events:
                handler = max(events, key=lambda e: e[0])[1]
        raw[r.id] = (active, handler)
        if handler is not None:
            wanted.add(handler)

    names: dict[uuid.UUID, str] = {}
    if wanted:
        for uid, name in await session.execute(
            select(User.id, User.display_name).where(User.id.in_(wanted))
        ):
            names[uid] = name
    for r in inbound:
        active, handler = raw[r.id]
        result[r.id] = Progress(active, handler, names.get(handler) if handler else None)
    return result
