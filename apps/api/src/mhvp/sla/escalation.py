"""Notfallkette und Eskalation (docs/mail/04-status-und-sla.md, Abschnitt 6): ohne Reaktion
eskaliert eine Uhr je Eskalationsstufe an Verantwortliche, Bereitschaft oder Rolle."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.config import Settings, get_settings
from mhvp.core.events import emit
from mhvp.platform.models import Membership, User
from mhvp.properties.models import Property
from mhvp.sla.channels import (
    channels_for_level,
    email_body,
    email_subject,
    get_gateway,
    send_email,
    send_sms,
    sms_text,
    ticket_link,
)
from mhvp.sla.models import (
    AlertChannel,
    ClockState,
    EmergencyAlert,
    EscalationStep,
    OnCallSchedule,
    SlaClock,
    SlaClockLog,
    SlaColor,
    SlaRule,
)
from mhvp.sla.service import recompute_color
from mhvp.sla.whatsapp import get_config as get_whatsapp_config
from mhvp.sla.whatsapp import send_whatsapp
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
    *,
    delivery_error: str | None = None,
) -> EmergencyAlert:
    """Legt den Alarm an; interne Alarme gelten mit der Benachrichtigung als zugestellt."""
    alert = EmergencyAlert(
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.id,
        level=level,
        sent_to=sent_to[:300],
        channel=channel,
        delivery_error=delivery_error,
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
            alert.delivered_at = datetime.now(UTC)
    return alert


async def _user_contacts(
    session: AsyncSession, tenant_id: uuid.UUID, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    """E-Mail-Adresse und Mobilnummer (Mitgliedschaft) je Benutzer."""
    if not user_ids:
        return {}
    rows = await session.execute(
        select(User.id, User.email, Membership.mobile_phone)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id, User.id.in_(user_ids))
    )
    return {r.id: (r.email, r.mobile_phone) for r in rows}


async def _property_label(session: AsyncSession, ticket: Ticket) -> str | None:
    if ticket.property_id is None:
        return None
    prop = await session.get(Property, ticket.property_id)
    return f"{prop.number} {prop.name}" if prop is not None else None


async def escalate_level(
    session: AsyncSession,
    settings: Settings,
    ticket: Ticket,
    clock: SlaClock,
    rule: SlaRule | None,
    level: int,
    user_ids: list[uuid.UUID],
    role: str | None,
    on_call: OnCallSchedule | None,
) -> list[EmergencyAlert]:
    """Alarmiert eine Stufe auf allen Kanälen der Stufe (``channels_for_level``). Empfänger
    sind die Benutzer der Stufe, bei E-Mail und SMS zusätzlich die aktuelle Bereitschaft; eine
    Rolle erhält nur den internen Alarm. Versandfehler landen in ``delivery_error``."""
    alerts: list[EmergencyAlert] = []
    channels = channels_for_level(rule, level)
    targets = list(dict.fromkeys(user_ids))
    external = list(dict.fromkeys([*targets, *([on_call.user_id] if on_call else [])]))
    contacts = await _user_contacts(session, ticket.tenant_id, external)
    link = ticket_link(settings, ticket)
    for channel in channels:
        if channel == AlertChannel.INTERNAL:
            for user_id in targets or ([on_call.user_id] if on_call and not role else []):
                alerts.append(await _send_alert(session, ticket, level, str(user_id), channel))
            if role:
                alerts.append(await _send_alert(session, ticket, level, role, channel))
        elif channel == AlertChannel.EMAIL:
            subject = email_subject(ticket, level)
            body = email_body(
                ticket,
                level,
                await _property_label(session, ticket),
                clock.due_resolution_at or ticket.sla_due_at,
                link,
            )
            for user_id in external:
                address = contacts.get(user_id, ("", None))[0]
                error = (
                    await send_email(session, settings, ticket.tenant_id, address, subject, body)
                    if address
                    else "Keine E-Mail-Adresse des Benutzers gefunden."
                )
                alert = await _send_alert(
                    session, ticket, level, address or str(user_id), channel, delivery_error=error
                )
                if error is None:
                    alert.delivered_at = datetime.now(UTC)
                alerts.append(alert)
        elif channel == AlertChannel.SMS:
            gateway = await get_gateway(session, ticket.tenant_id)
            text = sms_text(ticket, level, link)
            for user_id in external:
                number = contacts.get(user_id, ("", None))[1]
                if on_call is not None and user_id == on_call.user_id and on_call.phone:
                    number = on_call.phone
                error = (
                    await send_sms(gateway, number, text)
                    if number
                    else "Keine Mobilnummer des Benutzers hinterlegt."
                )
                # Die Mobilnummer wird nicht im Klartext protokolliert, nur der Benutzer.
                alert = await _send_alert(
                    session, ticket, level, str(user_id), channel, delivery_error=error
                )
                if error is None:
                    alert.delivered_at = datetime.now(UTC)
                alerts.append(alert)
        elif channel == AlertChannel.WHATSAPP:
            wa_config = await get_whatsapp_config(session, ticket.tenant_id)
            alert_type = "emergency" if level == 0 else "sla_escalation"
            params = [f"#{ticket.number}", str(level), ticket.title[:60]]
            for user_id in external:
                number = contacts.get(user_id, ("", None))[1]
                if on_call is not None and user_id == on_call.user_id and on_call.phone:
                    number = on_call.phone
                wa_error: str | None
                if wa_config is None or not wa_config.enabled:
                    wa_error = "WhatsApp nicht eingerichtet oder deaktiviert."
                elif not number:
                    wa_error = "Keine Mobilnummer des Benutzers hinterlegt."
                else:
                    wa_error = await send_whatsapp(
                        session,
                        settings,
                        wa_config,
                        alert_id=None,
                        to=number,
                        alert_type=alert_type,
                        params=params,
                    )
                    if wa_error is not None and wa_config.sms_fallback:
                        gateway = await get_gateway(session, ticket.tenant_id)
                        fallback_error = await send_sms(
                            gateway, number, sms_text(ticket, level, link)
                        )
                        if fallback_error is None:
                            wa_error = None
                        else:
                            wa_error = f"{wa_error} SMS-Rückfall: {fallback_error}"
                alert = await _send_alert(
                    session, ticket, level, str(user_id), channel, delivery_error=wa_error
                )
                if wa_error is None:
                    alert.delivered_at = datetime.now(UTC)
                alerts.append(alert)
    return alerts


async def check_and_escalate(
    session: AsyncSession, clock: SlaClock, settings: Settings | None = None
) -> SlaColor:
    """Berechnet die Ampel neu und löst fällige Eskalationsstufen aus."""
    settings = settings or get_settings()
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
    rule = await session.get(SlaRule, clock.rule_id) if clock.rule_id else None
    due_steps = [s for s in steps if s.step_no not in clock.escalated_steps]
    on_call = await current_on_call(session, clock.tenant_id) if due_steps or not steps else None
    elapsed_minutes = int((datetime.now(UTC) - clock.started_at).total_seconds() // 60)
    for step in steps:
        if step.step_no in clock.escalated_steps or elapsed_minutes < step.after_minutes:
            continue
        await escalate_level(
            session,
            settings,
            ticket,
            clock,
            rule,
            step.step_no,
            list(step.notify_user_ids),
            step.notify_role,
            on_call,
        )
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
    if (
        not steps
        and on_call is not None
        and ticket.priority in ESCALATED_PRIORITIES
        and 0 not in clock.escalated_steps
    ):
        await escalate_level(
            session, settings, ticket, clock, rule, 0, [on_call.user_id], None, on_call
        )
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
