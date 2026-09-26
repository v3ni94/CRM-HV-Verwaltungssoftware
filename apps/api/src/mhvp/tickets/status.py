"""Ticket status transitions (service layer, section 6.6 and 6.8).

Single place for the rules that apply whenever a ticket changes its status, regardless of the
entry point (PATCH, bulk action, merge, later mail intake): allowed transitions, completion
checks, the ``TicketEvent`` row, ``resolved_at``, the SLA clock (``mhvp.sla``), the domain event
``ticket.status_changed``, playbook learning and mail archiving on closing statuses. The
routers only validate input and call :func:`transition_status`.
"""

import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import Ticket, TicketEvent, TicketStatus, TicketTemplate

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


class ResolutionKind(StrEnum):
    """Feste Liste der Erledigungsarten (Betreiberauftrag 26.09.2026). ``zusammengefuehrt``
    setzt nur die Zusammenführung für ihre Quelltickets, wenn keine Erledigung mitkommt."""

    STAMMDATEN_ERGAENZT = "stammdaten_ergaenzt"
    HANDWERKER_BEAUFTRAGT = "handwerker_beauftragt"
    AUSKUNFT_ERTEILT = "auskunft_erteilt"
    WEITERGELEITET = "weitergeleitet"
    KEIN_HANDLUNGSBEDARF = "kein_handlungsbedarf"
    ABGELEHNT = "abgelehnt"
    ZUSAMMENGEFUEHRT = "zusammengefuehrt"
    SONSTIGES = "sonstiges"


RESOLUTION_LABELS: dict[str, str] = {
    ResolutionKind.STAMMDATEN_ERGAENZT: "Stammdaten ergänzt",
    ResolutionKind.HANDWERKER_BEAUFTRAGT: "Handwerker beauftragt",
    ResolutionKind.AUSKUNFT_ERTEILT: "Auskunft erteilt",
    ResolutionKind.WEITERGELEITET: "Weitergeleitet",
    ResolutionKind.KEIN_HANDLUNGSBEDARF: "Kein Handlungsbedarf",
    ResolutionKind.ABGELEHNT: "Abgelehnt",
    ResolutionKind.ZUSAMMENGEFUEHRT: "Zusammengeführt",
    ResolutionKind.SONSTIGES: "Sonstiges",
}


class ResolutionIn(BaseModel):
    """Erledigungsnotiz beim Setzen auf done, closed oder rejected: Art plus Freitext, der
    Freitext ist bei ``sonstiges`` Pflicht."""

    model_config = ConfigDict(extra="forbid")

    kind: ResolutionKind
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _note_for_other(self) -> "ResolutionIn":
        self.note = (self.note or "").strip() or None
        if self.kind is ResolutionKind.SONSTIGES and not self.note:
            raise ValueError("Bei Sonstiges ist eine Beschreibung erforderlich.")
        return self


def resolution_text(kind: str | None, note: str | None) -> str:
    """Lesbare Erledigung, zum Beispiel ``Stammdaten ergänzt: Telefonnummer nachgetragen``."""
    if not kind:
        return (note or "").strip()
    label = RESOLUTION_LABELS.get(kind, kind)
    return f"{label}: {note.strip()}" if note and note.strip() else label


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


async def record_resolution_example(session: AsyncSession, ticket: Ticket) -> None:
    """Speichert je Abschluss ein Lernbeispiel (``AiExample``, Aufgabe ``ticket_resolution``);
    ein Fehler darf den Statuswechsel nie stören (eigener Savepoint)."""
    from mhvp.communication.suggest import resolution_example

    try:
        async with session.begin_nested():
            session.add(await resolution_example(session, ticket))
    except Exception:
        log.warning("could not store resolution example", extra={"ticket_id": str(ticket.id)})


async def assert_transition_allowed(
    session: AsyncSession, ticket: Ticket, new_status: TicketStatus, *, skip_flow: bool = False
) -> None:
    """Raises ``ProblemError`` when the flow forbids the change or the completion checks
    (required checklist items, required template fields) fail for done and closed.
    ``skip_flow`` (Betreiber 26.09.2026: Mandantenadministratoren setzen jeden Status in jeden
    anderen, ohne Zwischenschritte) lässt nur die Flussprüfung aus, nie die Abschlussprüfungen."""
    if not skip_flow and new_status not in TICKET_FLOW[ticket.status]:
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
    skip_flow: bool = False,
    resolution: ResolutionIn | None = None,
) -> bool:
    """Applies a status change with all side effects. Returns False when the status is
    unchanged. Raises ``ProblemError`` for a forbidden transition or failed completion checks.
    The caller holds the row lock (``with_for_update``) and commits. ``skip_flow`` marks the
    event with ``admin_override`` when the flow would have forbidden the change. A closing
    status requires ``resolution`` (Erledigungsnotiz), also for the admin bypass; it is stored
    on the ticket and as a learning example (``AiExample``, task ``ticket_resolution``)."""
    if new_status is ticket.status:
        return False
    closing = new_status in CLOSING_STATUSES
    admin_override = skip_flow and new_status not in TICKET_FLOW[ticket.status]
    await assert_transition_allowed(session, ticket, new_status, skip_flow=skip_flow)
    if closing and resolution is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Beim Abschluss ist eine Erledigungsnotiz (resolution) erforderlich.",
        )
    previous = ticket.status
    data: dict[str, Any] = {"from": previous.value, "to": new_status.value}
    if bulk:
        data["bulk"] = True
    if admin_override:
        data["admin_override"] = True
    if closing and resolution is not None:
        data["resolution"] = {"kind": resolution.kind.value, "note": resolution.note}
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
    ticket.resolved_at = datetime.now(UTC) if closing else None
    if closing and resolution is not None:
        ticket.resolution_kind = resolution.kind.value
        ticket.resolution_note = resolution.note
        ticket.resolved_by = actor_user_id
    elif not closing:
        ticket.resolution_kind = None
        ticket.resolution_note = None
        ticket.resolved_by = None
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
    if closing:
        await record_resolution_example(session, ticket)
    if new_status in (TicketStatus.DONE, TicketStatus.CLOSED):
        await queue_learn_playbook(session, settings, ticket)
    if closing:
        # Operator rule: every closing status (done, closed, rejected) archives the linked
        # mails in the mailbox; the mailbox flag archive_on_ticket_done applies.
        from mhvp.communication.services import enqueue_archive_for_ticket

        await enqueue_archive_for_ticket(session, settings, ticket.tenant_id, ticket.id)
    return True
