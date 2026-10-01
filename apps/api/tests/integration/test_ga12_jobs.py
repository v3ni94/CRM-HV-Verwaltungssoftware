"""GA12-01 and GA12-06: tenant switch of the standard jobs and double effect of the beat jobs
(repeat, parallel manual and scheduled run, clock change in Europe/Berlin)."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from mhvp.accounting.direct_debit_models import PaymentRunPreview, PaymentRunSetting
from mhvp.accounting.models import DunningRun, Ledger
from mhvp.automation.job_schedule import in_window
from mhvp.automation.models import JOB_CATALOG, TenantJobSchedule
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.platform import services
from mhvp.properties.models import LegalEntity, LegalEntityKind
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


def utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


# ---------------------------------------------------------------------- clock change (no DB)


def _ticks_in_window(run_at: str, day: date) -> list[datetime]:
    """15 minute beat ticks over the local day (Europe/Berlin) that fall in the window."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Berlin")
    start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
    end = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(days=1)
    end = datetime(end.year, end.month, end.day, tzinfo=tz).astimezone(UTC)
    ticks = []
    t = start
    while t < end:
        ticks.append(t)
        t += timedelta(minutes=15)
    return [t for t in ticks if in_window(run_at, t)]


def test_catalogue_has_no_platform_wide_job_and_has_payment_preview() -> None:
    assert "ops-backup-verify" not in JOB_CATALOG
    assert "payments-payment-run-preview" in JOB_CATALOG


@pytest.mark.parametrize("run_at", ["01:30", "02:30", "03:00", "06:30"])
def test_window_opens_once_on_spring_forward_day(run_at: str) -> None:
    """29.03.2026: 02:00 CET jumps to 03:00 CEST. A frequent beat finds one window of 60
    minutes (4 ticks), also for a start time inside the missing hour."""
    ticks = _ticks_in_window(run_at, date(2026, 3, 29))
    assert len(ticks) == 4, ticks
    # contiguous: one window, not two
    assert ticks[-1] - ticks[0] == timedelta(minutes=45)


@pytest.mark.parametrize("run_at", ["01:30", "02:30", "03:00", "06:30"])
def test_window_opens_once_on_fall_back_day(run_at: str) -> None:
    """25.10.2026: 03:00 CEST falls back to 02:00 CET, the local hour 02:00 occurs twice. The
    window opens once (4 ticks), never a second time in the repeated hour."""
    ticks = _ticks_in_window(run_at, date(2026, 10, 25))
    assert len(ticks) == 4, ticks
    assert ticks[-1] - ticks[0] == timedelta(minutes=45)


def test_window_boundaries_summer_and_winter_time() -> None:
    assert in_window("06:30", utc(2026, 7, 1, 4, 30))  # CEST
    assert not in_window("06:30", utc(2026, 7, 1, 5, 30))
    assert in_window("06:30", utc(2026, 12, 1, 5, 30))  # CET
    assert not in_window("06:30", utc(2026, 12, 1, 4, 30))
    # fall back day: 02:30 CEST (00:30 UTC) opens, 02:30 CET (01:30 UTC) does not open again
    assert in_window("02:30", utc(2026, 10, 25, 0, 30))
    assert not in_window("02:30", utc(2026, 10, 25, 1, 30))
    assert not in_window("02:30", utc(2026, 10, 25, 1, 45))


@pytest.mark.parametrize("day", [date(2026, 3, 29), date(2026, 10, 25), date(2026, 7, 1)])
def test_beat_entries_fire_at_most_once_per_local_day(day: date) -> None:
    """Every beat entry with a fixed time of day (Celery crontab, Europe/Berlin) is due at most
    once per local day, also on the clock change days 29.03.2026 and 25.10.2026; entries that run
    every hour are due at most once per hour and local day."""
    from datetime import time
    from zoneinfo import ZoneInfo

    from celery.schedules import crontab

    from mhvp.worker import create_celery

    app = create_celery(set_as_current=False)
    assert app.conf.timezone == "Europe/Berlin"
    tz = ZoneInfo("Europe/Berlin")
    start = datetime.combine(day, time(0), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
    checked = 0
    for name, entry in app.conf.beat_schedule.items():
        sched = entry["schedule"]
        if not isinstance(sched, crontab):
            continue
        sched.app = app
        last = start - timedelta(seconds=1)
        fires = 0
        for _ in range(60):
            last_run, delta, _now = sched.remaining_delta(last)
            nxt = last_run + delta
            nxt = nxt if nxt.tzinfo else nxt.replace(tzinfo=tz)
            if nxt >= end:
                break
            fires += 1
            last = nxt
        hourly = len(sched.hour) == 24
        assert fires <= (25 if hourly else 1), (name, day, fires)
        checked += 1
    assert checked > 20


# ---------------------------------------------------------------------- database part


@pytest.fixture(scope="module")
def tenants(database: Database, redis_url: str) -> dict[str, uuid.UUID]:
    settings = _settings(database, redis_url)

    async def build() -> dict[str, uuid.UUID]:
        from mhvp.core import crypto

        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            a, _ = await services.provision_tenant(factory, slug=f"ga12-{RUN}", name=f"GA12 {RUN}")
            return {"a": a}
        finally:
            await engine.dispose()

    return asyncio.run(build())


def _factory(settings: Any) -> tuple[Any, Any]:
    engine = create_app_engine(settings)
    return engine, create_session_factory(engine)


async def _set_job(settings: Any, tenant: uuid.UUID, job: str, enabled: bool) -> None:
    engine, factory = _factory(settings)
    try:
        async with tenant_transaction(factory, tenant) as session:
            row = await session.scalar(
                select(TenantJobSchedule).where(TenantJobSchedule.job_key == job)
            )
            if row is None:
                session.add(
                    TenantJobSchedule(tenant_id=tenant, job_key=job, enabled=enabled, run_at=None)
                )
            else:
                row.enabled = enabled
    finally:
        await engine.dispose()


def test_disabled_payment_preview_job_is_skipped_and_enabled_runs_once_in_parallel(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID]
) -> None:
    from mhvp.banking.payment_run_tasks import weekly_previews

    settings = _settings(database, redis_url)
    tenant = tenants["a"]

    async def count() -> int:
        engine, factory = _factory(settings)
        try:
            async with tenant_transaction(factory, tenant) as session:
                return int(
                    await session.scalar(
                        select(func.count())
                        .select_from(PaymentRunPreview)
                        .where(PaymentRunPreview.trigger == "schedule")
                    )
                    or 0
                )
        finally:
            await engine.dispose()

    async def enable_setting() -> None:
        engine, factory = _factory(settings)
        try:
            async with tenant_transaction(factory, tenant) as session:
                session.add(PaymentRunSetting(tenant_id=tenant, weekly_preview_enabled=True))
        finally:
            await engine.dispose()

    asyncio.run(enable_setting())
    asyncio.run(_set_job(settings, tenant, "payments-payment-run-preview", False))
    asyncio.run(weekly_previews(settings))
    assert asyncio.run(count()) == 0  # switched off: skipped

    asyncio.run(_set_job(settings, tenant, "payments-payment-run-preview", True))

    async def parallel() -> None:
        await asyncio.gather(weekly_previews(settings), weekly_previews(settings))
        await weekly_previews(settings)  # a repeat

    asyncio.run(parallel())
    assert asyncio.run(count()) == 1  # parallel and repeated runs: one preview per day


def test_dunning_job_switch_and_single_scheduled_run_per_day(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.accounting import tasks as acc_tasks

    settings = _settings(database, redis_url)
    tenant = tenants["a"]
    calls: list[uuid.UUID] = []

    async def fake_preview(session: Any, *, tenant_id: Any, user_id: Any, run_date: date) -> Any:
        calls.append(tenant_id)
        run = DunningRun(tenant_id=tenant_id, created_by=user_id, run_date=run_date)
        session.add(run)
        await session.flush()
        return run

    monkeypatch.setattr(acc_tasks.dunning, "preview", fake_preview)

    async def make_ledger() -> None:
        engine, factory = _factory(settings)
        try:
            async with tenant_transaction(factory, tenant) as session:
                entity = LegalEntity(
                    tenant_id=tenant, kind=LegalEntityKind.MANAGER, name="Muster Verwaltung GmbH"
                )
                session.add(entity)
                await session.flush()
                session.add(Ledger(tenant_id=tenant, legal_entity_id=entity.id, name="Muster"))
        finally:
            await engine.dispose()

    asyncio.run(make_ledger())
    asyncio.run(_set_job(settings, tenant, "accounting-dunning-run", False))
    asyncio.run(acc_tasks.dunning_previews(settings))
    assert tenant not in calls  # switched off

    asyncio.run(_set_job(settings, tenant, "accounting-dunning-run", True))

    async def parallel() -> None:
        await asyncio.gather(
            acc_tasks.dunning_previews(settings), acc_tasks.dunning_previews(settings)
        )
        await acc_tasks.dunning_previews(settings)

    asyncio.run(parallel())
    assert calls.count(tenant) == 1  # parallel and repeated scheduled runs: one run per day


def test_reconciliation_report_honours_job_switch(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.imports import reconciliation as rec
    from mhvp.imports import tasks as imp_tasks

    settings = _settings(database, redis_url)
    tenant = tenants["a"]
    seen: list[str] = []

    async def fake_sources(session: Any) -> list[Any]:
        seen.append("called")
        return []

    monkeypatch.setattr(rec, "latest_sources", fake_sources)
    asyncio.run(_set_job(settings, tenant, "imports-reconciliation-report", False))
    result = asyncio.run(imp_tasks.report_tenant_once(settings, tenant, trigger="beat"))
    assert result["skipped"] == 1
    assert seen == []  # scheduled run honours the switch
    manual = asyncio.run(imp_tasks.report_tenant_once(settings, tenant, trigger="manual"))
    assert manual["skipped"] == 1
    assert seen == ["called"]  # manual run is not blocked
    asyncio.run(_set_job(settings, tenant, "imports-reconciliation-report", True))
    asyncio.run(imp_tasks.report_tenant_once(settings, tenant, trigger="beat"))
    assert seen == ["called", "called"]


def test_document_intake_honours_job_switch(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.documents import distribution, intake

    settings = _settings(database, redis_url)
    tenant = tenants["a"]
    processed: list[uuid.UUID] = []

    async def fake_process(*args: Any, **kwargs: Any) -> dict[str, int]:
        processed.append(args[3])
        return {intake.SOURCE_PAPERLESS: 0, intake.SOURCE_DRIVE: 0, intake.SOURCE_MAILBOX: 0}

    async def fake_distribute(*args: Any, **kwargs: Any) -> int:
        return 0

    monkeypatch.setattr(intake, "process_tenant_inbox", fake_process)
    monkeypatch.setattr(distribution, "distribute_shared_mailboxes", fake_distribute)

    class _Http:
        async def aclose(self) -> None:
            return None

    asyncio.run(_set_job(settings, tenant, "documents-process-inbox", False))
    asyncio.run(intake.process_inbox_once(settings, client=_Http(), blobs=object()))  # type: ignore[arg-type]
    assert tenant not in processed
    asyncio.run(_set_job(settings, tenant, "documents-process-inbox", True))
    asyncio.run(intake.process_inbox_once(settings, client=_Http(), blobs=object()))  # type: ignore[arg-type]
    assert tenant in processed


def test_workspace_jobs_are_idempotent_on_repeat_and_in_parallel(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID]
) -> None:
    """Digest, deadline list and reminders: a repeated and a parallel run of the same day add
    nothing to the first run (digest_run, deadline rows and reminders are unique per day)."""
    from mhvp.workspace.tasks import deadlines_once, digest_once, reminders_once

    settings = _settings(database, redis_url)
    today = date(2026, 10, 25)  # the fall back day of the clock change

    async def scenario() -> list[tuple[dict[str, int], dict[str, int]]]:
        out = []
        for job in (digest_once, deadlines_once, reminders_once):
            first = await job(settings, today)  # type: ignore[operator]
            again = await asyncio.gather(job(settings, today), job(settings, today))  # type: ignore[operator]
            out.append((first, again[0] | {"x": 0}))
            for result in again:
                for key in ("created", "notified", "users"):
                    assert result.get(key, 0) == 0 or key == "users", (job.__name__, result)
        return out

    asyncio.run(scenario())
