"""Folgevorgang statt Wiedereröffnung (Regel M19-10, Betreiberentscheidung 28.09.2026).

A new inbound mail for a finished ticket (``done``, ``closed``, ``rejected``), matched through
the mail thread or the ``TNR#`` tag (``mhvp.communication.services.attach_to_ticket``):

- closed at most ``tenant_settings.ticket_reopen_window_days`` calendar days ago (operator
  time zone, default 30, the boundary day included): the ticket is reopened as before;
- closed longer ago: the ticket stays closed and a follow-up ticket is created for the mail.
  It points to its predecessor (``Ticket.follow_up_of_ticket_id``), takes over property, unit
  and contact of the predecessor as preset, and both tickets get an internal note and a
  history entry;
- an automatic reply (``classification.auto_submitted``, headers only, see
  ``mhvp.communication.mail.is_auto_submitted``) is attached to the closed ticket without
  reopening it and never creates a follow-up.

The ticket a mail lands on is the current end of the case: a merged ticket leads to its merge
target (M36), a closed ticket with a follow-up leads to that follow-up. Each ticket has at most
one follow-up (``uq_ticket_follow_up_of``), so the chain never branches; the predecessor row
is locked while the chain is resolved, so two different mails of the same thread arriving in
parallel do not both create a follow-up. The same mail processed twice never gets here twice
(``mhvp.communication.duplicates.lock_mail`` and ``find_known``).

A follow-up merged back into its case (into its predecessor or another ticket of the chain,
review 1.40.2) is no successor: the resolution never cycles, and before a new follow-up is
created the merged back one gives up its link (``release``). Merging a follow-up directly into
its predecessor clears the link right away (``mhvp.tickets.routers.merge_tickets``); every
other merge keeps the links, the resolution follows them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.tickets.models import Ticket, TicketComment, TicketEvent
from mhvp.workspace.services import local_date

DEFAULT_REOPEN_WINDOW_DAYS = 30
CLOSED_STATES = frozenset({"done", "closed", "rejected"})
# Guard against a corrupt cycle of merge or follow-up links; real chains are short.
_MAX_CHAIN = 50


def closed_at(ticket: Ticket) -> datetime:
    """Time the ticket was finished: ``resolved_at`` (set by every closing status change and
    by a merge); older rows without it fall back to the last change of the row."""
    moment = ticket.resolved_at or ticket.updated_at
    return moment if moment is not None else datetime.now(UTC)


def within_reopen_window(closed: datetime, now: datetime, window_days: int) -> bool:
    """True when the ticket closed at ``closed`` may still be reopened at ``now``: at most
    ``window_days`` calendar days in the operator time zone lie between both days, the
    boundary day included (closed on 28.08., mail on 27.09. is 30 days and reopens)."""
    return (local_date(now) - local_date(closed)).days <= window_days


async def reopen_window_days(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(
        select(TenantSettings.ticket_reopen_window_days).where(
            TenantSettings.tenant_id == tenant_id
        )
    )
    return DEFAULT_REOPEN_WINDOW_DAYS if value is None else int(value)


async def _locked(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    return await session.get(Ticket, ticket_id, with_for_update=True, populate_existing=True)


@dataclass(frozen=True)
class Resolution:
    """Result of ``resolve``: the current end of the case and, when the walk came back into
    the case, the follow-up of ``ticket`` that was merged back (``released``)."""

    ticket: Ticket | None
    released: Ticket | None = None


async def resolve(session: AsyncSession, ticket_id: uuid.UUID) -> Resolution:
    """Current end of the case, locked: follows merges to the target and, for a finished
    ticket, its follow-up. Every ticket is visited at most once. When a link leads back to a
    ticket already visited (a follow-up merged back into its predecessor or into another
    ticket of the chain, review 1.40.2), the follow-up being followed is no successor of the
    case: the walk ends at the last ticket that is not merged, and that follow-up is returned
    as ``released`` (it still holds the slot of ``uq_ticket_follow_up_of``). ``ticket`` is
    ``None`` when the ticket does not exist (RLS)."""
    ticket = await _locked(session, ticket_id)
    seen: set[uuid.UUID] = set()
    end: Ticket | None = None  # last ticket of the walk that is not merged
    pending: Ticket | None = None  # follow-up of ``end`` being followed
    while ticket is not None and len(seen) < _MAX_CHAIN:
        if ticket.id in seen:
            return Resolution(end or ticket, pending if end is not None else None)
        seen.add(ticket.id)
        if ticket.merged_into_ticket_id is not None:
            target = await _locked(session, ticket.merged_into_ticket_id)
            if target is None:
                break
            ticket = target
            continue
        end, pending = ticket, None
        if ticket.status.value not in CLOSED_STATES:
            break
        successor = await follow_up_of(session, ticket)
        if successor is None:
            break
        pending = ticket = successor
    return Resolution(end or ticket)


async def current_ticket(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    """Ticket a new mail of the case belongs to, locked (``resolve``)."""
    return (await resolve(session, ticket_id)).ticket


async def follow_up_of(session: AsyncSession, ticket: Ticket) -> Ticket | None:
    """The follow-up of ``ticket`` (at most one, ``uq_ticket_follow_up_of``), locked."""
    successor_id = await session.scalar(
        select(Ticket.id).where(Ticket.follow_up_of_ticket_id == ticket.id)
    )
    return await _locked(session, successor_id) if successor_id is not None else None


async def release(session: AsyncSession, follow_up: Ticket) -> None:
    """A follow-up merged back into its case is no follow-up any more: its link is cleared, so
    the slot of its predecessor is free for a new follow-up. The history keeps the relation
    (``follow_up_of`` and ``merged_into`` entries; ``released_follow_up`` in the entries of the
    new follow-up)."""
    follow_up.follow_up_of_ticket_id = None
    await session.flush()


@dataclass(frozen=True)
class MailTarget:
    """Where a new inbound mail of a case goes (``attach_to_ticket``).

    ``follow_up``: create a follow-up of ``ticket``; ``reopen``: attach the mail and reopen
    ``ticket``; neither: attach without a status change. ``released``: follow-up merged back
    into the case whose link was cleared for the new follow-up."""

    ticket: Ticket | None
    reopen: bool = False
    follow_up: bool = False
    window_days: int | None = None
    released: Ticket | None = None


async def mail_target(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    *,
    auto_reply: bool,
    now: datetime,
) -> MailTarget:
    """Decision of rule M19-10 for a new mail of the case of ``ticket_id``.

    The case is resolved to its current end (``resolve``). An open end takes the mail; an
    automatic reply is attached without a status change; a finished end within the reopen
    window is reopened. Outside the window a follow-up is created, unless the ticket already
    has one (the slot of ``uq_ticket_follow_up_of`` is taken): a follow-up merged back into the
    case is released first (``release``); any other existing follow-up is resolved in turn
    (it takes the mail, is reopened within its own window or leads further along the chain).
    A chain that does not end within the resolution limit leaves the mail on the last ticket,
    reopened, so the mail is never lost and the intake never fails on the unique index."""
    window: int | None = None
    released: Ticket | None = None
    start = ticket_id
    ticket: Ticket | None = None
    for _ in range(_MAX_CHAIN):
        resolution = await resolve(session, start)
        ticket = resolution.ticket
        if (
            ticket is None
            or auto_reply
            or ticket.merged_into_ticket_id is not None
            or ticket.status.value not in CLOSED_STATES
        ):
            return MailTarget(ticket)
        if window is None:
            window = await reopen_window_days(session, tenant_id)
        if within_reopen_window(closed_at(ticket), now, window):
            return MailTarget(ticket, reopen=True, window_days=window)
        if resolution.released is not None:
            await release(session, resolution.released)
            released = resolution.released
        existing = await follow_up_of(session, ticket)
        if existing is None:
            return MailTarget(ticket, follow_up=True, window_days=window, released=released)
        start = existing.id
    return MailTarget(ticket, reopen=ticket is not None, window_days=window)


def preset(
    predecessor: Ticket, *, contact_id: uuid.UUID | None, property_id: uuid.UUID | None
) -> dict[str, uuid.UUID | None]:
    """Assignment of the follow-up: property, unit and contact of the predecessor; the values
    derived from the mail only fill what the predecessor leaves empty. A unit is taken only
    together with the predecessor's property."""
    prop: uuid.UUID | None = property_id
    unit: uuid.UUID | None = None
    if predecessor.property_id is not None:
        prop, unit = predecessor.property_id, predecessor.unit_id
    return {
        "contact_id": predecessor.contact_id or contact_id,
        "property_id": prop,
        "unit_id": unit,
        "follow_up_of_ticket_id": predecessor.id,
    }


async def record_follow_up(
    session: AsyncSession,
    *,
    predecessor: Ticket,
    follow_up: Ticket,
    message_id: uuid.UUID,
    window_days: int,
    actor_user_id: uuid.UUID | None,
    released: Ticket | None = None,
) -> None:
    """Notes, history entries, notification of the predecessor's assignees and the domain
    event for a follow-up just created from a mail. ``released``: the follow-up merged back
    into the case that held the slot before (``release``), recorded in both entries."""
    from mhvp.core.events import emit
    from mhvp.tickets.models import TicketAssignee
    from mhvp.workspace.services import notify

    extra: dict[str, Any] = (
        {"released_follow_up": {"ticket_id": str(released.id), "number": released.number}}
        if released is not None
        else {}
    )
    closed_on = local_date(closed_at(predecessor)).strftime("%d.%m.%Y")
    session.add_all(
        [
            TicketComment(
                tenant_id=follow_up.tenant_id,
                ticket_id=follow_up.id,
                internal=True,
                body=(
                    f"Folgevorgang zu Ticket #{predecessor.number} {predecessor.title}. "
                    f"Das Ticket wurde am {closed_on} abgeschlossen; die neue E-Mail ist nach "
                    f"Ablauf der Wiedereröffnungsfrist von {window_days} Tagen eingegangen. "
                    "Objekt, Einheit und Kontakt wurden aus dem Vorgänger übernommen."
                ),
            ),
            TicketComment(
                tenant_id=predecessor.tenant_id,
                ticket_id=predecessor.id,
                internal=True,
                body=(
                    f"Neuer Folgevorgang #{follow_up.number} angelegt: eine neue E-Mail ist "
                    f"nach Ablauf der Wiedereröffnungsfrist von {window_days} Tagen "
                    "eingegangen. Dieses Ticket bleibt abgeschlossen."
                ),
            ),
            TicketEvent(
                tenant_id=follow_up.tenant_id,
                ticket_id=follow_up.id,
                kind="follow_up_of",
                data={
                    "ticket_id": str(predecessor.id),
                    "number": predecessor.number,
                    "message_id": str(message_id),
                    "window_days": window_days,
                }
                | extra,
                user_id=actor_user_id,
            ),
            TicketEvent(
                tenant_id=predecessor.tenant_id,
                ticket_id=predecessor.id,
                kind="follow_up_created",
                data={
                    "ticket_id": str(follow_up.id),
                    "number": follow_up.number,
                    "message_id": str(message_id),
                }
                | extra,
                user_id=actor_user_id,
            ),
        ]
    )
    await session.flush()
    recipients: set[uuid.UUID] = (
        {predecessor.assignee_user_id} if predecessor.assignee_user_id else set()
    )
    recipients.update(
        await session.scalars(
            select(TicketAssignee.user_id).where(TicketAssignee.ticket_id == predecessor.id)
        )
    )
    for user_id in recipients:
        await notify(
            session,
            tenant_id=follow_up.tenant_id,
            user_id=user_id,
            kind="ticket.follow_up_created",
            title=f"Neuer Folgevorgang #{follow_up.number} zu Ticket #{predecessor.number}",
            body=(follow_up.title or "")[:300],
            entity_type="ticket",
            entity_id=follow_up.id,
        )
    payload: dict[str, Any] = {
        "message_id": str(message_id),
        "predecessor_id": str(predecessor.id),
        "predecessor_number": predecessor.number,
        "number": follow_up.number,
        "window_days": window_days,
    }
    await emit(
        session,
        tenant_id=follow_up.tenant_id,
        type="ticket.follow_up_created",
        entity_type="ticket",
        entity_id=follow_up.id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
