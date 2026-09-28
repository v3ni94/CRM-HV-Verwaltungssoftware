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
"""

from __future__ import annotations

import uuid
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


async def current_ticket(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    """Ticket a new mail of the case belongs to, locked: follows merges to the target and,
    for a finished ticket, its follow-up. ``None`` when the ticket does not exist (RLS)."""
    ticket = await _locked(session, ticket_id)
    seen: set[uuid.UUID] = set()
    while ticket is not None and ticket.id not in seen and len(seen) < _MAX_CHAIN:
        seen.add(ticket.id)
        if ticket.merged_into_ticket_id is not None:
            target = await _locked(session, ticket.merged_into_ticket_id)
            if target is None:
                break
            ticket = target
            continue
        if ticket.status.value not in CLOSED_STATES:
            break
        successor_id = await session.scalar(
            select(Ticket.id).where(Ticket.follow_up_of_ticket_id == ticket.id)
        )
        if successor_id is None:
            break
        successor = await _locked(session, successor_id)
        if successor is None:
            break
        ticket = successor
    return ticket


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
) -> None:
    """Notes, history entries, notification of the predecessor's assignees and the domain
    event for a follow-up just created from a mail."""
    from mhvp.core.events import emit
    from mhvp.tickets.models import TicketAssignee
    from mhvp.workspace.services import notify

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
                },
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
                },
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
