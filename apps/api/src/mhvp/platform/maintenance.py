"""Maintenance windows and monthly availability (AD10: GB16-01, GB16-02, section 16).

* Platform administrators announce windows (``/platform/maintenance-windows``); CRM and portal
  show a banner from the lead time before the start (``GET /platform/maintenance/current``,
  public, no personal data), the status page reads the same endpoint.
* The availability target is 99,5 percent per month. The figures come from the external
  monitoring (Uptime Kuma) and are imported per month and measuring point
  (``PUT /platform/availability``); nothing is measured or invented here. Announced windows are
  planned downtime and are shown separately (``GET /platform/availability``).

Platform tables without RLS; every change is written to the platform audit.
"""

from __future__ import annotations

import calendar
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import AvailabilityMeasurement, MaintenanceWindow, PlatformAuditEvent

router = APIRouter(tags=["Plattform"])

TARGET_PERCENT = Decimal("99.5")
PROBES = ("api", "crm", "portal")
Probe = Literal["api", "crm", "portal"]
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_PCT = Decimal("0.001")


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _audit(
    session: Any, principal: Principal, action: str, target_id: str, payload: dict[str, Any]
) -> None:
    session.add(
        PlatformAuditEvent(
            actor_user_id=principal.user_id,
            action=action,
            target_type="maintenance_window"
            if action.startswith("maintenance")
            else "availability_measurement",
            target_id=target_id,
            payload=payload,
        )
    )


def phase_of(window: MaintenanceWindow, now: datetime, default_notice_hours: int) -> str:
    """scheduled (not yet shown), announced, active, ended or cancelled."""
    if window.cancelled_at is not None:
        return "cancelled"
    notice = window.notice_hours if window.notice_hours is not None else default_notice_hours
    if now >= window.ends_at:
        return "ended"
    if now >= window.starts_at:
        return "active"
    if now >= window.starts_at - timedelta(hours=notice):
        return "announced"
    return "scheduled"


# Windows ---------------------------------------------------------------------------------


class MaintenanceWindowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime
    text_de: str = Field(min_length=3, max_length=500)
    text_en: str = Field(min_length=3, max_length=500)
    notice_hours: int | None = Field(default=None, ge=0, le=720)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Zeitangabe mit Zeitzone erforderlich.")
        return value.astimezone(UTC)


class MaintenanceWindowPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    text_de: str | None = Field(default=None, min_length=3, max_length=500)
    text_en: str | None = Field(default=None, min_length=3, max_length=500)
    notice_hours: int | None = Field(default=None, ge=0, le=720)
    cancel: bool | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Zeitangabe mit Zeitzone erforderlich.")
        return value.astimezone(UTC) if value is not None else None


class MaintenanceWindowOut(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    text_de: str
    text_en: str
    notice_hours: int | None
    cancelled_at: datetime | None
    phase: str


class MaintenancePublicItem(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    text_de: str
    text_en: str
    phase: Literal["announced", "active"]


class MaintenanceCurrentOut(BaseModel):
    status: Literal["operational", "maintenance"]
    items: list[MaintenancePublicItem]


def _out(row: MaintenanceWindow, now: datetime, default_notice: int) -> MaintenanceWindowOut:
    return MaintenanceWindowOut(
        id=row.id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        text_de=row.text_de,
        text_en=row.text_en,
        notice_hours=row.notice_hours,
        cancelled_at=row.cancelled_at,
        phase=phase_of(row, now, default_notice),
    )


def _snapshot(row: MaintenanceWindow) -> dict[str, Any]:
    return {
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "notice_hours": row.notice_hours,
        "cancelled": row.cancelled_at is not None,
    }


@router.get(
    "/platform/maintenance/current",
    summary="Aktuelle und angekündigte Wartungsfenster (öffentlich, für Banner und Statusseite)",
    dependencies=[Depends(strict_query)],
)
async def current_maintenance(request: Request, response: Response) -> MaintenanceCurrentOut:
    default_notice = _settings(request).maintenance_notice_hours
    now = datetime.now(UTC)
    async with platform_transaction(sessions(request)) as session:
        rows = await session.scalars(
            select(MaintenanceWindow)
            .where(
                MaintenanceWindow.cancelled_at.is_(None),
                MaintenanceWindow.ends_at > now,
                MaintenanceWindow.starts_at <= now + timedelta(hours=720),
            )
            .order_by(MaintenanceWindow.starts_at)
        )
        items = [
            MaintenancePublicItem(
                id=r.id,
                starts_at=r.starts_at,
                ends_at=r.ends_at,
                text_de=r.text_de,
                text_en=r.text_en,
                phase=phase,
            )
            for r in rows
            if (phase := phase_of(r, now, default_notice)) in ("announced", "active")
        ]
    response.headers["Cache-Control"] = "public, max-age=30"
    return MaintenanceCurrentOut(
        status="maintenance" if any(i.phase == "active" for i in items) else "operational",
        items=items,
    )


@router.get(
    "/platform/maintenance-windows",
    summary="Wartungsfenster auflisten",
    dependencies=[Depends(strict_query)],
)
async def list_maintenance_windows(
    request: Request,
    limit: int = Query(100, ge=1, le=200),
    _: Principal = Depends(require_platform_admin),
) -> list[MaintenanceWindowOut]:
    default_notice = _settings(request).maintenance_notice_hours
    now = datetime.now(UTC)
    async with platform_transaction(sessions(request)) as session:
        rows = await session.scalars(
            select(MaintenanceWindow).order_by(MaintenanceWindow.starts_at.desc()).limit(limit)
        )
        return [_out(r, now, default_notice) for r in rows]


@router.post("/platform/maintenance-windows", status_code=201, summary="Wartungsfenster ankündigen")
async def create_maintenance_window(
    body: MaintenanceWindowIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> MaintenanceWindowOut:
    if body.ends_at <= body.starts_at:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Ende muss nach dem Beginn liegen.")
    now = datetime.now(UTC)
    async with platform_transaction(sessions(request)) as session:
        row = MaintenanceWindow(
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            text_de=body.text_de.strip(),
            text_en=body.text_en.strip(),
            notice_hours=body.notice_hours,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        _audit(session, principal, "maintenance_window_created", str(row.id), _snapshot(row))
        await session.refresh(row)
        return _out(row, now, _settings(request).maintenance_notice_hours)


@router.patch(
    "/platform/maintenance-windows/{window_id}", summary="Wartungsfenster ändern oder absagen"
)
async def update_maintenance_window(
    window_id: uuid.UUID,
    body: MaintenanceWindowPatch,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> MaintenanceWindowOut:
    now = datetime.now(UTC)
    async with platform_transaction(sessions(request)) as session:
        row = await session.get(MaintenanceWindow, window_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.cancelled_at is not None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Das Wartungsfenster ist abgesagt.")
        before = _snapshot(row)
        fields = body.model_fields_set - {"cancel"}
        for name in fields:
            value = getattr(body, name)
            if value is None and name != "notice_hours":
                continue
            setattr(row, name, value.strip() if isinstance(value, str) else value)
        if row.ends_at <= row.starts_at:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Das Ende muss nach dem Beginn liegen."
            )
        action = "maintenance_window_updated"
        if body.cancel:
            row.cancelled_at = now
            action = "maintenance_window_cancelled"
        row.updated_by = principal.user_id
        _audit(session, principal, action, str(row.id), {"before": before, "after": _snapshot(row)})
        await session.flush()
        await session.refresh(row)
        return _out(row, now, _settings(request).maintenance_notice_hours)


# Availability ----------------------------------------------------------------------------


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: str
    probe: Probe
    uptime_percent: Decimal = Field(ge=0, le=100, max_digits=12, decimal_places=6)
    source_note: str = Field(min_length=3, max_length=200)

    @field_validator("month")
    @classmethod
    def _month(cls, value: str) -> str:
        if not _MONTH.match(value):
            raise ValueError("Monat im Format JJJJ-MM erforderlich.")
        return value


class ProbeFigure(BaseModel):
    probe: str
    uptime_percent: Decimal | None
    source_note: str | None
    adjusted_percent: Decimal | None
    target_met: bool | None
    target_met_adjusted: bool | None


class AvailabilityMonth(BaseModel):
    month: str
    month_seconds: int
    planned_downtime_seconds: int
    probes: list[ProbeFigure]
    actual_percent: Decimal | None
    adjusted_percent: Decimal | None
    target_met: bool | None
    target_met_adjusted: bool | None


class AvailabilityOut(BaseModel):
    target_percent: Decimal
    months: list[AvailabilityMonth]


def _month_bounds(first: date) -> tuple[datetime, datetime]:
    last = calendar.monthrange(first.year, first.month)[1]
    start = datetime(first.year, first.month, 1, tzinfo=UTC)
    return start, start + timedelta(days=last)


def planned_downtime_seconds(
    windows: list[MaintenanceWindow], start: datetime, end: datetime, until: datetime
) -> int:
    """Union of the non cancelled windows inside [start, min(end, until)) in seconds; overlapping
    windows are counted once. Windows still in the future count only as far as they have passed."""
    stop = min(end, until)
    spans = sorted(
        (max(w.starts_at, start), min(w.ends_at, stop))
        for w in windows
        if w.cancelled_at is None and w.ends_at > start and w.starts_at < stop
    )
    total = 0.0
    cur_s: datetime | None = None
    cur_e: datetime | None = None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_s is not None and cur_e is not None:
                total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
        elif e > cur_e:
            cur_e = e
    if cur_s is not None and cur_e is not None:
        total += (cur_e - cur_s).total_seconds()
    return int(total)


def adjusted_percent(uptime: Decimal, month_seconds: int, planned_seconds: int) -> Decimal:
    """Availability without the announced windows: the downtime derived from the imported figure
    is reduced by the planned downtime (upper bound, never below zero downtime). Orientation only,
    because the monitoring does not say whether the window really was down."""
    down = Decimal(month_seconds) * (Decimal(100) - uptime) / Decimal(100)
    unplanned = max(down - Decimal(planned_seconds), Decimal(0))
    pct = Decimal(100) - unplanned * Decimal(100) / Decimal(month_seconds)
    return pct.quantize(_PCT, rounding=ROUND_HALF_UP)


@router.put("/platform/availability", summary="Monatszahl der Verfügbarkeit importieren")
async def import_availability(
    body: AvailabilityIn, request: Request, principal: Principal = Depends(require_platform_admin)
) -> ProbeFigure:
    year, mon = (int(x) for x in body.month.split("-"))
    first = date(year, mon, 1)
    today = datetime.now(UTC).date()
    if first > today.replace(day=1):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Monat liegt in der Zukunft.")
    async with platform_transaction(sessions(request)) as session:
        row = await session.scalar(
            select(AvailabilityMeasurement)
            .where(
                AvailabilityMeasurement.month == first, AvailabilityMeasurement.probe == body.probe
            )
            .with_for_update()
        )
        before = None
        if row is None:
            row = AvailabilityMeasurement(
                month=first,
                probe=body.probe,
                uptime_percent=body.uptime_percent,
                source_note=body.source_note.strip(),
                created_by=principal.user_id,
                updated_by=principal.user_id,
            )
            session.add(row)
        else:
            before = str(row.uptime_percent)
            row.uptime_percent = body.uptime_percent
            row.source_note = body.source_note.strip()
            row.updated_by = principal.user_id
        await session.flush()
        _audit(
            session,
            principal,
            "availability_measurement_recorded",
            f"{body.month}:{body.probe}",
            {
                "uptime_percent": str(body.uptime_percent),
                "before": before,
                "source_note": body.source_note.strip(),
            },
        )
        windows = list(await session.scalars(select(MaintenanceWindow)))
    start, end = _month_bounds(first)
    seconds = int((end - start).total_seconds())
    planned = planned_downtime_seconds(windows, start, end, datetime.now(UTC))
    return _figure(body.probe, body.uptime_percent, body.source_note, seconds, planned)


def _figure(
    probe: str, uptime: Decimal | None, note: str | None, seconds: int, planned: int
) -> ProbeFigure:
    if uptime is None:
        return ProbeFigure(
            probe=probe,
            uptime_percent=None,
            source_note=None,
            adjusted_percent=None,
            target_met=None,
            target_met_adjusted=None,
        )
    adj = adjusted_percent(uptime, seconds, planned)
    return ProbeFigure(
        probe=probe,
        uptime_percent=uptime,
        source_note=note,
        adjusted_percent=adj,
        target_met=uptime >= TARGET_PERCENT,
        target_met_adjusted=adj >= TARGET_PERCENT,
    )


@router.get(
    "/platform/availability",
    summary="Verfügbarkeit je Monat gegen das Ziel 99,5 Prozent",
    dependencies=[Depends(strict_query)],
)
async def availability(
    request: Request,
    months: int = Query(12, ge=1, le=36),
    _: Principal = Depends(require_platform_admin),
) -> AvailabilityOut:
    now = datetime.now(UTC)
    cur = date(now.year, now.month, 1)
    firsts: list[date] = []
    y, m = cur.year, cur.month
    for _i in range(months):
        firsts.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    async with platform_transaction(sessions(request)) as session:
        rows = list(
            await session.scalars(
                select(AvailabilityMeasurement).where(AvailabilityMeasurement.month.in_(firsts))
            )
        )
        windows = list(await session.scalars(select(MaintenanceWindow)))
    by_key = {(r.month, r.probe): r for r in rows}
    out: list[AvailabilityMonth] = []
    for first in firsts:
        start, end = _month_bounds(first)
        seconds = int((end - start).total_seconds())
        planned = planned_downtime_seconds(windows, start, end, now)
        figures = []
        for probe in PROBES:
            r = by_key.get((first, probe))
            figures.append(
                _figure(
                    probe,
                    r.uptime_percent if r else None,
                    r.source_note if r else None,
                    seconds,
                    planned,
                )
            )
        measured = [f for f in figures if f.uptime_percent is not None]
        # The weakest measuring point decides: the target holds only if every point reaches it.
        actual = min((f.uptime_percent for f in measured), default=None)  # type: ignore[type-var]
        adj = min((f.adjusted_percent for f in measured), default=None)  # type: ignore[type-var]
        complete = len(measured) == len(PROBES)
        out.append(
            AvailabilityMonth(
                month=f"{first.year:04d}-{first.month:02d}",
                month_seconds=seconds,
                planned_downtime_seconds=planned,
                probes=figures,
                actual_percent=actual,
                adjusted_percent=adj,
                target_met=(actual >= TARGET_PERCENT) if actual is not None and complete else None,
                target_met_adjusted=(adj >= TARGET_PERCENT)
                if adj is not None and complete
                else None,
            )
        )
    return AvailabilityOut(target_percent=TARGET_PERCENT, months=out)
