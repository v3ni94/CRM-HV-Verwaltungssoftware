"""Notfallkette und Eskalation (docs/mail/04-status-und-sla.md, Abschnitt 6): ohne Reaktion
eskaliert eine Uhr je Eskalationsstufe an Verantwortliche, Bereitschaft oder Rolle."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import emit
from mhvp.sla.models import (
    AlertChannel,
    ClockState,
    EmergencyAlert,
    EscalationStep,
    OnCallSchedule,
    SlaClock,
    SlaClockLog,
    SlaColor,
)
from mhvp.sla.service import recompute_color
from mhvp.tickets.models import Priority, Ticket
from mhvp.workspace.services import notify

log = logging.getLogger(__name__)

ESCALATED_PRIORITIES = (Priority.IMMEDIATE, Priority.URGENT)


async def current_on_call(session: AsyncSession, tenant_id: uuid.UUID) -> OnCallSchedule | None:
    now = datetime.now(UTC)
    on_call: OnCallSchedule | None = await session.scalar(
        select(OnCallSchedule).where(
            OnCallSchedule.tenant_id == tenant_id,
            OnCallSchedule.starts_at <= now,
            OnCallSchedule.ends_at >= now,
        )
    )
    return on_call


async def _send_alert(
    session: AsyncSession,
    ticket: Ticket,
    level: int,
    sent_to: str,
    channel: AlertChannel,
) -> EmergencyAlert:
    alert = EmergencyAlert(
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.id,
        level=level,
        sent_to=sent_to,
        channel=channel,
    )
    session.add(alert)
    await session.flush()
    if channel == AlertChannel.INTERNAL:
        try:
            user_id = uuid.UUID(sent_to)
        except ValueError:
            user_id = None
        if user_id is not None:
            await notify(
                session,
                tenant_id=ticket.tenant_id,
                user_id=user_id,
                kind="sla_escalation",
                title=f"SLA-Eskalation Ticket #{ticket.number}",
                body=ticket.title,
                entity_type="ticket",
                entity_id=ticket.id,
            )
    # E-Mail-Versand läuft über den bestehenden Mailversand (Gmail send_raw des Default-
    # Postfachs oder SMTP, siehe communication.tasks); hier nur protokolliert, da ein
    # Mandanten-Postfach dafür konfiguriert sein muss.
    return alert


async def check_and_escalate(session: AsyncSession, clock: SlaClock) -> SlaColor:
    """Berechnet die Ampel neu und löst fällige Eskalationsstufen aus."""
    color = await recompute_color(session, clock.tenant_id, clock)
    if clock.state != ClockState.BREACHED:
        return color
    ticket = await session.get(Ticket, clock.ticket_id)
    if ticket is None:
        return color
    steps = list(
        await session.scalars(
            select(EscalationStep)
            .where(EscalationStep.rule_id == clock.rule_id)
            .order_by(EscalationStep.step_no)
        )
    )
    elapsed_minutes = int((datetime.now(UTC) - clock.started_at).total_seconds() // 60)
    for step in steps:
        if step.step_no in clock.escalated_steps or elapsed_minutes < step.after_minutes:
            continue
        for user_id in step.notify_user_ids:
            await _send_alert(session, ticket, step.step_no, str(user_id), step.channel)
        if step.notify_role:
            await _send_alert(session, ticket, step.step_no, step.notify_role, step.channel)
        clock.escalated_steps = [*clock.escalated_steps, step.step_no]
        session.add(
            SlaClockLog(
                tenant_id=clock.tenant_id,
                clock_id=clock.id,
                event="escalated",
                note=f"Stufe {step.step_no}",
            )
        )
        await emit(
            session,
            tenant_id=clock.tenant_id,
            type="sla.escalated",
            entity_type="ticket",
            entity_id=ticket.id,
            actor_user_id=None,
            payload={"clock_id": str(clock.id), "step_no": step.step_no},
        )
    if not steps and ticket.priority in ESCALATED_PRIORITIES and 0 not in clock.escalated_steps:
        on_call = await current_on_call(session, clock.tenant_id)
        if on_call is not None:
            await _send_alert(session, ticket, 0, str(on_call.user_id), AlertChannel.INTERNAL)
            clock.escalated_steps = [*clock.escalated_steps, 0]
            session.add(
                SlaClockLog(
                    tenant_id=clock.tenant_id,
                    clock_id=clock.id,
                    event="escalated",
                    note="Bereitschaft benachrichtigt",
                )
            )
    return color
