"""AE36 (AA15-01, AC09-01, ADR 0021): demo tenant flag with exclusions and scale monitoring.

Own test world (prefix ``ae36``, RUN suffix): tenant a (real), tenant d (demo), tenant c (flag
changes), users: tenant admin of a, tenant admin of d, reader of a, platform administrator who is
also member of a (receives the alarm in the bell).

Expected values by hand:

* demo tenant: every export (tenant export, journal, DATEV, audit export, export request),
  licence, usage count and billing preview answer 409 ``MHVP-DEMO-0001``; the readiness view
  shows zeros instead of a usage count; the nightly usage job leaves no usage row for it;
* ``tenants_active`` of the metrics = active tenants without the demo flag;
* alarm: threshold of productive tenants 1 is reached by a, so the first snapshot of the week
  announces ``tenants:productive`` once (one bell entry, one audit event), the second does not;
* P95: three weekly snapshots with 25 samples of 500 ms for ``journal_list`` (threshold 300 ms,
  three weeks) reach the trigger exactly with the third week, and it is announced once.
"""

import asyncio
import json
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import Engine, text

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.platform.licensing import usage_all_once
from mhvp.workspace import backup_verify, scale
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
P = "/api/v1/platform"
SCALE = f"{P}/ops/scale"
DEMO_CODE = "MHVP-DEMO-0001"


class OpenG1:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae36a-{RUN}", name=f"AE36 A {RUN}")
        d, _ = await services.provision_tenant(
            factory, slug=f"ae36d-{RUN}", name=f"AE36 Demo {RUN}", is_demo=True
        )
        c, _ = await services.provision_tenant(factory, slug=f"ae36c-{RUN}", name=f"AE36 C {RUN}")
        world = World(tenant_a=a, tenant_b=d, app_url=settings.database_url.get_secret_value())
        world.users["tenant_c"] = c
        specs = {
            "ae36admin": (False, [(a, "tenant_admin")]),
            "ae36demo": (False, [(d, "tenant_admin")]),
            "ae36reader": (False, [(a, "read_only")]),
            "ae36padmin": (True, [(a, "tenant_admin")]),
            # platform administrator who is member of the real and of the demo tenant
            "ae36pboth": (True, [(a, "tenant_admin"), (d, "tenant_admin")]),
        }
        for name, (is_admin, memberships) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            for tenant_id, role in memberships:
                await services.add_member(
                    factory,
                    tenant_id=tenant_id,
                    user_id=uid,
                    role_codes=[role],
                    actor_user_id=None,
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module", autouse=True)
def clean_scale_tables(database: Database, redis_url: str) -> Iterator[None]:
    """Scale tables and Redis keys of this module start and end empty; the settings row is
    reset to the ADR proposals."""

    def reset() -> None:
        from sqlalchemy import create_engine

        engine = create_engine(database.migrator_url)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM platform_scale_snapshot"))
            conn.execute(text("DELETE FROM platform_scale_setting"))
        engine.dispose()

        async def redis_clean() -> None:
            redis = Redis.from_url(redis_url)
            await redis.delete(
                backup_verify.RESULT_KEY, *[scale.LATENCY_PREFIX + k for k in scale.LATENCY_KEYS]
            )
            await redis.aclose()

        asyncio.run(redis_clean())

    reset()
    yield
    reset()


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _demo_refused(response: Any) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] == DEMO_CODE


def _count(engine: Engine, sql: str, **params: Any) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar() or 0)


# Flag and listing ------------------------------------------------------------------------------


def test_flag_is_listed_and_set_at_creation(client: TestClient, world: World) -> None:
    p = bearer(login(client, world, "ae36padmin"))
    rows = {t["id"]: t for t in _ok(client.get(f"{P}/tenants", headers=p))}
    assert rows[str(world.tenant_b)]["is_demo"] is True
    assert rows[str(world.tenant_a)]["is_demo"] is False
    created = _ok(
        client.post(
            f"{P}/tenants",
            json={"slug": f"ae36n-{RUN}", "name": "AE36 N", "is_demo": True},
            headers=p,
        ),
        201,
    )
    assert created["is_demo"] is True


def test_demo_flag_endpoint_rules_and_audit(
    client: TestClient, world: World, database: Database, redis_url: str, app_engine: Engine
) -> None:
    c = world.users["tenant_c"]
    url = f"{P}/tenants/{c}/demo"
    p = bearer(login(client, world, "ae36padmin"))
    t = bearer(login(client, world, "ae36admin"))
    assert client.put(url, json={"is_demo": True}, headers=t).status_code == 403
    assert client.put(url, json={"is_demo": "x"}, headers=p).status_code == 422
    assert client.put(url, json={"is_demo": True, "x": 1}, headers=p).status_code == 422
    assert (
        client.put(
            f"{P}/tenants/{uuid.uuid4()}/demo", json={"is_demo": True}, headers=p
        ).status_code
        == 404
    )
    # a tenant with an open gate works with real data: refused
    with TestClient(
        create_app(_settings(database, redis_url), release_gate_resolver=OpenG1())
    ) as open_:
        po = bearer(login(open_, world, "ae36padmin"))
        refused = open_.put(url, json={"is_demo": True}, headers=po)
        assert refused.status_code == 409
        assert refused.json()["code"] == "MHVP-DEMO-0002"
    assert _ok(client.put(url, json={"is_demo": True}, headers=p))["is_demo"] is True
    assert _ok(client.put(url, json={"is_demo": True}, headers=p))["is_demo"] is True  # idempotent
    assert _count(app_engine, "SELECT count(*) FROM tenant WHERE id = :i AND is_demo", i=c) == 1
    # a demo tenant is excluded right away
    _demo_refused(client.post(f"{P}/tenants/{c}/usage", json={"month": "2026-09-01"}, headers=p))
    assert _ok(client.put(url, json={"is_demo": False}, headers=p))["is_demo"] is False
    changed = _count(
        app_engine,
        "SELECT count(*) FROM platform_audit_event WHERE action = 'tenant_demo_flag_changed' "
        "AND target_id = :i",
        i=str(c),
    )
    assert changed == 2  # on and off; the repeated call wrote nothing


# Exclusion from exports and DATEV -----------------------------------------------------------------


def test_demo_tenant_takes_no_part_in_exports(client: TestClient, world: World) -> None:
    demo = bearer(login(client, world, "ae36demo"))
    real = bearer(login(client, world, "ae36admin"))
    p = bearer(login(client, world, "ae36padmin"))
    ledger = uuid.uuid4()
    period = {"start": "2026-01-01", "end": "2026-12-31"}
    a = "/api/v1/accounting"
    _demo_refused(client.post("/api/v1/tenant/export-jobs", headers=demo))
    _demo_refused(client.post(f"{a}/ledgers/{ledger}/exports/journal", params=period, headers=demo))
    _demo_refused(client.post(f"{a}/ledgers/{ledger}/exports/datev", params=period, headers=demo))
    _demo_refused(
        client.post(
            f"{a}/audit-exports",
            json={"ledger_id": str(ledger), "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=demo,
        )
    )
    _demo_refused(
        client.post(
            f"{P}/tenants/{world.tenant_b}/export-requests", json={"purpose": "access"}, headers=p
        )
    )
    # the same calls in a real tenant pass the guard (unknown ledger: 404, not 409)
    assert (
        client.post(
            f"{a}/ledgers/{ledger}/exports/journal", params=period, headers=real
        ).status_code
        == 404
    )
    assert (
        client.post(f"{a}/ledgers/{ledger}/exports/datev", params=period, headers=real).status_code
        == 404
    )
    audit = client.post(
        f"{a}/audit-exports",
        json={"ledger_id": str(ledger), "period_from": "2026-01-01", "period_to": "2026-12-31"},
        headers=real,
    )
    assert audit.status_code == 404
    exported = client.post(
        f"{P}/tenants/{world.tenant_a}/export-requests", json={"purpose": "access"}, headers=p
    )
    assert exported.status_code in (200, 201), exported.text


# Exclusion from billing ---------------------------------------------------------------------------


def test_demo_tenant_takes_no_part_in_billing(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    p = bearer(login(client, world, "ae36padmin"))
    body = {
        "module": "core",
        "unit_quota": 50,
        "valid_from": "2026-01-01",
        "price_per_unit": "1.00",
    }
    _demo_refused(
        client.post(f"{P}/licenses", json={**body, "tenant_id": str(world.tenant_b)}, headers=p)
    )
    _ok(
        client.post(f"{P}/licenses", json={**body, "tenant_id": str(world.tenant_a)}, headers=p),
        201,
    )
    demo_tenant = world.tenant_b
    _demo_refused(
        client.post(f"{P}/tenants/{demo_tenant}/usage", json={"month": "2026-09-01"}, headers=p)
    )
    _demo_refused(
        client.get(
            f"{P}/tenants/{demo_tenant}/billing-preview", params={"month": "2026-09-01"}, headers=p
        )
    )
    ready = _ok(client.get(f"{P}/tenants/{demo_tenant}/readiness", headers=p))
    assert ready["demo"] is True
    assert ready["usage"]["units"] == 0
    assert ready["usage"]["users"] == 0
    real_ready = _ok(client.get(f"{P}/tenants/{world.tenant_a}/readiness", headers=p))
    assert real_ready["demo"] is False
    # the usage job counts the real tenant and leaves no row for the demo tenant
    counted = asyncio.run(usage_all_once(_settings(database, redis_url)))
    assert counted["counted"] >= 1
    demo_history = _ok(client.get(f"{P}/tenants/{demo_tenant}/usage/history", headers=p))
    assert demo_history == {"daily": [], "monthly": []}
    real_history = _ok(client.get(f"{P}/tenants/{world.tenant_a}/usage/history", headers=p))
    assert len(real_history["monthly"]) >= 1


# Statistics -----------------------------------------------------------------------------------------


def test_metrics_leave_demo_tenants_out_and_show_scale_gauges(
    client: TestClient, world: World, app_engine: Engine
) -> None:
    p = bearer(login(client, world, "ae36padmin"))
    body = _ok(client.get(f"{P}/ops/metrics", headers=p))
    metrics = body["metrics"]
    productive = _count(
        app_engine, "SELECT count(*) FROM tenant WHERE status = 'active' AND NOT is_demo"
    )
    demo = _count(app_engine, "SELECT count(*) FROM tenant WHERE is_demo")
    assert metrics["tenants_active"] == productive
    assert metrics["tenants_productive"] == productive
    assert metrics["tenants_demo"] == demo >= 1
    for name in ("journal_entry", "journal_line", "bank_transaction"):
        assert metrics[f"{name}_rows"] >= 0
        assert metrics[f"{name}_bytes"] > 0
    for key in scale.LATENCY_KEYS:
        assert f"{key}_p95_ms" in metrics
    assert "scale_trigger_partition_review" in metrics
    prometheus = client.get(f"{P}/ops/metrics", params={"format": "prometheus"}, headers=p)
    assert "mhvp_journal_line_rows " in prometheus.text
    assert "mhvp_tenants_demo " in prometheus.text


def test_cross_tenant_working_view_leaves_demo_tenants_out(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ae36pboth"))
    view = _ok(client.get(f"{P}/overview", headers=h))
    ids = {row["tenant_id"] for row in view["tenants"]}
    assert str(world.tenant_a) in ids
    assert str(world.tenant_b) not in ids  # tenant d is the demo tenant


# Scale view, settings, latency ------------------------------------------------------------------------


def test_scale_view_requires_a_platform_administrator(client: TestClient, world: World) -> None:
    t = bearer(login(client, world, "ae36admin"))
    r = bearer(login(client, world, "ae36reader"))
    p = bearer(login(client, world, "ae36padmin"))
    assert client.get(SCALE, headers=t).status_code == 403
    assert client.get(SCALE, headers=r).status_code == 403
    assert (
        client.patch(f"{SCALE}/settings", json={"alarm_enabled": False}, headers=t).status_code
        == 403
    )
    assert client.post(f"{SCALE}/snapshot", headers=t).status_code == 403
    assert client.get(SCALE, params={"unknown": 1}, headers=p).status_code == 422
    view = _ok(client.get(SCALE, headers=p))
    assert [row["table"] for row in view["tables"]] == [
        "journal_entry",
        "journal_line",
        "bank_transaction",
    ]
    settings = view["settings"]
    assert settings["rows_threshold"] == 20_000_000
    assert settings["size_gb_threshold"] == 50
    assert settings["p95_ms_threshold"] == 300
    assert settings["p95_deep_ms_threshold"] == 1000
    assert settings["p95_weeks"] == 3
    assert settings["restore_seconds_threshold"] == 14_400
    assert settings["tenants_review_threshold"] == 20
    assert settings["alarm_enabled"] is True
    assert {row["key"] for row in view["latency"]} == set(scale.LATENCY_KEYS)
    assert view["tenants"]["demo"] >= 1
    assert "ADR 0021" in view["note"]


def test_scale_settings_validation_version_and_audit(
    client: TestClient, world: World, app_engine: Engine
) -> None:
    p = bearer(login(client, world, "ae36padmin"))
    url = f"{SCALE}/settings"
    for bad in (
        {"p95_weeks": 0},
        {"p95_weeks": 53},
        {"rows_threshold": 0},
        {"unknown": 1},
        {"alarm_enabled": "x"},
    ):
        assert client.patch(url, json=bad, headers=p).status_code == 422, bad
    first = _ok(client.patch(url, json={"p95_ms_threshold": 250, "p95_weeks": 2}, headers=p))
    assert first["p95_ms_threshold"] == 250
    assert first["p95_weeks"] == 2
    assert first["version"] == 2
    same = _ok(client.patch(url, json={"p95_ms_threshold": 250}, headers=p))
    assert same["version"] == 2  # no change, no new version
    back = _ok(client.patch(url, json={"p95_ms_threshold": 300, "p95_weeks": 3}, headers=p))
    assert back["version"] == 3
    audit = _count(
        app_engine,
        "SELECT count(*) FROM platform_audit_event WHERE action = 'scale.settings_changed' "
        "AND actor_user_id = :u",
        u=world.users["ae36padmin"],
    )
    assert audit == 2


def test_list_requests_feed_the_p95(client: TestClient, world: World) -> None:
    a = bearer(login(client, world, "ae36admin"))
    p = bearer(login(client, world, "ae36padmin"))
    # Latency samples are process wide in Redis: other tests in the same run may have hit the
    # journal list already, so compare against the baseline instead of an absolute zero.
    before = {row["key"]: row for row in _ok(client.get(SCALE, headers=p))["latency"]}
    journal_before = before.get("journal_list", {}).get("samples", 0)
    for _ in range(scale.MIN_SAMPLES + 2):
        _ok(client.get("/api/v1/banking/transactions", params={"limit": 5}, headers=a))
    _ok(client.get("/api/v1/banking/transactions", params={"offset": 10000, "limit": 5}, headers=a))
    # a failed request (unknown account filter value) is not measured
    assert (
        client.get("/api/v1/banking/transactions", params={"limit": 0}, headers=a).status_code
        == 422
    )
    view = _ok(client.get(SCALE, headers=p))
    by_key = {row["key"]: row for row in view["latency"]}
    assert by_key["bank_list"]["samples"] >= scale.MIN_SAMPLES + 2
    assert by_key["bank_list"]["p95_ms"] is not None
    assert by_key["bank_list"]["p95_ms"] > 0
    assert by_key["bank_list_deep"]["samples"] >= 1
    assert by_key["bank_list_deep"]["p95_ms"] is None  # below the sample basis
    assert by_key["journal_list"]["samples"] == journal_before


# Snapshot and alarm -------------------------------------------------------------------------------------


def test_snapshot_alarm_once_and_replaced_within_the_week(
    client: TestClient, world: World, app_engine: Engine
) -> None:
    p = bearer(login(client, world, "ae36padmin"))
    _ok(client.patch(f"{SCALE}/settings", json={"tenants_review_threshold": 1}, headers=p))
    key_audit = (
        "SELECT count(*) FROM platform_audit_event WHERE action = 'scale.trigger_reached' "
        "AND target_id = 'tenants:productive' AND payload ->> 'iso_week' = :w"
    )
    week_now = scale.iso_week_of(datetime.now(UTC).date())
    audit_before = _count(app_engine, key_audit, w=week_now)  # earlier runs stay in the audit
    try:
        first = _ok(client.post(f"{SCALE}/snapshot", headers=p))
        week = first["iso_week"]
        assert week == scale.iso_week_of(datetime.now(UTC).date())
        assert "tenants:productive" in first["new_triggers"]
        assert first["notified"] >= 1
        bell = _ok(
            client.get("/api/v1/workspace/notifications", params={"unread": "true"}, headers=p)
        )
        entries = [n for n in bell if n["kind"] == scale.NOTIFICATION_KIND]
        assert len(entries) == 1
        assert entries[0]["href"] == "/plattform/betrieb"
        assert entries[0]["title"].startswith("Skalierung:")
        assert _count(app_engine, key_audit, w=week) == audit_before + 1
        # a second run in the same week replaces the snapshot and does not announce it again
        second = _ok(client.post(f"{SCALE}/snapshot", headers=p))
        assert second["new_triggers"] == []
        assert second["notified"] == 0
        assert "tenants:productive" in [t["key"] for t in second["triggers"]]
        assert _count(app_engine, key_audit, w=week) == audit_before + 1
        assert (
            _count(
                app_engine,
                "SELECT count(*) FROM platform_scale_snapshot WHERE iso_week = :w",
                w=week,
            )
            == 1
        )
        view = _ok(client.get(SCALE, headers=p))
        assert view["history"][0]["iso_week"] == week
        assert view["history"][0]["source"] == "manual"
        assert view["history"][0]["tenants_demo"] >= 1
        assert "tenants:productive" in view["history"][0]["triggers"]
    finally:
        _ok(client.patch(f"{SCALE}/settings", json={"tenants_review_threshold": 20}, headers=p))


def test_alarm_switch_and_restore_trigger(
    client: TestClient, world: World, redis_url: str, app_engine: Engine
) -> None:
    """Restore test of 20.000 s is above the RTO of 14.400 s: trigger ``restore:duration``. With
    the alarm switch off the snapshot still records it but nothing is announced."""
    p = bearer(login(client, world, "ae36padmin"))

    async def put_record(seconds: int | None) -> None:
        redis = Redis.from_url(redis_url)
        if seconds is None:
            await redis.delete(backup_verify.RESULT_KEY)
        else:
            record = {
                "status": "ok",
                "started_at": datetime.now(UTC).isoformat(),
                "duration_seconds": seconds,
                "checked_file": "backup.dump",
                "exit_code": 0,
                "error": None,
            }
            await redis.set(backup_verify.RESULT_KEY, json.dumps(record))
        await redis.aclose()

    asyncio.run(put_record(20_000))
    _ok(client.patch(f"{SCALE}/settings", json={"alarm_enabled": False}, headers=p))
    try:
        view = _ok(client.get(SCALE, headers=p))
        assert view["restore"] == {"seconds": 20_000, "threshold_seconds": 14_400}
        assert "restore:duration" in [t["key"] for t in view["triggers"]]
        before = _count(
            app_engine,
            "SELECT count(*) FROM platform_audit_event WHERE target_id = 'restore:duration'",
        )
        silent = _ok(client.post(f"{SCALE}/snapshot", headers=p))
        assert "restore:duration" in silent["new_triggers"]
        assert silent["notified"] == 0
        assert (
            _count(
                app_engine,
                "SELECT count(*) FROM platform_audit_event WHERE target_id = 'restore:duration'",
            )
            == before
        )
        metrics = _ok(client.get(f"{P}/ops/metrics", headers=p))
        assert "scale_trigger_partition_review" in metrics["alerts"]
    finally:
        _ok(client.patch(f"{SCALE}/settings", json={"alarm_enabled": True}, headers=p))
        asyncio.run(put_record(None))


def test_p95_trigger_after_three_weekly_measurements(
    database: Database, redis_url: str, world: World, app_engine: Engine
) -> None:
    """25 samples of 500 ms per week (threshold 300 ms, three weeks in a row)."""
    settings = _settings(database, redis_url)

    async def run() -> list[Any]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        redis = Redis.from_url(redis_url)
        results = []
        try:
            now = int(time.time())
            await redis.delete(scale.LATENCY_PREFIX + "journal_list")
            await redis.lpush(
                scale.LATENCY_PREFIX + "journal_list", *[f"{now}:500.0" for _ in range(25)]
            )
            for day in (date(2031, 3, 3), date(2031, 3, 10), date(2031, 3, 17), date(2031, 3, 24)):
                results.append(await scale.snapshot_once(factory, redis, today=day))
            return results
        finally:
            await redis.delete(scale.LATENCY_PREFIX + "journal_list")
            await redis.aclose()
            await engine.dispose()

    announced_sql = (
        "SELECT count(*) FROM platform_audit_event WHERE action = 'scale.trigger_reached' "
        "AND target_id = 'p95:journal_list'"
    )
    announced_before = _count(app_engine, announced_sql)  # earlier runs stay in the audit
    first, second, third, fourth = asyncio.run(run())
    assert [r.iso_week for r in (first, second, third, fourth)] == [
        "2031-W10",
        "2031-W11",
        "2031-W12",
        "2031-W13",
    ]
    found = [{t.key for t in r.triggers} for r in (first, second, third, fourth)]
    assert "p95:journal_list" not in found[0]  # one measurement
    assert "p95:journal_list" not in found[1]  # two in a row
    assert "p95:journal_list" in found[2]  # the third
    assert "p95:journal_list" in found[3]  # stays active
    assert "p95:journal_list" in {t.key for t in third.new_triggers}
    assert "p95:journal_list" not in {t.key for t in fourth.new_triggers}  # announced once
    assert _count(app_engine, announced_sql) == announced_before + 1
    stored = _count(
        app_engine, "SELECT count(*) FROM platform_scale_snapshot WHERE iso_week LIKE '2031-W%'"
    )
    assert stored == 4


def test_table_stats_count_exactly_below_the_estimate_limit(
    database: Database, redis_url: str, world: World
) -> None:
    from sqlalchemy import func, select

    from mhvp.accounting.models import JournalEntry, JournalLine
    from mhvp.banking.models import BankTransaction
    from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
    from mhvp.platform.models import Tenant

    settings = _settings(database, redis_url)

    async def run() -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with platform_transaction(factory) as session:
                ids = list(await session.scalars(select(Tenant.id)))
            expected = dict.fromkeys(("journal_entry", "journal_line", "bank_transaction"), 0)
            for tenant_id in ids:
                async with tenant_transaction(factory, tenant_id) as session:
                    for name, model in (
                        ("journal_entry", JournalEntry),
                        ("journal_line", JournalLine),
                        ("bank_transaction", BankTransaction),
                    ):
                        expected[name] += int(
                            await session.scalar(select(func.count()).select_from(model)) or 0
                        )
            return await scale.table_stats(factory, ids), expected
        finally:
            await engine.dispose()

    stats, expected = asyncio.run(run())
    for name, rows in expected.items():
        assert stats[name]["rows"] == rows
        assert stats[name]["exact"] is True
        assert stats[name]["bytes"] > 0
