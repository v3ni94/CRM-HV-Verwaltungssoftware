"""SLA-Regeln, Uhren, Bereitschaft und Notfallalarme (/api/v1/sla, M21)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.sla.escalation import current_on_call
from mhvp.sla.models import (
    AlertChannel,
    ClockState,
    ClockType,
    EmergencyAlert,
    EscalationStep,
    OnCallSchedule,
    SlaClock,
    SlaColor,
    SlaRule,
    WorkCalendar,
)
from mhvp.sla.service import get_calendar, pause_clock, recompute_color, resume_clock
from mhvp.tickets.models import Priority

router = APIRouter(prefix="/sla", tags=["SLA und Bereitschaft"])
READ = require_permission("sla:read")
MANAGE = require_permission("sla:update")
TICKETS_READ = require_permission("tickets:read")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlaRuleIn(_In):
    name: str = Field(min_length=1, max_length=200)
    priority: Priority
    response_minutes: int = Field(ge=1, le=100_000)
    resolution_minutes: int = Field(ge=1, le=1_000_000)
    clock_type: ClockType = ClockType.BUSINESS
    active: bool = True


class EscalationStepIn(_In):
    step_no: int = Field(ge=1, le=20)
    after_minutes: int = Field(ge=0, le=100_000)
    notify_user_ids: list[uuid.UUID] = Field(default_factory=list)
    notify_role: str | None = Field(default=None, max_length=64)
    channel: AlertChannel = AlertChannel.EMAIL


class OnCallIn(_In):
    user_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    phone: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class CalendarIn(_In):
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    opens_at: str = "08:00"
    closes_at: str = "16:30"
    timezone: str = "Europe/Berlin"
    holidays: list[str] = Field(default_factory=list)


def _rule_out(row: SlaRule) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "priority": row.priority.value,
        "response_minutes": row.response_minutes,
        "resolution_minutes": row.resolution_minutes,
        "clock_type": row.clock_type.value,
        "active": row.active,
    }


def _step_out(row: EscalationStep) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "rule_id": str(row.rule_id),
        "step_no": row.step_no,
        "after_minutes": row.after_minutes,
        "notify_user_ids": [str(u) for u in row.notify_user_ids],
        "notify_role": row.notify_role,
        "channel": row.channel.value,
    }


def _clock_out(row: SlaClock) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "ticket_id": str(row.ticket_id),
        "rule_id": str(row.rule_id) if row.rule_id else None,
        "started_at": row.started_at.isoformat(),
        "due_response_at": row.due_response_at.isoformat() if row.due_response_at else None,
        "due_resolution_at": row.due_resolution_at.isoformat() if row.due_resolution_at else None,
        "first_response_at": row.first_response_at.isoformat() if row.first_response_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "state": row.state.value,
        "color": row.color.value,
    }


def _on_call_out(row: OnCallSchedule) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "note": row.note,
    }


def _alert_out(row: EmergencyAlert) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "ticket_id": str(row.ticket_id),
        "level": row.level,
        "sent_to": row.sent_to,
        "channel": row.channel.value,
        "sent_at": row.sent_at.isoformat(),
        "acknowledged_by": str(row.acknowledged_by) if row.acknowledged_by else None,
        "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
    }


def _calendar_out(row: WorkCalendar) -> dict[str, Any]:
    return {
        "weekdays": row.weekdays,
        "opens_at": row.opens_at.strftime("%H:%M"),
        "closes_at": row.closes_at.strftime("%H:%M"),
        "timezone": row.timezone,
        "holidays": row.holidays,
    }


# --- Regeln ---------------------------------------------------------------


@router.get("/rules", summary="SLA-Regeln")
async def list_rules(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(select(SlaRule).order_by(SlaRule.priority))
        return [_rule_out(r) for r in rows.all()]


@router.post("/rules", status_code=201, summary="SLA-Regel anlegen")
async def create_rule(
    body: SlaRuleIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        existing = await session.scalar(
            select(SlaRule).where(
                SlaRule.tenant_id == principal.tenant_id, SlaRule.priority == body.priority
            )
        )
        if existing is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Für diese Priorität besteht bereits eine Regel."
            )
        rule = SlaRule(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(rule)
        await session.flush()
        return _rule_out(rule)


@router.patch("/rules/{rule_id}", summary="SLA-Regel ändern")
async def update_rule(
    rule_id: uuid.UUID,
    body: SlaRuleIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rule = await session.get(SlaRule, rule_id)
        if rule is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        for key, value in body.model_dump().items():
            setattr(rule, key, value)
        rule.updated_by = principal.user_id
        await session.flush()
        return _rule_out(rule)


# Vorschlagswerte für eine Hausverwaltung (Produktschutz-Vorschlag, keine Rechtsvorschrift;
# docs/OPEN_QUESTIONS.md M19-01, operator 25.09.2026): Reaktion/Lösung je Priorität in Minuten.
PRESET_RULES: dict[Priority, tuple[int, int]] = {
    Priority.IMMEDIATE: (2 * 60, 8 * 60),
    Priority.URGENT: (4 * 60, 24 * 60),
    Priority.HIGH: (8 * 60, 72 * 60),
    Priority.NORMAL: (24 * 60, 168 * 60),
    Priority.LOW: (72 * 60, 336 * 60),
}
PRESET_NAMES = {
    Priority.IMMEDIATE: "Vorschlag: Notfall",
    Priority.URGENT: "Vorschlag: Dringend",
    Priority.HIGH: "Vorschlag: Hoch",
    Priority.NORMAL: "Vorschlag: Normal",
    Priority.LOW: "Vorschlag: Niedrig",
}


@router.post(
    "/rules/presets",
    status_code=201,
    summary="Vorschlagswerte laden (Produktschutz-Vorschlag, keine Rechtsvorschrift)",
)
async def load_presets(
    request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> list[dict[str, Any]]:
    """Setzt für jede Priorität ohne bestehende Regel eine Vorschlagsregel (Antwort-/Lösungszeit)
    und den Geschäftszeitenkalender Mo-Fr 08:00-17:00 Europe/Berlin; bestehende Regeln und ein
    bereits gepflegter Kalender bleiben unverändert. Feiertage NRW pflegt der Betreiber selbst
    (``holidays`` bleibt eine einfache Liste, kein Automatismus)."""
    async with tenant_tx(request, principal) as session:
        created: list[SlaRule] = []
        for priority, (response_minutes, resolution_minutes) in PRESET_RULES.items():
            existing = await session.scalar(
                select(SlaRule).where(
                    SlaRule.tenant_id == principal.tenant_id, SlaRule.priority == priority
                )
            )
            if existing is not None:
                created.append(existing)
                continue
            rule = SlaRule(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                name=PRESET_NAMES[priority],
                priority=priority,
                response_minutes=response_minutes,
                resolution_minutes=resolution_minutes,
                clock_type=(
                    ClockType.CALENDAR if priority == Priority.IMMEDIATE else ClockType.BUSINESS
                ),
                active=True,
            )
            session.add(rule)
            await session.flush()
            created.append(rule)
        calendar = await get_calendar(session, principal.tenant_id)
        if (
            calendar.weekdays == [0, 1, 2, 3, 4]
            and calendar.opens_at.strftime("%H:%M") == "08:00"
            and calendar.closes_at.strftime("%H:%M") == "16:30"
        ):
            # Nur der Standard aus der Modellvorgabe wird durch den Vorschlag 08:00-17:00
            # ersetzt; ein bereits abweichend gepflegter Kalender bleibt unangetastet.
            from datetime import time as _time

            calendar.closes_at = _time(17, 0)
            calendar.timezone = "Europe/Berlin"
        await session.flush()
        return [_rule_out(r) for r in created]


@router.delete("/rules/{rule_id}", status_code=204, summary="SLA-Regel löschen")
async def delete_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> None:
    async with tenant_tx(request, principal) as session:
        rule = await session.get(SlaRule, rule_id)
        if rule is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        await session.delete(rule)


@router.get("/rules/{rule_id}/steps", summary="Eskalationsstufen einer Regel")
async def list_steps(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(EscalationStep)
            .where(EscalationStep.rule_id == rule_id)
            .order_by(EscalationStep.step_no)
        )
        return [_step_out(r) for r in rows.all()]


@router.post("/rules/{rule_id}/steps", status_code=201, summary="Eskalationsstufe anlegen")
async def create_step(
    rule_id: uuid.UUID,
    body: EscalationStepIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rule = await session.get(SlaRule, rule_id)
        if rule is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        step = EscalationStep(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            rule_id=rule_id,
            **body.model_dump(),
        )
        session.add(step)
        await session.flush()
        return _step_out(step)


@router.delete("/steps/{step_id}", status_code=204, summary="Eskalationsstufe löschen")
async def delete_step(
    step_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> None:
    async with tenant_tx(request, principal) as session:
        step = await session.get(EscalationStep, step_id)
        if step is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        await session.delete(step)


# --- Uhren -----------------------------------------------------------------


@router.get("/clocks", summary="SLA-Uhren")
async def list_clocks(
    request: Request,
    state: ClockState | None = None,
    color: SlaColor | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(SlaClock)
        if state:
            query = query.where(SlaClock.state == state)
        if color:
            query = query.where(SlaClock.color == color)
        rows = await session.scalars(query.order_by(SlaClock.started_at.desc()).limit(limit))
        return [_clock_out(r) for r in rows.all()]


@router.get("/tickets/{ticket_id}/sla", summary="SLA-Uhr eines Tickets")
async def ticket_clock(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(TICKETS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket_id))
        if clock is None:
            raise ProblemError(ErrorCodes.NOT_FOUND, detail="Für dieses Ticket läuft keine Uhr.")
        await recompute_color(session, principal.tenant_id, clock)
        return _clock_out(clock)


@router.post("/clocks/{clock_id}/pause", summary="Uhr pausieren")
async def pause(
    clock_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        clock = await session.get(SlaClock, clock_id)
        if clock is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        await pause_clock(session, clock)
        return _clock_out(clock)


@router.post("/clocks/{clock_id}/resume", summary="Uhr fortsetzen")
async def resume(
    clock_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        clock = await session.get(SlaClock, clock_id)
        if clock is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        await resume_clock(session, principal.tenant_id, clock)
        return _clock_out(clock)


# --- Bereitschaft ------------------------------------------------------------


@router.get("/on-call", summary="Bereitschaftsplan")
async def list_on_call(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(OnCallSchedule).order_by(OnCallSchedule.starts_at.desc())
        )
        return [_on_call_out(r) for r in rows.all()]


@router.get("/on-call/current", summary="Aktuelle Bereitschaft")
async def get_current_on_call(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any] | None:
    async with tenant_tx(request, principal) as session:
        row = await current_on_call(session, principal.tenant_id)
        return _on_call_out(row) if row else None


@router.post("/on-call", status_code=201, summary="Bereitschaft eintragen")
async def create_on_call(
    body: OnCallIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    if body.ends_at <= body.starts_at:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ende muss nach dem Beginn liegen.")
    async with tenant_tx(request, principal) as session:
        row = OnCallSchedule(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _on_call_out(row)


@router.delete("/on-call/{on_call_id}", status_code=204, summary="Bereitschaft löschen")
async def delete_on_call(
    on_call_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(OnCallSchedule, on_call_id)
        if row is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        await session.delete(row)


# --- Notfallalarme -----------------------------------------------------------


@router.get("/alerts", summary="Notfallalarme")
async def list_alerts(
    request: Request,
    unacknowledged: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(EmergencyAlert)
        if unacknowledged:
            query = query.where(EmergencyAlert.acknowledged_at.is_(None))
        rows = await session.scalars(query.order_by(EmergencyAlert.sent_at.desc()).limit(limit))
        return [_alert_out(r) for r in rows.all()]


@router.post("/alerts/{alert_id}/ack", summary="Notfallalarm bestätigen")
async def ack_alert(
    alert_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        alert = await session.get(EmergencyAlert, alert_id)
        if alert is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        if alert.acknowledged_at is None:
            alert.acknowledged_by, alert.acknowledged_at = principal.user_id, datetime.now(UTC)
        return _alert_out(alert)


# --- Kalender -----------------------------------------------------------------


@router.get("/calendar", summary="Geschäftszeitenkalender")
async def get_calendar_endpoint(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        calendar = await get_calendar(session, principal.tenant_id)
        return _calendar_out(calendar)


@router.put("/calendar", summary="Geschäftszeitenkalender ändern")
async def put_calendar(
    body: CalendarIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    from datetime import time as _time

    async with tenant_tx(request, principal) as session:
        calendar = await get_calendar(session, principal.tenant_id)
        try:
            opens = _time.fromisoformat(body.opens_at)
            closes = _time.fromisoformat(body.closes_at)
        except ValueError as exc:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Uhrzeit im Format HH:MM erwartet."
            ) from exc
        if not all(0 <= d <= 6 for d in body.weekdays):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Wochentage 0 (Montag) bis 6 (Sonntag)."
            )
        calendar.weekdays = body.weekdays
        calendar.opens_at = opens
        calendar.closes_at = closes
        calendar.timezone = body.timezone
        calendar.holidays = body.holidays
        calendar.updated_by = principal.user_id
        await session.flush()
        return _calendar_out(calendar)
