"""Ticket status transitions (service layer, section 6.6 and 6.8).

Single place for the rules that apply whenever a ticket changes its status, regardless of the
entry point (PATCH, bulk action, merge, later mail intake): allowed transitions, completion
checks, the ``TicketEvent`` row, ``resolved_at``, the SLA clock (``mhvp.sla``), the domain event
``ticket.status_changed``, playbook learning and mail archiving on closing statuses. The
routers only validate input and call :func:`transition_status`. Assignment of the primary
assignee goes through :func:`assign_ticket` (event ``ticket.assigned``, notification,
``TicketAssignee.primary``).

Mail archiving is an event consumer: it is registered with ``after_commit`` and runs only once
the status change is committed (review 26.09.2026, M14), so a failed commit never leaves
archived mails behind an open ticket.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.db.tenancy import after_commit
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import Ticket, TicketAssignee, TicketEvent, TicketStatus, TicketTemplate
from mhvp.workspace.services import notify

log = logging.getLogger(__name__)

TICKET_FLOW: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.NEW: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING,
        TicketStatus.REJECTED,
        TicketStatus.DONE,
    },
    TicketStatus.IN_PROGRESS: {TicketStatus.WAITING, TicketStatus.DONE, TicketStatus.REJECTED},
    TicketStatus.WAITING: {TicketStatus.IN_PROGRESS, TicketStatus.DONE, TicketStatus.REJECTED},
    TicketStatus.DONE: {TicketStatus.CLOSED, TicketStatus.IN_PROGRESS},
    TicketStatus.CLOSED: set(),
    TicketStatus.REJECTED: {TicketStatus.IN_PROGRESS},
}

# Statuses that end a ticket; they set resolved_at, stop the SLA clock and archive mails.
CLOSING_STATUSES = frozenset({TicketStatus.DONE, TicketStatus.CLOSED, TicketStatus.REJECTED})


def check_required_extra_fields(
    template_fields: list[dict[str, Any]], values: dict[str, Any]
) -> None:
    for field in template_fields:
        if field.get("required") and not values.get(field["key"]):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Pflichtfeld fehlt: {field.get('label', field['key'])}",
            )


def check_checklist_complete(checklist: list[dict[str, Any]]) -> None:
    for item in checklist:
        if item.get("required") and not item.get("done"):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Checkliste unvollständig")


async def queue_learn_playbook(session: AsyncSession, settings: Any, ticket: Ticket) -> None:
    """Playbook-Lernen beim Schließen eines Tickets (M20 Übernahme aus dem Immoware Hub):
    synchron in Tests und Entwicklung (``ai_inline``), sonst über die Queue ``ai``. Ein
    Fehler beim Lernen darf den Statuswechsel nie stören."""
    if settings.ai_inline:
        from mhvp.communication.suggest import learn_playbook_from_ticket

        try:
            await learn_playbook_from_ticket(session, settings, ticket)
        except Exception:
            return
    else:
        try:
            from mhvp.worker import get_celery

            get_celery().send_task(
                "mhvp.communication.learn_playbook",
                args=[str(ticket.tenant_id), str(ticket.id)],
                queue="ai",
            )
        except Exception:
            log.warning("could not queue playbook learning", extra={"ticket_id": str(ticket.id)})


async def assert_transition_allowed(
    session: AsyncSession, ticket: Ticket, new_status: TicketStatus
) -> None:
    """Raises ``ProblemError`` when the flow forbids the change or the completion checks
    (required checklist items, required template fields) fail for done and closed."""
    if new_status not in TICKET_FLOW[ticket.status]:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=f"Wechsel {ticket.status.value} nach {new_status.value} unzulässig.",
        )
    if new_status in (TicketStatus.DONE, TicketStatus.CLOSED):
        check_checklist_complete(ticket.checklist)
        if ticket.template_id:
            template = await session.get(TicketTemplate, ticket.template_id)
            if template:
                check_required_extra_fields(template.extra_fields, ticket.extra_fields)


async def _sync_sla_clock(session: AsyncSession, ticket: Ticket, closing: bool) -> None:
    """Closing stops the resolution clock; leaving a closing status (reopening) restarts it.
    A ticket without a clock (older rows) is left alone here; the SLA job backfills."""
    from mhvp.sla.models import ClockState, SlaClock, SlaClockLog
    from mhvp.sla.service import mark_resolved

    clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket.id))
    if clock is None:
        return
    if closing:
        await mark_resolved(session, clock)
    elif clock.state == ClockState.DONE:
        clock.resolved_at = None
        clock.state = ClockState.RUNNING
        session.add(SlaClockLog(tenant_id=clock.tenant_id, clock_id=clock.id, event="reopened"))


async def transition_status(
    session: AsyncSession,
    settings: Any,
    ticket: Ticket,
    new_status: TicketStatus,
    actor_user_id: uuid.UUID | None,
    *,
    bulk: bool = False,
) -> bool:
    """Applies a status change with all side effects. Returns False when the status is
    unchanged. Raises ``ProblemError`` for a forbidden transition or failed completion checks.
    The caller holds the row lock (``with_for_update``) and commits."""
    if new_status is ticket.status:
        return False
    await assert_transition_allowed(session, ticket, new_status)
    previous = ticket.status
    data: dict[str, Any] = {"from": previous.value, "to": new_status.value}
    if bulk:
        data["bulk"] = True
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind="status",
            user_id=actor_user_id,
            data=data,
        )
    )
    ticket.status = new_status
    closing = new_status in CLOSING_STATUSES
    ticket.resolved_at = datetime.now(UTC) if closing else None
    await _sync_sla_clock(session, ticket, closing)
    await emit(
        session,
        tenant_id=ticket.tenant_id,
        type="ticket.status_changed",
        entity_type="ticket",
        entity_id=ticket.id,
        actor_user_id=actor_user_id,
        payload={"from": previous.value, "to": new_status.value, "number": ticket.number},
    )
    if new_status in (TicketStatus.DONE, TicketStatus.CLOSED):
        await queue_learn_playbook(session, settings, ticket)
    if closing:
        # Operator rule: every closing status (done, closed, rejected) archives the linked
        # mails in the mailbox; the mailbox flag archive_on_ticket_done applies. Consumer of
        # ticket.status_changed, executed after the commit.
        after_commit(session, _archive_consumer(session, settings, ticket.tenant_id, ticket.id))
    return True


def _archive_consumer(
    session: AsyncSession, settings: Any, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> Any:
    async def _run() -> None:
        from mhvp.communication import services as communication_services

        await communication_services.enqueue_archive_for_ticket(
            session, settings, tenant_id, ticket_id
        )

    return _run


async def assign_ticket(
    session: AsyncSession,
    ticket: Ticket,
    user_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    *,
    reason: str = "manuell",
    notify_user: bool = True,
) -> bool:
    """Sets the primary assignee with all side effects: ``TicketAssignee`` row with reason
    (the previous primary row loses its ``primary`` mark, review N3), ``TicketEvent``
    ``assigned`` with ``from`` and ``to``, notification and domain event ``ticket.assigned``.
    Returns False when the assignee is unchanged."""
    if user_id == ticket.assignee_user_id:
        return False
    previous = ticket.assignee_user_id
    ticket.assignee_user_id = user_id
    rows = (
        await session.scalars(select(TicketAssignee).where(TicketAssignee.ticket_id == ticket.id))
    ).all()
    current = None
    for row in rows:
        if row.user_id == user_id:
            current = row
        elif row.primary:
            row.primary = False
    if current is None:
        session.add(
            TicketAssignee(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                user_id=user_id,
                primary=True,
                reason=reason,
            )
        )
    else:
        current.primary = True
        current.reason = reason
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind="assigned",
            user_id=actor_user_id,
            data={
                "user_id": str(user_id),
                "from": str(previous) if previous else None,
                "to": str(user_id),
                "reason": reason,
            },
        )
    )
    if notify_user:
        await notify(
            session,
            tenant_id=ticket.tenant_id,
            user_id=user_id,
            kind="ticket_assigned",
            title=f"Ticket {ticket.number}: {ticket.title}",
            entity_type="ticket",
            entity_id=ticket.id,
        )
    await emit(
        session,
        tenant_id=ticket.tenant_id,
        type="ticket.assigned",
        entity_type="ticket",
        entity_id=ticket.id,
        actor_user_id=actor_user_id,
        payload={
            "from": str(previous) if previous else None,
            "to": str(user_id),
            "reason": reason,
            "number": ticket.number,
        },
    )
    return True
