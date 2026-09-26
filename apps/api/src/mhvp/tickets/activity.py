"""Staff activity, customer activity and attention level of a ticket (operator 26.09.2026,
rule M19-09).

``last_staff_activity_at`` is the latest action by the management company's staff: a ticket
event with a user (status change, assignment, reply sent, ...; not the intake event
``created``), a comment by a user (internal
or public), an outbound mail (``direction == "out"``) or a work order update. Inbound mails,
portal comments by tenants or owners and external reminders do not reset the clock; they are
reported separately as ``last_inbound_at`` ("letzte Nachricht des Kunden").

The attention level is derived server side from ``last_staff_activity_at`` with
``created_at`` as the reference for tickets without any staff reaction, so that clients only
map it to colours:

- ``closed``: any closing status (done, closed, rejected); never stale.
- ``stale_96h``: no staff reaction for 96 hours or more (Produktschutz threshold).
- ``stale_24h``: no staff reaction for 24 hours or more.
- ``new``: status new with a recent reference time.
- ``none``: everything else.

Everything is computed inside the list query (one query, no N+1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select

from mhvp.tickets.models import Ticket, TicketComment, TicketEvent, TicketStatus, WorkOrder
from mhvp.tickets.status import CLOSING_STATUSES

Attention = Literal["none", "new", "stale_24h", "stale_96h", "closed"]

STALE_AFTER = timedelta(hours=24)
STALE_CRITICAL_AFTER = timedelta(hours=96)

SORT_OPTIONS = ("urgency", "created_desc")


def last_staff_activity_expression() -> Any:
    """SQL expression (correlated to ``Ticket``) for the latest staff action, or NULL."""
    from mhvp.communication.models import Message

    events = (
        select(func.max(TicketEvent.created_at))
        .where(
            TicketEvent.ticket_id == Ticket.id,
            TicketEvent.user_id.is_not(None),
            # Intake is not a reaction: the "created" event of a manually created ticket
            # carries the creator, but the clock starts at created_at.
            TicketEvent.kind != "created",
        )
        .correlate(Ticket)
        .scalar_subquery()
    )
    comments = (
        select(func.max(TicketComment.created_at))
        .where(TicketComment.ticket_id == Ticket.id, TicketComment.author_user_id.is_not(None))
        .correlate(Ticket)
        .scalar_subquery()
    )
    messages = (
        select(func.max(Message.created_at))
        .where(Message.ticket_id == Ticket.id, Message.direction == "out")
        .correlate(Ticket)
        .scalar_subquery()
    )
    work_orders = (
        select(func.max(WorkOrder.updated_at))
        .where(WorkOrder.ticket_id == Ticket.id)
        .correlate(Ticket)
        .scalar_subquery()
    )
    # PostgreSQL GREATEST ignores NULL operands and is NULL only when all are NULL.
    return func.greatest(events, comments, messages, work_orders)


def last_inbound_expression() -> Any:
    """SQL expression (correlated to ``Ticket``) for the latest customer message, or NULL:
    inbound mail or portal comment by a contact."""
    from mhvp.communication.models import Message

    messages = (
        select(func.max(Message.created_at))
        .where(Message.ticket_id == Ticket.id, Message.direction == "in")
        .correlate(Ticket)
        .scalar_subquery()
    )
    comments = (
        select(func.max(TicketComment.created_at))
        .where(TicketComment.ticket_id == Ticket.id, TicketComment.author_contact_id.is_not(None))
        .correlate(Ticket)
        .scalar_subquery()
    )
    return func.greatest(messages, comments)


def reaction_reference_expression() -> Any:
    """Reference time of the traffic light: last staff action, else ``created_at``."""
    return func.coalesce(last_staff_activity_expression(), Ticket.created_at)


def urgency_order() -> list[Any]:
    """Default sort "Dringlichkeit": closed tickets last, then the longest without a staff
    reaction first (red before orange before yellow, since the levels are monotonic in the
    idle time), then newest number first."""
    return [
        Ticket.status.in_(CLOSING_STATUSES).asc(),
        reaction_reference_expression().asc(),
        Ticket.number.desc(),
    ]


def attention_for(
    status: TicketStatus | str, reference_at: datetime, now: datetime | None = None
) -> Attention:
    """Derive the attention level; closed tickets never count as stale."""
    if status in CLOSING_STATUSES:
        return "closed"
    current = now or datetime.now(UTC)
    idle = current - reference_at
    if idle >= STALE_CRITICAL_AFTER:
        return "stale_96h"
    if idle >= STALE_AFTER:
        return "stale_24h"
    if status == TicketStatus.NEW:
        return "new"
    return "none"


def activity_out(
    ticket: Ticket,
    last_staff_activity_at: datetime | None,
    last_inbound_at: datetime | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    reference = last_staff_activity_at or ticket.created_at
    return {
        "last_staff_activity_at": last_staff_activity_at,
        "last_inbound_at": last_inbound_at,
        "last_activity_at": reference,
        "attention": attention_for(ticket.status, reference, now),
    }
