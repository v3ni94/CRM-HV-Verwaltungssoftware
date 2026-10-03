"""AP08 (GAM-510): task level tests of the beat jobs ``core.auth.session_metadata_purge``,
``contracts.expire_mandates``, ``banking.weekly_digest`` and ``hoa.inspection_ownership_scan``
with two tenants: job switch, repetition without double effect and fault isolation (a failure
in tenant A must not keep tenant B from its run).

Expected values for the purge by hand: fixed moment 03.10.2026 12:00 UTC, grace 90 days, cutoff
05.07.2026 12:00 UTC. Rows ended one second before the cutoff lose their device description,
rows ended one second after keep it; a second run at the same moment changes nothing (0, 0).

The domain functions of the other three jobs (``expire_due_mandates``, ``digest.build_week``,
``note_ownership_transfers``) have their own tests; here they are replaced by recorders so the
job layer (tenant iteration, RLS context, ``job_allowed``, isolation) is checked."""

import asyncio
import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from mhvp.automation.models import TenantJobSchedule
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform import services
from mhvp.platform.models import RefreshToken, TrustedDevice
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, _settings

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
CUTOFF = NOW - timedelta(days=90)


@pytest.fixture(scope="module")
def tenants(database: Database, redis_url: str) -> dict[str, Any]:
    settings = _settings(database, redis_url)

    async def build() -> dict[str, Any]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            a, _ = await services.provision_tenant(
                factory, slug=f"w26ma-{RUN}", name=f"W26MA {RUN}"
            )
            b, _ = await services.provision_tenant(
                factory, slug=f"w26mb-{RUN}", name=f"W26MB {RUN}"
            )
            users = {}
            for name, tenant in (("w26ma", a), ("w26mb", b)):
                uid = await services.create_user(
                    factory,
                    email=f"{name}-{RUN}@example.org",
                    display_name=name,
                    password=PASSWORD,
                )
                await services.add_member(
                    factory,
                    tenant_id=tenant,
                    user_id=uid,
                    role_codes=["read_only"],
                    actor_user_id=None,
                )
                users[tenant] = uid
            return {"a": a, "b": b, "users": users}
        finally:
            await engine.dispose()

    return asyncio.run(build())


def _failing_tenant(monkeypatch: pytest.MonkeyPatch, module: Any, bad: uuid.UUID) -> None:
    original = module.tenant_transaction

    @asynccontextmanager
    async def wrapped(factory: Any, tenant_id: uuid.UUID) -> Any:
        if tenant_id == bad:
            raise RuntimeError("w26 injected tenant failure")
        async with original(factory, tenant_id) as session:
            yield session

    monkeypatch.setattr(module, "tenant_transaction", wrapped)


def _run(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "w26 injected" not in str(exc):
            raise
        return None


async def _rls_tenant(session: Any) -> uuid.UUID:
    return uuid.UUID(str(await session.scalar(text("select current_setting('app.tenant_id')"))))


def _recorder(calls: list[tuple[uuid.UUID, uuid.UUID]], result: Any) -> Any:
    """Records (RLS tenant of the session, tenant argument or RLS tenant) per call."""

    async def fake(session: Any, *args: Any, **kwargs: Any) -> Any:
        rls = await _rls_tenant(session)
        arg = kwargs.get("tenant_id") or next((a for a in args if isinstance(a, uuid.UUID)), rls)
        calls.append((rls, arg))
        return result

    return fake


async def _set_job(settings: Any, tenant: uuid.UUID, job: str, enabled: bool) -> None:
    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant) as session:
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


def _mine(calls: list[tuple[uuid.UUID, uuid.UUID]], tenants: dict[str, Any]) -> list[str]:
    names = {tenants["a"]: "a", tenants["b"]: "b"}
    out = []
    for rls, arg in calls:
        if rls in names:
            assert rls == arg, "job passed a tenant id different from its RLS context"
            out.append(names[rls])
    return sorted(out)


# ------------------------------------------------------------------ session metadata purge


def test_session_metadata_purge_cutoff_two_tenants_and_repeat(
    database: Database, redis_url: str, tenants: dict[str, Any]
) -> None:
    from mhvp.core.auth.session_purge import purge_session_metadata_once

    settings = _settings(database, redis_url)
    before, after = CUTOFF - timedelta(seconds=1), CUTOFF + timedelta(seconds=1)
    far = NOW + timedelta(days=30)
    # (key, tenant, expires_at, revoked_at, purged?)
    specs = [
        ("exp-before", "a", before, None, True),
        ("exp-after", "a", after, None, False),
        ("rev-before", "b", far, before, True),
        ("rev-after", "b", far, after, False),
        ("active", "b", far, None, False),
    ]
    ids: dict[str, tuple[uuid.UUID, uuid.UUID]] = {}

    def h(key: str, kind: str) -> str:
        return hashlib.sha256(f"w26-{kind}-{key}-{RUN}".encode()).hexdigest()

    async def seed() -> None:
        engine = create_app_engine(settings)
        try:
            async with platform_transaction(create_session_factory(engine)) as session:
                for key, t, exp, rev, _ in specs:
                    tenant = tenants[t]
                    user = tenants["users"][tenant]
                    tok = RefreshToken(
                        user_id=user,
                        family_id=uuid.uuid4(),
                        token_hash=h(key, "rt"),
                        tenant_id=tenant,
                        user_agent=f"W26 Agent {key}",
                        issued_at=NOW - timedelta(days=200),
                        expires_at=exp,
                        revoked_at=rev,
                    )
                    dev = TrustedDevice(
                        user_id=user,
                        tenant_id=tenant,
                        token_hash=h(key, "td"),
                        label=f"W26 Device {key}",
                        expires_at=exp,
                        revoked_at=rev,
                    )
                    session.add_all([tok, dev])
                    await session.flush()
                    ids[key] = (tok.id, dev.id)
        finally:
            await engine.dispose()

    async def state() -> dict[str, tuple[str | None, str | None]]:
        engine = create_app_engine(settings)
        try:
            async with platform_transaction(create_session_factory(engine)) as session:
                out = {}
                for key, (tid, did) in ids.items():
                    tok = await session.get(RefreshToken, tid)
                    dev = await session.get(TrustedDevice, did)
                    assert tok is not None
                    assert dev is not None
                    out[key] = (tok.user_agent, dev.label)
                return out
        finally:
            await engine.dispose()

    asyncio.run(seed())
    first = asyncio.run(purge_session_metadata_once(settings, now=NOW))
    assert first["refresh_tokens"] >= 2
    assert first["trusted_devices"] >= 2
    expected = {
        key: (None, None) if purged else (f"W26 Agent {key}", f"W26 Device {key}")
        for key, _, _, _, purged in specs
    }
    assert asyncio.run(state()) == expected
    # Repetition at the same moment: nothing left to blank, rows still exist.
    assert asyncio.run(purge_session_metadata_once(settings, now=NOW)) == {
        "refresh_tokens": 0,
        "trusted_devices": 0,
    }
    assert asyncio.run(state()) == expected


# ------------------------------------------------------------------ contracts.expire_mandates


def test_expire_mandates_job_runs_per_tenant_and_isolates_failures(
    database: Database,
    redis_url: str,
    tenants: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mhvp.contracts import tasks

    settings = _settings(database, redis_url)
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []
    seen_days: list[date] = []
    rec = _recorder(calls, 0)

    async def fake(session: Any, today: date) -> int:
        seen_days.append(today)
        return int(await rec(session))

    monkeypatch.setattr(tasks, "expire_due_mandates", fake)
    day = date(2026, 10, 3)
    assert asyncio.run(tasks.expire_mandates_once(settings, today=day)) == {"expired": 0}
    assert _mine(calls, tenants) == ["a", "b"]
    assert set(seen_days) == {day}
    calls.clear()
    _failing_tenant(monkeypatch, tasks, tenants["a"])
    _run(tasks.expire_mandates_once(settings, today=day))
    assert _mine(calls, tenants) == ["b"], "a failure in tenant A stopped tenant B"


# ------------------------------------------------------------------ banking.weekly_digest


def test_weekly_digest_job_switch_repeat_and_isolation(
    database: Database,
    redis_url: str,
    tenants: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mhvp.banking import digest, tasks

    settings = _settings(database, redis_url)
    # Monday 05.10.2026 -> previous ISO week starts Monday 28.09.2026.
    monday = date(2026, 10, 5)
    # Real domain function first: tenants without automatic postings get no digest, twice.
    for _ in range(2):
        asyncio.run(tasks.weekly_digest_once(settings, today=monday))

    calls: list[tuple[uuid.UUID, uuid.UUID]] = []
    weeks: list[date] = []
    rec = _recorder(calls, [])

    async def fake(session: Any, *, tenant_id: uuid.UUID, week_start: date, **_: Any) -> Any:
        weeks.append(week_start)
        return await rec(session, tenant_id=tenant_id)

    monkeypatch.setattr(digest, "build_week", fake)
    asyncio.run(_set_job(settings, tenants["a"], "banking-weekly-digest", False))
    asyncio.run(tasks.weekly_digest_once(settings, today=monday))
    assert _mine(calls, tenants) == ["b"], "disabled job ran in tenant A"
    assert set(weeks) == {date(2026, 9, 28)}
    asyncio.run(_set_job(settings, tenants["a"], "banking-weekly-digest", True))
    calls.clear()
    _failing_tenant(monkeypatch, tasks, tenants["a"])
    _run(tasks.weekly_digest_once(settings, today=monday))
    assert _mine(calls, tenants) == ["b"], "a failure in tenant A stopped tenant B"


# ------------------------------------------------------------------ hoa.inspection_ownership_scan


def test_inspection_scan_runs_per_tenant_and_repeats_without_effect(
    database: Database,
    redis_url: str,
    tenants: dict[str, Any],
) -> None:
    from mhvp.hoa import inspection_transfer

    settings = _settings(database, redis_url)
    # Real run twice: tenants without ownership transfer events get no note.
    for _ in range(2):
        asyncio.run(inspection_transfer.run_once(settings))

    async def notes(tenant: uuid.UUID) -> int:
        from mhvp.hoa.inspection import InspectionEvent

        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant) as session:
                return len((await session.scalars(select(InspectionEvent.id))).all())
        finally:
            await engine.dispose()

    assert asyncio.run(notes(tenants["a"])) == 0
    assert asyncio.run(notes(tenants["b"])) == 0


def test_inspection_scan_isolates_failures(
    database: Database,
    redis_url: str,
    tenants: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mhvp.core.db import tenancy
    from mhvp.hoa import inspection_transfer

    settings = _settings(database, redis_url)
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(
        inspection_transfer, "note_ownership_transfers", _recorder(calls, {"events": 0})
    )
    asyncio.run(inspection_transfer.run_once(settings))
    assert _mine(calls, tenants) == ["a", "b"]
    calls.clear()
    # run_once imports tenant_transaction from mhvp.core.db.tenancy at call time.
    _failing_tenant(monkeypatch, tenancy, tenants["a"])
    _run(inspection_transfer.run_once(settings))
    assert _mine(calls, tenants) == ["b"], "a failure in tenant A stopped tenant B"


def test_inspection_scan_respects_disabled_job(
    database: Database,
    redis_url: str,
    tenants: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mhvp.hoa import inspection_transfer

    settings = _settings(database, redis_url)
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(
        inspection_transfer, "note_ownership_transfers", _recorder(calls, {"events": 0})
    )
    asyncio.run(_set_job(settings, tenants["a"], "hoa-inspection-ownership-scan", False))
    try:
        asyncio.run(inspection_transfer.run_once(settings))
    finally:
        asyncio.run(_set_job(settings, tenants["a"], "hoa-inspection-ownership-scan", True))
    assert _mine(calls, tenants) == ["b"]
