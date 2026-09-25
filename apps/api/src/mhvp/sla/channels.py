"""Zustellkanäle der SLA-Eskalation (M35): Kanalauswahl je Stufe, E-Mail als Systemmail über
den bestehenden Mailtransport (ohne Vier-Augen-Freigabe) und SMS über ein anbieterneutrales
HTTP-Gateway. Fehler werden als Text ohne Zugangsdaten zurückgegeben und am Alarm in
``delivery_error`` vermerkt; die Eskalation bricht dabei nie ab."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import transport
from mhvp.communication.models import Mailbox
from mhvp.core.config import Settings
from mhvp.sla.models import AlertChannel, SlaRule, SmsGateway
from mhvp.tickets.models import Priority, Ticket

SMS_TIMEOUT_SECONDS = 10.0
SMS_TEST_TEXT = "Testnachricht MH Verwaltungsplattform"
DISPLAY_TZ = ZoneInfo("Europe/Berlin")

# Standard je Stufe (M35). Stufe 0 ist die Bereitschaftsalarmierung ohne Eskalationsstufen
# bei Notfall- und Dringend-Tickets; Stufen über 3 verhalten sich wie Stufe 3.
DEFAULT_CHANNELS_BY_LEVEL: dict[int, tuple[AlertChannel, ...]] = {
    0: (AlertChannel.INTERNAL, AlertChannel.EMAIL, AlertChannel.SMS),
    1: (AlertChannel.INTERNAL,),
    2: (AlertChannel.INTERNAL, AlertChannel.EMAIL),
    3: (AlertChannel.INTERNAL, AlertChannel.EMAIL, AlertChannel.SMS),
}

PRIORITY_LABELS = {
    Priority.LOW: "Niedrig",
    Priority.NORMAL: "Normal",
    Priority.HIGH: "Hoch",
    Priority.URGENT: "Dringend",
    Priority.IMMEDIATE: "Notfall",
}


def channels_for_level(rule: SlaRule | None, level: int) -> list[AlertChannel]:
    """Kanäle der Stufe: Regelwert ``channels_by_level[str(level)]``, sonst Standard."""
    configured = (rule.channels_by_level or {}).get(str(level)) if rule is not None else None
    if configured is not None:
        known = {c.value for c in AlertChannel}
        return list(dict.fromkeys(AlertChannel(c) for c in configured if c in known))
    return list(DEFAULT_CHANNELS_BY_LEVEL[min(max(level, 0), 3)])


def validate_channels_by_level(value: dict[str, list[str]] | None) -> str | None:
    """Fehlertext oder ``None``: Schlüssel sind Stufen 0 bis 20, Werte bekannte Kanäle."""
    if value is None:
        return None
    known = {c.value for c in AlertChannel}
    for key, channels in value.items():
        if not key.isdigit() or not 0 <= int(key) <= 20:
            return f"Ungültige Stufe {key!r}, erwartet 0 bis 20."
        unknown = [c for c in channels if c not in known]
        if unknown:
            return f"Unbekannte Kanäle: {', '.join(unknown)}."
    return None


def ticket_link(settings: Settings, ticket: Ticket) -> str | None:
    if not settings.web_crm_url:
        return None
    return f"{settings.web_crm_url.rstrip('/')}/tickets/{ticket.id}"


def _fmt(value: datetime | None) -> str:
    if value is None:
        return "nicht gesetzt"
    return value.astimezone(DISPLAY_TZ).strftime("%d.%m.%Y %H:%M") + " Uhr"


def email_subject(ticket: Ticket, level: int) -> str:
    return f"SLA-Eskalation Stufe {level}: Ticket #{ticket.number} {ticket.title}"


def email_body(
    ticket: Ticket,
    level: int,
    property_label: str | None,
    due_at: datetime | None,
    link: str | None,
) -> str:
    lines = [
        f"Das Ticket #{ticket.number} hat die SLA-Zielzeit überschritten (Stufe {level}).",
        "",
        f"Titel: {ticket.title}",
        f"Objekt: {property_label or 'ohne Objekt'}",
        f"Priorität: {PRIORITY_LABELS.get(ticket.priority, ticket.priority.value)}",
        f"Fälligkeit: {_fmt(due_at)}",
        f"Link: {link or 'MHVP_WEB_CRM_URL nicht konfiguriert'}",
        "",
        "Diese Nachricht wurde automatisch von der MH Verwaltungsplattform versendet.",
    ]
    return "\n".join(lines)


def sms_text(ticket: Ticket, level: int, link: str | None) -> str:
    prio = PRIORITY_LABELS.get(ticket.priority, ticket.priority.value)
    text = f"SLA-Eskalation Stufe {level}: Ticket #{ticket.number} {ticket.title[:80]}, {prio}"
    return f"{text}, {link}" if link else text


def render_sms_body(template: str, to: str, text: str, sender: str | None) -> str:
    """Setzt ``{to}``, ``{text}`` und ``{sender}`` JSON-sicher ein und prüft das Ergebnis."""

    def esc(value: str) -> str:
        return json.dumps(value)[1:-1]

    body = (
        template.replace("{to}", esc(to))
        .replace("{text}", esc(text))
        .replace("{sender}", esc(sender or ""))
    )
    json.loads(body)  # ValueError bei ungültigem Template
    return body


async def get_gateway(session: AsyncSession, tenant_id: uuid.UUID) -> SmsGateway | None:
    gateway: SmsGateway | None = await session.scalar(
        select(SmsGateway).where(SmsGateway.tenant_id == tenant_id)
    )
    return gateway


async def send_sms(
    gateway: SmsGateway | None,
    to: str,
    text: str,
    *,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> str | None:
    """Sendet eine SMS; liefert ``None`` bei Erfolg, sonst Fehlertext ohne Zugangsdaten."""
    if gateway is None or not gateway.enabled:
        return "SMS-Gateway nicht eingerichtet oder deaktiviert."
    if not gateway.url or not gateway.body_template:
        return "SMS-Gateway unvollständig: URL oder Vorlage fehlt."
    if not to.strip():
        return "Keine Mobilnummer hinterlegt."
    try:
        body = render_sms_body(gateway.body_template, to.strip(), text, gateway.sender)
    except ValueError:
        return "SMS-Vorlage ergibt kein gültiges JSON."
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if gateway.auth_header_name and gateway.auth_header_value:
        headers[gateway.auth_header_name] = gateway.auth_header_value
    try:
        async with httpx.AsyncClient(
            timeout=SMS_TIMEOUT_SECONDS, transport=http_transport
        ) as client:
            response = await client.request(
                gateway.method or "POST", gateway.url, content=body, headers=headers
            )
    except httpx.TimeoutException:
        return "SMS-Gateway antwortet nicht (Zeitüberschreitung 10 s)."
    except httpx.HTTPError as exc:
        return f"SMS-Gateway nicht erreichbar ({type(exc).__name__})."
    if response.status_code >= 400:
        return f"SMS-Gateway meldet HTTP {response.status_code}."
    return None


async def default_mailbox(session: AsyncSession, tenant_id: uuid.UUID) -> Mailbox | None:
    box: Mailbox | None = await session.scalar(
        select(Mailbox)
        .where(Mailbox.tenant_id == tenant_id, Mailbox.enabled.is_(True))
        .order_by(Mailbox.is_default.desc(), Mailbox.created_at)
        .limit(1)
    )
    return box


async def send_email(
    session: AsyncSession,
    settings: Settings,
    tenant_id: uuid.UUID,
    to: str,
    subject: str,
    body: str,
) -> str | None:
    """Systemmail ohne Freigabeprozess; ``None`` bei Erfolg, sonst Fehlertext."""
    box = await default_mailbox(session, tenant_id)
    if box is None or not transport.is_sendable(box):
        return "Kein Postfach für den Versand eingerichtet (M20-01)."
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = box.address, to, subject
    msg["Message-ID"] = make_msgid(domain=box.address.rsplit("@", 1)[-1] or None)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body)
    try:
        await transport.send_message(session, settings, box, msg)
    except transport.MailTransportError as exc:
        return str(exc)[:500]
    return None
