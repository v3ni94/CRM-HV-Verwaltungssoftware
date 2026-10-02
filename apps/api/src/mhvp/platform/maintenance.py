"""Maintenance windows and monthly availability (AD10: GB16-01, GB16-02, section 16).

* Platform administrators announce windows (``/platform/maintenance-windows``); CRM and portal
  show a banner from the lead time before the start (``GET /platform/maintenance/current``,
  public, no personal data), the status page reads the same endpoint.
* The availability target is 99,5 percent per month. The figures come from the external
  monitoring (Uptime Kuma) and are imported per month and measuring point
  (``PUT /platform/availability``); nothing is measured or invented here. Announced windows are
  planned downtime and are shown separately (``GET /platform/availability``).

* AE35: the platform also measures itself (``availability_probe``: minute checks of the health
  URLs, daily evaluation per month). ``GET /platform/availability`` shows the own measurement
  next to the imported figures; ``PUT /platform/availability/settings`` holds the switch whether
  announced windows count as downtime (open question AD10-02, default: they do not count).

Platform tables without RLS; every change is written to the platform audit.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.clock import local_today
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform import availability_probe as probe_lib
from mhvp.platform.availability_probe import PROBES, TARGET_PERCENT, url_host
from mhvp.platform.models import (
    AvailabilityMeasurement,
    AvailabilityProbePoint,
    MaintenanceWindow,
    PlatformAuditEvent,
)
from mhvp.platform.models import AvailabilityMonth as AvailabilityMonthRow
from mhvp.platform.services import platform_settings

router = APIRouter(tags=["Plattform"])

Probe = Literal["api", "crm", "portal"]
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_PCT = Decimal("0.001")


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _audit(
    session: Any, principal: Principal, action: str, target_id: str, payload: dict[str, Any]
) -> None:
    if action.startswith("maintenance"):
        target_type = "maintenance_window"
    elif action.startswith("availability_setting"):
        target_type = "availability_setting"
    else:
        target_type = "availability_measurement"
    session.add(
        PlatformAuditEvent(
            actor_user_id=principal.user_id,
            action=action,
            target_type=target_type,
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


class AvailabilitySelfFigure(BaseModel):
    """Own measurement of one measuring point and month (AE35)."""

    probe: str
    checks_total: int
    checks_ok: int
    checks_maintenance: int
    failed_in_maintenance: int
    expected_checks: int
    coverage_percent: Decimal
    uptime_gross: Decimal
    uptime_net: Decimal | None
    counted_percent: Decimal | None
    target_met: bool | None
    final: bool


class AvailabilityMonth(BaseModel):
    month: str
    month_seconds: int
    planned_downtime_seconds: int
    probes: list[ProbeFigure]
    actual_percent: Decimal | None
    adjusted_percent: Decimal | None
    target_met: bool | None
    target_met_adjusted: bool | None
    # AE35: own measurement. ``self_gross_percent`` and ``self_net_percent`` are the weakest
    # measuring point (all checks / without the announced windows); ``self_counted_percent`` is
    # the one the switch selects; the rating needs all three points with enough coverage.
    self_probes: list[AvailabilitySelfFigure] = []
    self_gross_percent: Decimal | None = None
    self_net_percent: Decimal | None = None
    self_counted_percent: Decimal | None = None
    self_failed_in_maintenance_minutes: int | None = None
    self_coverage_percent: Decimal | None = None
    self_target_met: bool | None = None
    self_final: bool | None = None


class AvailabilityOut(BaseModel):
    target_percent: Decimal
    # AD10-02 switch: announced maintenance windows count as downtime in the own measurement.
    maintenance_counts_as_downtime: bool = False
    min_coverage_percent: Decimal = probe_lib.MIN_COVERAGE_PERCENT
    months: list[AvailabilityMonth]


class AvailabilitySettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maintenance_counts_as_downtime: bool


class AvailabilitySettingsOut(BaseModel):
    maintenance_counts_as_downtime: bool
    updated_by: uuid.UUID | None
    updated_at: datetime


class AvailabilityLiveProbe(BaseModel):
    probe: str
    configured: bool
    host: str | None
    last_checked_at: datetime | None
    last_ok: bool | None
    last_status_code: int | None
    last_latency_ms: int | None
    last_error_class: str | None
    checks_24h: int
    ok_24h: int
    percent_24h: Decimal | None


class AvailabilityFailure(BaseModel):
    probe: str
    slot: datetime
    status_code: int | None
    error_class: str | None


class AvailabilityLiveOut(BaseModel):
    probes: list[AvailabilityLiveProbe]
    recent_failures: list[AvailabilityFailure]
    retention_days: int
    maintenance_counts_as_downtime: bool
    min_coverage_percent: Decimal


_month_bounds = probe_lib.month_bounds


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
    today = local_today()
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
        own_rows = list(
            await session.scalars(
                select(AvailabilityMonthRow).where(AvailabilityMonthRow.month.in_(firsts))
            )
        )
        counts_maintenance = await probe_lib.maintenance_counts_as_downtime(session)
    by_key = {(r.month, r.probe): r for r in rows}
    own_by_key = {(r.month, r.probe): r for r in own_rows}
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
        own = [
            _self_figure(own_by_key[(first, p)], counts_maintenance)
            for p in PROBES
            if (first, p) in own_by_key
        ]
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
                **_self_month_fields(own, counts_maintenance),
            )
        )
    return AvailabilityOut(
        target_percent=TARGET_PERCENT,
        maintenance_counts_as_downtime=counts_maintenance,
        months=out,
    )


def _self_figure(row: AvailabilityMonthRow, counts_maintenance: bool) -> AvailabilitySelfFigure:
    coverage = probe_lib.coverage_percent(row.checks_total, row.expected_checks)
    counted = probe_lib.counted_percent(row.uptime_gross, row.uptime_net, counts_maintenance)
    return AvailabilitySelfFigure(
        probe=row.probe,
        checks_total=row.checks_total,
        checks_ok=row.checks_ok,
        checks_maintenance=row.checks_maintenance,
        failed_in_maintenance=row.checks_maintenance - row.checks_ok_maintenance,
        expected_checks=row.expected_checks,
        coverage_percent=coverage,
        uptime_gross=row.uptime_gross,
        uptime_net=row.uptime_net,
        counted_percent=counted,
        target_met=probe_lib.rated(counted, coverage),
        final=row.final,
    )


def _self_month_fields(
    own: list[AvailabilitySelfFigure], counts_maintenance: bool
) -> dict[str, Any]:
    """Month level figures of the own measurement. The weakest measuring point decides, and a
    rating needs all three points with enough coverage (as for the imported figures)."""
    if not own:
        return {}
    counted = [f.counted_percent for f in own if f.counted_percent is not None]
    nets = [f.uptime_net for f in own if f.uptime_net is not None]
    coverage = min(f.coverage_percent for f in own)
    complete = len(own) == len(PROBES)
    weakest = min(counted) if counted and len(counted) == len(own) else None
    return {
        "self_probes": own,
        "self_gross_percent": min(f.uptime_gross for f in own),
        "self_net_percent": min(nets) if len(nets) == len(own) else None,
        "self_counted_percent": weakest,
        "self_failed_in_maintenance_minutes": max(f.failed_in_maintenance for f in own),
        "self_coverage_percent": coverage,
        "self_target_met": probe_lib.rated(weakest, coverage) if complete else None,
        "self_final": all(f.final for f in own),
    }


@router.put(
    "/platform/availability/settings",
    summary="Schalter: Wartungsfenster zählen als Ausfall (AD10-02)",
)
async def set_availability_settings(
    body: AvailabilitySettingsIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> AvailabilitySettingsOut:
    async with platform_transaction(sessions(request)) as session:
        row = await platform_settings(session)
        before = row.maintenance_counts_as_downtime
        if before != body.maintenance_counts_as_downtime:
            row.maintenance_counts_as_downtime = body.maintenance_counts_as_downtime
            row.version += 1
            row.updated_by = principal.user_id
            _audit(
                session,
                principal,
                "availability_setting_changed",
                "maintenance_counts_as_downtime",
                {"before": before, "after": body.maintenance_counts_as_downtime},
            )
            await session.flush()
            await session.refresh(row)
        return AvailabilitySettingsOut(
            maintenance_counts_as_downtime=row.maintenance_counts_as_downtime,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )


@router.get(
    "/platform/availability/live",
    summary="Eigenmessung: letzte Prüfungen, 24 Stunden und Fehlschläge",
    dependencies=[Depends(strict_query)],
)
async def availability_live(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> AvailabilityLiveOut:
    settings = _settings(request)
    urls = {
        "api": settings.availability_api_url,
        "crm": settings.availability_crm_url,
        "portal": settings.availability_portal_url,
    }
    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    point = AvailabilityProbePoint
    probes: list[AvailabilityLiveProbe] = []
    async with platform_transaction(sessions(request)) as session:
        for name in PROBES:
            last = await session.scalar(
                select(point).where(point.probe == name).order_by(point.slot.desc()).limit(1)
            )
            total, ok = (
                await session.execute(
                    select(func.count(), func.count().filter(point.ok.is_(True))).where(
                        point.probe == name, point.slot >= since
                    )
                )
            ).one()
            probes.append(
                AvailabilityLiveProbe(
                    probe=name,
                    configured=bool(urls[name]),
                    host=url_host(urls[name]),
                    last_checked_at=last.slot if last else None,
                    last_ok=last.ok if last else None,
                    last_status_code=last.status_code if last else None,
                    last_latency_ms=last.latency_ms if last else None,
                    last_error_class=last.error_class if last else None,
                    checks_24h=int(total),
                    ok_24h=int(ok),
                    percent_24h=probe_lib.percent(int(ok), int(total)),
                )
            )
        failures = list(
            await session.scalars(
                select(point).where(point.ok.is_(False)).order_by(point.slot.desc()).limit(10)
            )
        )
        counts_maintenance = await probe_lib.maintenance_counts_as_downtime(session)
    return AvailabilityLiveOut(
        probes=probes,
        recent_failures=[
            AvailabilityFailure(
                probe=f.probe, slot=f.slot, status_code=f.status_code, error_class=f.error_class
            )
            for f in failures
        ],
        retention_days=settings.availability_retention_days,
        maintenance_counts_as_downtime=counts_maintenance,
        min_coverage_percent=probe_lib.MIN_COVERAGE_PERCENT,
    )
