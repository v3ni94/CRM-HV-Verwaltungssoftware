"""SLA-Regelauflösung, Uhrensteuerung und Ampel (Übernahme aus dem Immoware Hub, M21)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.sla.business_time import add_business_minutes, business_minutes_between
from mhvp.sla.models import (
    ClockState,
    ClockType,
    SlaClock,
    SlaClockLog,
    SlaColor,
    SlaRule,
    WorkCalendar,
)
from mhvp.tickets.models import Priority

# Startvorschläge aus docs/mail/04-status-und-sla.md, Abschnitt 6 (P0-P3), auf die fünf
# Ticket-Prioritäten des CRM übertragen. Von der Geschäftsführung zu bestätigen.
DEFAULT_RULES: dict[Priority, tuple[int, int]] = {
    Priority.IMMEDIATE: (10, 240),  # Notfall: Annahme 10 Min, Lösung 4 Std, Kalenderzeit
    Priority.URGENT: (240, 2 * 24 * 60),  # 4 Arbeitsstunden, 2 Arbeitstage
    Priority.HIGH: (240, 2 * 24 * 60),
    Priority.NORMAL: (2 * 24 * 60, 5 * 24 * 60),
    Priority.LOW: (4 * 24 * 60, 10 * 24 * 60),
}
WARN_PERCENT = 50


async def get_calendar(session: AsyncSession, tenant_id: uuid.UUID) -> WorkCalendar:
    calendar = await session.scalar(select(WorkCalendar).where(WorkCalendar.tenant_id == tenant_id))
    if calendar is None:
        calendar = WorkCalendar(tenant_id=tenant_id)
        session.add(calendar)
        await session.flush()
    return calendar


async def resolve_rule(
    session: AsyncSession, tenant_id: uuid.UUID, priority: Priority
) -> SlaRule | None:
    """Liefert die aktive Regel der Priorität, falls hinterlegt. Ohne Regel gelten die
    Startvorschläge (``DEFAULT_RULES``); es wird keine Regel-Zeile erzeugt."""
    rule: SlaRule | None = await session.scalar(
        select(SlaRule).where(
            SlaRule.tenant_id == tenant_id,
            SlaRule.priority == priority,
            SlaRule.active.is_(True),
        )
    )
    return rule


def _due_at(
    calendar: WorkCalendar, start: datetime, minutes: int, clock_type: ClockType
) -> datetime:
    if clock_type == ClockType.CALENDAR:
        from datetime import timedelta

        return start + timedelta(minutes=minutes)
    return add_business_minutes(calendar, start, minutes)


async def start_clock(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    priority: Priority,
    started_at: datetime | None = None,
) -> SlaClock:
    """Startet die Uhr eines Tickets bei Anlage (Hook in Ticket-Router, Gmail-Abruf und
    Portal). Idempotent: eine vorhandene Uhr bleibt. ``started_at`` erlaubt dem Nachlauf
    (``mhvp.sla.tasks``), die Uhr rückwirkend ab Ticketanlage zu starten."""
    existing = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket_id))
    if existing is not None:
        return existing
    calendar = await get_calendar(session, tenant_id)
    rule = await resolve_rule(session, tenant_id, priority)
    now = started_at or datetime.now(UTC)
    if rule is not None:
        response_minutes, resolution_minutes, clock_type = (
            rule.response_minutes,
            rule.resolution_minutes,
            rule.clock_type,
        )
    else:
        response_minutes, resolution_minutes = DEFAULT_RULES[priority]
        clock_type = ClockType.CALENDAR if priority == Priority.IMMEDIATE else ClockType.BUSINESS
    clock = SlaClock(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        rule_id=rule.id if rule else None,
        started_at=now,
        due_response_at=_due_at(calendar, now, response_minutes, clock_type),
        due_resolution_at=_due_at(calendar, now, resolution_minutes, clock_type),
        state=ClockState.RUNNING,
        color=SlaColor.GREEN,
    )
    session.add(clock)
    await session.flush()
    session.add(SlaClockLog(tenant_id=tenant_id, clock_id=clock.id, event="started"))
    return clock


async def backfill_clocks(session: AsyncSession, tenant_id: uuid.UUID, limit: int = 500) -> int:
    """Startet Uhren für offene Tickets ohne Uhr rückwirkend ab Anlage (review 26.09.2026,
    H6): Tickets aus Mail, Portal oder Import, die an ``start_clock`` vorbeigelaufen sind.
    Liefert die Anzahl der gestarteten Uhren."""
    from mhvp.tickets.models import Ticket, TicketStatus

    open_without_clock = (
        select(Ticket)
        .where(
            Ticket.status.notin_([TicketStatus.DONE, TicketStatus.CLOSED, TicketStatus.REJECTED]),
            Ticket.merged_into_ticket_id.is_(None),
            ~select(SlaClock.id).where(SlaClock.ticket_id == Ticket.id).exists(),
        )
        .order_by(Ticket.created_at)
        .limit(limit)
    )
    started = 0
    for ticket in await session.scalars(open_without_clock):
        await start_clock(session, tenant_id, ticket.id, ticket.priority, ticket.created_at)
        started += 1
    return started


async def pause_clock(session: AsyncSession, clock: SlaClock) -> SlaClock:
    if clock.state != ClockState.RUNNING:
        return clock
    clock.state = ClockState.PAUSED
    clock.paused_at = datetime.now(UTC)
    session.add(SlaClockLog(tenant_id=clock.tenant_id, clock_id=clock.id, event="paused"))
    return clock


async def resume_clock(session: AsyncSession, tenant_id: uuid.UUID, clock: SlaClock) -> SlaClock:
    if clock.state != ClockState.PAUSED or clock.paused_at is None:
        return clock
    calendar = await get_calendar(session, tenant_id)
    paused_minutes = int((datetime.now(UTC) - clock.paused_at).total_seconds() // 60)
    clock.paused_minutes_total += paused_minutes
    if clock.due_resolution_at is not None:
        rule_type = ClockType.CALENDAR if paused_minutes == 0 else ClockType.BUSINESS
        clock.due_resolution_at = _due_at(
            calendar, clock.due_resolution_at, paused_minutes, rule_type
        )
    clock.paused_at = None
    clock.state = ClockState.RUNNING
    session.add(SlaClockLog(tenant_id=tenant_id, clock_id=clock.id, event="resumed"))
    return clock


async def mark_first_response(session: AsyncSession, clock: SlaClock) -> SlaClock:
    """Erste ausgehende, freigegebene Nachricht stoppt die Reaktionsuhr (Hook in
    ``communication.routers.approve``)."""
    if clock.first_response_at is not None:
        return clock
    clock.first_response_at = datetime.now(UTC)
    session.add(SlaClockLog(tenant_id=clock.tenant_id, clock_id=clock.id, event="first_response"))
    return clock


async def reopen_clock(session: AsyncSession, clock: SlaClock) -> SlaClock:
    """Erledigte Uhr läuft nach einer Kundenantwort weiter (Wiedereröffnung des Tickets,
    Hook in ``communication.services.attach_to_ticket``)."""
    if clock.state != ClockState.DONE:
        return clock
    clock.resolved_at = None
    clock.state = ClockState.RUNNING
    session.add(SlaClockLog(tenant_id=clock.tenant_id, clock_id=clock.id, event="reopened"))
    return clock


async def mark_resolved(session: AsyncSession, clock: SlaClock) -> SlaClock:
    if clock.resolved_at is not None:
        return clock
    clock.resolved_at = datetime.now(UTC)
    clock.state = ClockState.DONE
    session.add(SlaClockLog(tenant_id=clock.tenant_id, clock_id=clock.id, event="resolved"))
    return clock


async def recompute_color(session: AsyncSession, tenant_id: uuid.UUID, clock: SlaClock) -> SlaColor:
    """Ampel je Uhr: grün unter 50 % der Zielzeit, gelb ab 50 %, rot ab 100 % oder Überschreitung
    (docs/mail/04, Abschnitt 5). Berücksichtigt die kritischere von Reaktions- und Lösungsuhr."""
    if clock.state == ClockState.DONE:
        clock.color = SlaColor.GREEN
        return clock.color
    now = datetime.now(UTC)
    calendar = await get_calendar(session, tenant_id)
    worst = SlaColor.GREEN
    for due_at, done_at in (
        (clock.due_response_at, clock.first_response_at),
        (clock.due_resolution_at, clock.resolved_at),
    ):
        if due_at is None or done_at is not None:
            continue
        elapsed_target = business_minutes_between(calendar, clock.started_at, due_at) or 1
        elapsed_now = business_minutes_between(calendar, clock.started_at, min(now, due_at))
        if now >= due_at:
            color = SlaColor.RED
        elif (elapsed_now / elapsed_target) * 100 >= WARN_PERCENT:
            color = SlaColor.YELLOW
        else:
            color = SlaColor.GREEN
        if color.rank_value() > worst.rank_value():
            worst = color
    clock.color = worst
    if worst == SlaColor.RED and clock.state == ClockState.RUNNING:
        clock.state = ClockState.BREACHED
    return worst
