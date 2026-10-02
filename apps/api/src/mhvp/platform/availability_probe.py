"""Own availability measurement (AE35: GB16-02, open question AD10-02, section 16).

A beat job checks the health URLs of API, CRM and portal every minute and stores one measuring
point per measuring point and minute (``platform_availability_probe_point``). A daily job evaluates
every month per measuring point (``platform_availability_month``): the figure counting every check
(gross) and the figure that leaves out the checks inside announced maintenance windows (net). The
platform switch ``maintenance_counts_as_downtime`` (default off) only decides which of the two is
rated against the target of 99,5 percent; both are always shown. A third job deletes minute points
after the retention period, but only for months that have been evaluated and frozen.

Limits that are shown to the operator, not hidden: the check runs on the same infrastructure as
the platform, so a total outage of the host leaves a gap instead of failed checks. Gaps are not
counted as downtime but lower the coverage; a month is only rated if the coverage reaches
``MIN_COVERAGE_PERCENT`` (open question AE35-01). Nothing here books, sends or deletes domain
data. The HTTP client is injectable, so tests never touch the network.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Any
from urllib.parse import urlsplit

import httpx
from celery import shared_task
from sqlalchemy import Date, and_, cast, delete, exists, false, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.ids import uuid7
from mhvp.platform.models import (
    AvailabilityMonth,
    AvailabilityProbePoint,
    MaintenanceWindow,
    PlatformSettings,
)

log = logging.getLogger(__name__)

TARGET_PERCENT = Decimal("99.5")
PROBES = ("api", "crm", "portal")
# A month is rated only if at least this share of the expected minute checks exists (the check
# runs on the platform's own infrastructure, so a host outage shows up as a gap). Product
# protection, no legal value (open question AE35-01).
MIN_COVERAGE_PERCENT = Decimal("95")
_PERCENT_STEP = Decimal("0.00000001")
_COVERAGE_STEP = Decimal("0.001")
PURGE_BATCH = 10_000


def month_bounds(first: date) -> tuple[datetime, datetime]:
    """[start, end) of the calendar month in UTC."""
    last = calendar.monthrange(first.year, first.month)[1]
    start = datetime(first.year, first.month, 1, tzinfo=UTC)
    return start, start + timedelta(days=last)


def slot_of(moment: datetime) -> datetime:
    """The minute (UTC) a check belongs to."""
    return moment.astimezone(UTC).replace(second=0, microsecond=0)


# Pure figures (no database) -----------------------------------------------------------------


def percent(part: int, whole: int) -> Decimal | None:
    """``part / whole`` in percent, rounded down (never overstates availability); None if
    ``whole`` is zero."""
    if whole <= 0:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(_PERCENT_STEP, rounding=ROUND_FLOOR)


def coverage_percent(checks_total: int, expected_checks: int) -> Decimal:
    """Share of the expected minute checks that exist, at most 100."""
    if expected_checks <= 0:
        return Decimal(0).quantize(_COVERAGE_STEP)
    value = Decimal(checks_total) * 100 / Decimal(expected_checks)
    return min(value, Decimal(100)).quantize(_COVERAGE_STEP, rounding=ROUND_FLOOR)


@dataclass(frozen=True)
class MonthFigures:
    checks_total: int
    checks_ok: int
    checks_maintenance: int
    checks_ok_maintenance: int
    expected_checks: int
    uptime_gross: Decimal
    uptime_net: Decimal | None


def month_figures(
    *,
    total: int,
    ok: int,
    maintenance: int,
    ok_maintenance: int,
    expected: int,
) -> MonthFigures:
    """Gross: all checks. Net: checks inside announced windows are left out of both counts."""
    gross = percent(ok, total)
    if gross is None:
        raise ValueError("a month figure needs at least one check")
    return MonthFigures(
        checks_total=total,
        checks_ok=ok,
        checks_maintenance=maintenance,
        checks_ok_maintenance=ok_maintenance,
        expected_checks=expected,
        uptime_gross=gross,
        uptime_net=percent(ok - ok_maintenance, total - maintenance),
    )


def counted_percent(
    gross: Decimal, net: Decimal | None, counts_maintenance: bool
) -> Decimal | None:
    """The figure rated against the target: gross if maintenance counts as downtime (switch on),
    otherwise the figure without the maintenance windows."""
    return gross if counts_maintenance else net


def rated(counted: Decimal | None, coverage: Decimal) -> bool | None:
    """Target met? None if there is no figure or the coverage is too low to rate the month."""
    if counted is None or coverage < MIN_COVERAGE_PERCENT:
        return None
    return counted >= TARGET_PERCENT


# Probe --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeResult:
    probe: str
    ok: bool
    status_code: int | None
    latency_ms: int | None
    error_class: str | None


def missing_probe_urls(settings: Settings) -> list[str]:
    """Measuring points without a configured health URL (deploy variables
    ``MHVP_AVAILABILITY_{API,CRM,PORTAL}_URL``), in the fixed order of ``PROBES``."""
    urls = settings.availability_probe_urls
    return [probe for probe in PROBES if probe not in urls]


_warned_missing = False


def warn_missing_probe_urls(settings: Settings, *, once: bool = True) -> list[str]:
    """Logs a warning for every measuring point without a URL (GAE-33). Staging and production
    expect all three; in dev and test a missing URL only gets an info line. With ``once`` the
    message is written once per process (the beat job runs every minute). Returns the missing
    measuring points; changes nothing else."""
    global _warned_missing
    missing = missing_probe_urls(settings)
    if not missing or (once and _warned_missing):
        return missing
    _warned_missing = True
    expected = settings.env.value in ("staging", "prod")
    level = logging.WARNING if expected else logging.INFO
    names = ", ".join(f"MHVP_AVAILABILITY_{probe.upper()}_URL" for probe in missing)
    suffix = (
        " (availability measurement is off for all measuring points)"
        if len(missing) == len(PROBES)
        else " (these measuring points are not measured)"
    )
    log.log(level, "availability measurement: deploy variable(s) not set: %s%s", names, suffix)
    return missing


async def check_url(
    client: httpx.AsyncClient, probe: str, url: str, timeout_seconds: float
) -> ProbeResult:
    """One health request. Only a 2xx answer counts as available (a redirect or 503 does not).
    The failure class is a fixed short string; neither the URL nor the exception text is kept."""
    started = time.perf_counter()
    status: int | None = None
    error: str | None = None
    try:
        response = await client.get(url, timeout=timeout_seconds, follow_redirects=False)
        status = response.status_code
        if not 200 <= status < 300:
            error = "http_status"
    except httpx.TimeoutException:
        error = "timeout"
    except httpx.ConnectError:
        error = "connect_error"
    except httpx.HTTPError:
        error = "http_error"
    except Exception:  # one broken check must never stop the other measuring points
        error = "error"
    latency = int((time.perf_counter() - started) * 1000)
    return ProbeResult(
        probe=probe,
        ok=error is None,
        status_code=status,
        latency_ms=latency if status is not None else None,
        error_class=error,
    )


async def run_probes_once(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, bool]:
    """Checks every configured measuring point and stores one point per probe and minute
    (idempotent: a repeated run in the same minute keeps the first result). Returns the result
    per probe; without a configured URL nothing happens."""
    warn_missing_probe_urls(settings)
    urls = settings.availability_probe_urls
    if not urls:
        return {}
    slot = slot_of(now or datetime.now(UTC))
    http = client or httpx.AsyncClient(headers={"User-Agent": "mhvp-availability/1"})
    try:
        results = await asyncio.gather(
            *(
                check_url(http, probe, url, settings.availability_timeout_seconds)
                for probe, url in urls.items()
            )
        )
    finally:
        if client is None:
            await http.aclose()
    for result in results:
        if not result.ok:
            log.warning(
                "availability check failed: probe=%s class=%s status=%s",
                result.probe,
                result.error_class,
                result.status_code,
            )
    engine = None
    factory = session_factory
    if factory is None:
        engine = create_async_engine(
            settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
        )
        factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            stmt = (
                pg_insert(AvailabilityProbePoint)
                .values(
                    [
                        {
                            "id": uuid7(),
                            "probe": r.probe,
                            "slot": slot,
                            "ok": r.ok,
                            "status_code": r.status_code,
                            "latency_ms": r.latency_ms,
                            "error_class": r.error_class,
                        }
                        for r in results
                    ]
                )
                .on_conflict_do_nothing(
                    constraint="uq_platform_availability_probe_point_probe_slot"
                )
            )
            await session.execute(stmt)
    finally:
        if engine is not None:
            await engine.dispose()
    return {r.probe: r.ok for r in results}


# Evaluation ---------------------------------------------------------------------------------


def _month_expr() -> Any:
    return cast(func.date_trunc("month", func.timezone("UTC", AvailabilityProbePoint.slot)), Date)


async def evaluate_months(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Evaluates every (probe, month) that has minute points and no frozen result: the running
    month provisionally, ended months finally. Frozen rows are never recomputed. Returns the
    number of provisional and final rows written."""
    point = AvailabilityProbePoint
    frozen = {
        (r.month, r.probe)
        for r in await session.execute(
            select(AvailabilityMonth.month, AvailabilityMonth.probe).where(
                AvailabilityMonth.final.is_(True)
            )
        )
    }
    month_col = _month_expr().label("month")
    pairs = [
        (probe, month)
        for probe, month in (
            await session.execute(
                select(point.probe, month_col)
                .group_by(point.probe, month_col)
                .order_by(month_col, point.probe)
            )
        ).all()
        if (month, probe) not in frozen
    ]
    if not pairs:
        return {"provisional": 0, "final": 0}
    windows = list(
        await session.scalars(
            select(MaintenanceWindow).where(MaintenanceWindow.cancelled_at.is_(None))
        )
    )
    written = {"provisional": 0, "final": 0}
    for probe, month in pairs:
        start, end = month_bounds(month)
        is_final = end <= now
        spans = [
            and_(point.slot >= max(w.starts_at, start), point.slot < min(w.ends_at, end))
            for w in windows
            if w.ends_at > start and w.starts_at < end
        ]
        in_window = or_(*spans) if spans else false()
        row = (
            await session.execute(
                select(
                    func.count(),
                    func.count().filter(point.ok.is_(True)),
                    func.count().filter(in_window),
                    func.count().filter(and_(point.ok.is_(True), in_window)),
                ).where(point.probe == probe, point.slot >= start, point.slot < end)
            )
        ).one()
        total, ok, maintenance, ok_maintenance = (int(x) for x in row)
        if total == 0:
            continue
        passed = end if is_final else min(end, now)
        expected = max(int((passed - start).total_seconds() // 60), 1)
        figures = month_figures(
            total=total,
            ok=ok,
            maintenance=maintenance,
            ok_maintenance=ok_maintenance,
            expected=expected,
        )
        existing = await session.scalar(
            select(AvailabilityMonth)
            .where(AvailabilityMonth.month == month, AvailabilityMonth.probe == probe)
            .with_for_update()
        )
        target = existing if existing is not None else AvailabilityMonth(month=month, probe=probe)
        target.checks_total = figures.checks_total
        target.checks_ok = figures.checks_ok
        target.checks_maintenance = figures.checks_maintenance
        target.checks_ok_maintenance = figures.checks_ok_maintenance
        target.expected_checks = figures.expected_checks
        target.uptime_gross = figures.uptime_gross
        target.uptime_net = figures.uptime_net
        target.final = is_final
        target.computed_at = now
        if existing is None:
            session.add(target)
        written["final" if is_final else "provisional"] += 1
    await session.flush()
    return written


async def _with_factory(settings: Settings, work: Any) -> Any:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        return await work(create_session_factory(engine))
    finally:
        await engine.dispose()


async def evaluate_months_once(
    settings: Settings,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, int]:
    moment = now or datetime.now(UTC)

    async def work(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
        async with platform_transaction(factory) as session:
            return await evaluate_months(session, moment)

    if session_factory is not None:
        return await work(session_factory)
    result: dict[str, int] = await _with_factory(settings, work)
    return result


async def purge_points(
    session: AsyncSession, now: datetime, retention_days: int, batch: int = PURGE_BATCH
) -> int:
    """Deletes minute points older than the retention period, but only those of months that
    have a frozen evaluation for the same measuring point. Returns the number of deleted rows."""
    point = AvailabilityProbePoint
    cutoff = now - timedelta(days=retention_days)
    evaluated = exists().where(
        AvailabilityMonth.probe == point.probe,
        AvailabilityMonth.month == _month_expr(),
        AvailabilityMonth.final.is_(True),
    )
    deleted = 0
    while True:
        ids = list(
            await session.scalars(
                select(point.id).where(point.slot < cutoff, evaluated).limit(batch)
            )
        )
        if not ids:
            return deleted
        await session.execute(delete(point).where(point.id.in_(ids)))
        deleted += len(ids)


async def purge_points_once(
    settings: Settings,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, int]:
    """Löschlauf: first evaluates every ended month (catch up), then deletes the old points of
    the evaluated months. If the evaluation fails, nothing is deleted."""
    moment = now or datetime.now(UTC)

    async def work(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
        async with platform_transaction(factory) as session:
            await evaluate_months(session, moment)
            deleted = await purge_points(session, moment, settings.availability_retention_days)
        return {"deleted": deleted}

    if session_factory is not None:
        return await work(session_factory)
    result: dict[str, int] = await _with_factory(settings, work)
    return result


async def maintenance_counts_as_downtime(session: AsyncSession) -> bool:
    """The platform switch (AD10-02); a missing settings row means off."""
    value = await session.scalar(select(PlatformSettings.maintenance_counts_as_downtime).limit(1))
    return bool(value)


def url_host(url: str | None) -> str | None:
    """Host (and port) of a configured URL for display; path, query and credentials stay hidden."""
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.hostname:
        return None
    return f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname


# Celery tasks -------------------------------------------------------------------------------


@shared_task(name="mhvp.platform.availability_probe")
def availability_probe() -> dict[str, bool]:
    return asyncio.run(run_probes_once(get_settings()))


@shared_task(name="mhvp.platform.availability_evaluate")
def availability_evaluate() -> dict[str, int]:
    return asyncio.run(evaluate_months_once(get_settings()))


@shared_task(name="mhvp.platform.availability_purge")
def availability_purge() -> dict[str, int]:
    return asyncio.run(purge_points_once(get_settings()))
