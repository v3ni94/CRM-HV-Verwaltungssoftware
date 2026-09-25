"""SLA-Regeln, Uhren, Eskalation, Bereitschaft und Notfallalarme (M21).

Übernommen aus dem Immoware Hub (app/Modules/Sla, docs/mail/04-status-und-sla.md): Prioritäten
folgen hier ``mhvp.tickets.models.Priority`` (low, normal, high, urgent, immediate) statt P0-P3,
da Tickets diese Skala bereits führen. Reaktion (``response_minutes``) entspricht der Uhr
``first_response``, Lösung (``resolution_minutes``) der Uhr ``resolve`` des Hubs. Die Ampel ist
grün unter 50 %, gelb ab 50 %, rot ab 100 % oder Überschreitung der Zielzeit.
"""

import uuid
from datetime import datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.tickets.models import Priority


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class ClockType(StrEnum):
    """Zeitbasis der Uhr: Geschäftszeit (Arbeitskalender) oder Kalenderzeit (rund um die Uhr,
    wie im Hub für Notfälle vorgesehen)."""

    BUSINESS = "business"
    CALENDAR = "calendar"


class ClockState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    BREACHED = "breached"
    DONE = "done"


class SlaColor(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

    def rank_value(self) -> int:
        return {"green": 0, "yellow": 1, "red": 2}[self.value]


class AlertChannel(StrEnum):
    EMAIL = "email"
    INTERNAL = "internal"
    SMS = "sms"


class SlaRule(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "sla_rule"
    __table_args__ = (UniqueConstraint("tenant_id", "priority"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[Priority] = mapped_column(_enum(Priority, "ticket_priority"), nullable=False)
    response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    clock_type: Mapped[ClockType] = mapped_column(
        _enum(ClockType, "sla_clock_type"), nullable=False, default=ClockType.BUSINESS
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Kanäle je Eskalationsstufe (M35), z. B. {"1": ["internal"], "2": ["internal", "email"]}.
    # ``None`` oder fehlende Stufe: Standard aus ``mhvp.sla.channels.DEFAULT_CHANNELS_BY_LEVEL``.
    channels_by_level: Mapped[dict[str, list[str]] | None] = mapped_column(JSONB)


class EscalationStep(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "sla_escalation_step"
    __table_args__ = (UniqueConstraint("rule_id", "step_no"),)

    rule_id: Mapped[uuid.UUID] = _fk("sla_rule.id", nullable=False, ondelete="CASCADE")
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    after_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    notify_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    notify_role: Mapped[str | None] = mapped_column(String(64))
    channel: Mapped[AlertChannel] = mapped_column(
        _enum(AlertChannel, "sla_alert_channel"), nullable=False, default=AlertChannel.EMAIL
    )


class SlaClock(IdMixin, TimestampMixin, TenantMixin, Base):
    """Eine Uhr je Ticket, mit Reaktions- und Lösungsfrist sowie Ampel
    (docs/mail/04, Abschnitt 5)."""

    __tablename__ = "sla_clock"
    __table_args__ = (UniqueConstraint("ticket_id"),)

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", nullable=False, ondelete="CASCADE")
    rule_id: Mapped[uuid.UUID | None] = _fk("sla_rule.id")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_minutes_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_resolution_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[ClockState] = mapped_column(
        _enum(ClockState, "sla_clock_state"), nullable=False, default=ClockState.RUNNING
    )
    color: Mapped[SlaColor] = mapped_column(
        _enum(SlaColor, "sla_color"), nullable=False, default=SlaColor.GREEN
    )
    escalated_steps: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)


class SlaClockLog(IdMixin, TenantMixin, Base):
    """Append-only Protokoll je Uhr (Start, Pause, Fortsetzung, Erstantwort, Lösung, Eskalation)."""

    __tablename__ = "sla_clock_log"

    clock_id: Mapped[uuid.UUID] = _fk("sla_clock.id", nullable=False, ondelete="CASCADE")
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class OnCallSchedule(IdMixin, TimestampMixin, TenantMixin, Base):
    """Bereitschaftsplan: welcher Mitarbeiter ist im Zeitraum erreichbar (Notfallkette)."""

    __tablename__ = "sla_on_call_schedule"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    phone: Mapped[str | None] = mapped_column(EncryptedText())
    note: Mapped[str | None] = mapped_column(String(500))


class EmergencyAlert(IdMixin, TenantMixin, Base):
    """Notfallalarm je Eskalationsstufe (level), mit Annahme (acknowledge)."""

    __tablename__ = "sla_emergency_alert"

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", nullable=False, ondelete="CASCADE")
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_to: Mapped[str] = mapped_column(String(300), nullable=False)
    channel: Mapped[AlertChannel] = mapped_column(
        _enum(AlertChannel, "sla_alert_channel"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Zustellung (M35): ``delivered_at`` bei erfolgreichem Versand, sonst Fehlerhinweis ohne
    # Zugangsdaten in ``delivery_error``.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_error: Mapped[str | None] = mapped_column(Text)


class SmsGateway(IdMixin, TimestampMixin, TenantMixin, Base):
    """Anbieterneutrales HTTP-SMS-Gateway je Mandant (M35). ``body_template`` ist ein JSON-String
    mit den Platzhaltern ``{to}``, ``{text}`` und optional ``{sender}``."""

    __tablename__ = "sla_sms_gateway"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    url: Mapped[str | None] = mapped_column(String(500))
    method: Mapped[str] = mapped_column(
        String(8), nullable=False, default="POST", server_default="POST"
    )
    auth_header_name: Mapped[str | None] = mapped_column(String(100))
    auth_header_value: Mapped[str | None] = mapped_column(EncryptedText())
    body_template: Mapped[str | None] = mapped_column(Text)
    sender: Mapped[str | None] = mapped_column(String(40))


class WorkCalendar(IdMixin, TimestampMixin, TenantMixin, Base):
    """Geschäftszeitenkalender je Mandant (Startvorschlag Mo-Fr 08:00-16:30, Europe/Berlin,
    docs/mail/04, Abschnitt 7). Genau eine Zeile je Mandant."""

    __tablename__ = "sla_work_calendar"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    weekdays: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=lambda: [0, 1, 2, 3, 4]
    )
    opens_at: Mapped[time] = mapped_column(Time, nullable=False, default=time(8, 0))
    closes_at: Mapped[time] = mapped_column(Time, nullable=False, default=time(16, 30))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Berlin")
    holidays: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
