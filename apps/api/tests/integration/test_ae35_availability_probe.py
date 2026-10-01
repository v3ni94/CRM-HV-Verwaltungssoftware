"""AE35 (GB16-02, AD10-02): own availability measurement with minute points, monthly evaluation,
switch for maintenance windows and retention purge. The HTTP client is a mock transport, no
test touches the network.

Scenario for month A (T = days * 1.440 minute checks, same arithmetic for every month length):
* api: 340 failed checks, 240 of them inside an announced window (4 hours), 100 outside.
  gross = (T - 340) / T, net = (T - 340) / (T - 240); with T = 44.640 (31 days) that is
  99,23835125 and 99,77477477 percent (pinned by hand in tests/unit/test_ae35_availability.py).
  Gross misses the target 99,5, net meets it for every month length (28 to 31 days).
* crm and portal: no failure, gross = net = 100.
Month B: api and crm complete, portal only the first 10.000 minutes (coverage below 95 percent,
so no rating). Month C: one probe, 1.000 minutes, used for the catch up of the purge run."""

import asyncio
import calendar
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction
from mhvp.main import create_app
from mhvp.platform import availability_probe as ap
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-ae35"
AV = "/api/v1/platform/availability"
LIVE = AV + "/live"
SWITCH = AV + "/settings"
API_URL = "https://api.ae35.example.test/api/v1/health/ready?token=hidden"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        availability_api_url=API_URL,
        availability_crm_url="https://crm.ae35.example.test/api/health",
        availability_portal_url="http://web-portal:3001/api/health",
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae35a-{RUN}", name=f"AE35 A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, is_admin in (("ae35admin", False), ("ae35padmin", True)):
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            if not is_admin:
                await services.add_member(
                    factory,
                    tenant_id=a,
                    user_id=uid,
                    role_codes=["tenant_admin"],
                    actor_user_id=None,
                )
        return world
    finally:
        await engine.dispose()


def _first_of_month(months_back: int) -> date:
    today = datetime.now(UTC).date()
    index = today.year * 12 + (today.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def _minutes(first: date) -> int:
    return calendar.monthrange(first.year, first.month)[1] * 1440


def _at(first: date, day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime(first.year, first.month, 1, tzinfo=UTC) + timedelta(
        days=day_offset, hours=hour, minutes=minute
    )


def _seed(
    conn: Any,
    probe: str,
    start: datetime,
    count: int,
    down: list[tuple[datetime, datetime]] | None = None,
) -> None:
    """``count`` minute points from ``start`` on; points inside a ``down`` range have failed."""
    ranges = down or []
    condition = " OR ".join(
        f"(gs >= CAST(:s{i} AS timestamptz) AND gs < CAST(:e{i} AS timestamptz))"
        for i in range(len(ranges))
    )
    params: dict[str, Any] = {
        "probe": probe,
        "start": start,
        "stop": start + timedelta(minutes=count - 1),
    }
    for i, (s, e) in enumerate(ranges):
        params[f"s{i}"] = s
        params[f"e{i}"] = e
    conn.execute(
        text(
            "INSERT INTO platform_availability_probe_point (id, probe, slot, ok)"
            f" SELECT gen_random_uuid(), :probe, gs, {'NOT (' + condition + ')' if ranges else 'true'}"
            " FROM generate_series(CAST(:start AS timestamptz), CAST(:stop AS timestamptz),"
            " interval '1 minute') AS gs"
        ),
        params,
    )


def _run_db(settings: Settings, work: Callable[[Any], Any]) -> Any:
    async def go() -> Any:
        engine = create_async_engine(settings.database_url.get_secret_value(), poolclass=NullPool)
        try:
            async with platform_transaction(create_session_factory(engine)) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


@pytest.fixture(scope="module")
def settings(database: Database, redis_url: str) -> Settings:
    return _settings(database, redis_url)


@pytest.fixture(scope="module")
def world(settings: Settings) -> World:
    return asyncio.run(_world(settings))


@pytest.fixture(scope="module")
def scenario(database: Database, settings: Settings, world: World) -> dict[str, date]:
    a, b, c = _first_of_month(5), _first_of_month(6), _first_of_month(8)
    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM platform_availability_probe_point"))
        conn.execute(text("DELETE FROM platform_availability_month"))
        conn.execute(
            text("DELETE FROM platform_maintenance_window WHERE starts_at < :cut"),
            {"cut": _first_of_month(0)},
        )
        window = (_at(a, 9, 2), _at(a, 9, 6))
        conn.execute(
            text(
                "INSERT INTO platform_maintenance_window (id, starts_at, ends_at, text_de, text_en)"
                " VALUES (gen_random_uuid(), :s, :e, 'Wartung AE35', 'Maintenance AE35')"
            ),
            {"s": window[0], "e": window[1]},
        )
        api_down = [window, (_at(a, 19, 12), _at(a, 19, 13, 40))]
        t_a = _minutes(a)
        _seed(conn, "api", _at(a, 0, 0), t_a, api_down)
        _seed(conn, "crm", _at(a, 0, 0), t_a)
        _seed(conn, "portal", _at(a, 0, 0), t_a)
        t_b = _minutes(b)
        _seed(conn, "api", _at(b, 0, 0), t_b)
        _seed(conn, "crm", _at(b, 0, 0), t_b)
        _seed(conn, "portal", _at(b, 0, 0), 10_000)
    engine.dispose()
    result = asyncio.run(ap.evaluate_months_once(settings))
    assert result == {"provisional": 0, "final": 6}
    return {"a": a, "b": b, "c": c}


@pytest.fixture
def client(database: Database, settings: Settings) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _floor8(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_FLOOR)


def _month(client: TestClient, headers: dict[str, str], first: date) -> dict[str, Any]:
    out = _ok(client.get(AV + "?months=36", headers=headers))
    key = f"{first.year:04d}-{first.month:02d}"
    return next(m for m in out["months"] if m["month"] == key)


def test_monthly_evaluation_gross_net_and_rating(
    client: TestClient, world: World, scenario: dict[str, date]
) -> None:
    p = bearer(login(client, world, "ae35padmin"))
    a, b = scenario["a"], scenario["b"]
    t = Decimal(_minutes(a))
    gross = _floor8((t - 340) * 100 / t)
    net = _floor8((t - 340) * 100 / (t - 240))

    month = _month(client, p, a)
    api = next(f for f in month["self_probes"] if f["probe"] == "api")
    assert (api["checks_total"], api["checks_ok"]) == (int(t), int(t) - 340)
    assert (api["checks_maintenance"], api["failed_in_maintenance"]) == (240, 240)
    assert api["expected_checks"] == int(t)
    assert Decimal(api["uptime_gross"]) == gross
    assert Decimal(api["uptime_net"]) == net
    assert Decimal(api["coverage_percent"]) == Decimal("100")
    assert api["final"] is True
    for name in ("crm", "portal"):
        other = next(f for f in month["self_probes"] if f["probe"] == name)
        assert Decimal(other["uptime_gross"]) == Decimal("100")
        assert Decimal(other["uptime_net"]) == Decimal("100")
        assert other["failed_in_maintenance"] == 0
        assert other["target_met"] is True

    # Default switch (off): the net figure is rated, the gross figure is shown next to it.
    assert _ok(client.get(AV, headers=p))["maintenance_counts_as_downtime"] is False
    assert Decimal(month["self_gross_percent"]) == gross
    assert Decimal(month["self_net_percent"]) == net
    assert Decimal(month["self_counted_percent"]) == net
    assert month["self_target_met"] is True
    assert api["target_met"] is True
    assert month["self_failed_in_maintenance_minutes"] == 240
    assert month["self_final"] is True
    assert gross < Decimal("99.5") <= net  # the scenario is meaningful for every month length

    # Month B: the portal has too little coverage, so no rating (10.000 of the month's minutes).
    month_b = _month(client, p, b)
    portal = next(f for f in month_b["self_probes"] if f["probe"] == "portal")
    assert Decimal(portal["coverage_percent"]) == _floor3(Decimal(10_000) * 100 / _minutes(b))
    assert portal["target_met"] is None
    assert month_b["self_target_met"] is None
    assert Decimal(month_b["self_coverage_percent"]) == Decimal(portal["coverage_percent"])
    assert all(f["target_met"] is True for f in month_b["self_probes"] if f["probe"] != "portal")


def _floor3(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_FLOOR)


def test_switch_maintenance_counts_as_downtime(
    client: TestClient, world: World, scenario: dict[str, date]
) -> None:
    p = bearer(login(client, world, "ae35padmin"))
    t_admin = bearer(login(client, world, "ae35admin"))
    a = scenario["a"]
    t = Decimal(_minutes(a))
    gross = _floor8((t - 340) * 100 / t)
    try:
        switched = _ok(client.put(SWITCH, json={"maintenance_counts_as_downtime": True}, headers=p))
        assert switched["maintenance_counts_as_downtime"] is True
        month = _month(client, p, a)
        assert Decimal(month["self_counted_percent"]) == gross
        assert month["self_target_met"] is False
        api = next(f for f in month["self_probes"] if f["probe"] == "api")
        assert api["target_met"] is False
        assert _ok(client.get(AV, headers=p))["maintenance_counts_as_downtime"] is True
        assert _ok(client.get(LIVE, headers=p))["maintenance_counts_as_downtime"] is True
        # Same value again: no new audit event.
        _ok(client.put(SWITCH, json={"maintenance_counts_as_downtime": True}, headers=p))
    finally:
        back = _ok(client.put(SWITCH, json={"maintenance_counts_as_downtime": False}, headers=p))
    assert back["maintenance_counts_as_downtime"] is False
    assert _month(client, p, a)["self_target_met"] is True
    events = _ok(
        client.get(
            "/api/v1/platform/audit-events?limit=200&action=availability_setting_changed", headers=p
        )
    )["items"]
    mine = [e for e in events if e["actor_user_id"] == str(world.users["ae35padmin"])]
    assert [e["payload"] for e in mine[:2]] == [
        {"before": True, "after": False},
        {"before": False, "after": True},
    ]
    assert all(e["target_id"] == "maintenance_counts_as_downtime" for e in mine)

    # Authorization and validation.
    on = {"maintenance_counts_as_downtime": True}
    assert client.put(SWITCH, json=on, headers=t_admin).status_code == 403
    assert client.get(LIVE, headers=t_admin).status_code == 403
    assert client.put(SWITCH, json=on).status_code in (401, 403)
    assert client.get(LIVE).status_code in (401, 403)
    assert client.put(SWITCH, json={**on, "extra": 1}, headers=p).status_code == 422
    assert client.put(SWITCH, json={}, headers=p).status_code == 422
    assert (
        client.put(SWITCH, json={"maintenance_counts_as_downtime": "maybe"}, headers=p).status_code
        == 422
    )
    assert client.get(LIVE + "?x=1", headers=p).status_code == 422


def test_probe_run_is_idempotent_and_shows_live(
    client: TestClient, world: World, settings: Settings, scenario: dict[str, date]
) -> None:
    p = bearer(login(client, world, "ae35padmin"))
    moment = datetime.now(UTC)
    calls: list[str] = []
    healthy = {"api": True}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "api.ae35.example.test":
            return httpx.Response(200 if healthy["api"] else 503)
        if request.url.host == "crm.ae35.example.test":
            return httpx.Response(503)
        raise httpx.ConnectTimeout("no route", request=request)

    async def run() -> dict[str, bool]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as mock:
            return await ap.run_probes_once(settings, client=mock, now=moment)

    assert asyncio.run(run()) == {"api": True, "crm": False, "portal": False}
    # A repeated run in the same minute keeps the first result (idempotent), even if it differs.
    healthy["api"] = False
    assert asyncio.run(run()) == {"api": False, "crm": False, "portal": False}
    assert set(calls) == {"api.ae35.example.test", "crm.ae35.example.test", "web-portal"}

    live = _ok(client.get(LIVE, headers=p))
    by_probe = {x["probe"]: x for x in live["probes"]}
    assert [x["probe"] for x in live["probes"]] == ["api", "crm", "portal"]
    assert by_probe["api"]["configured"] is True
    assert by_probe["api"]["host"] == "api.ae35.example.test"  # no path, no query string
    assert by_probe["portal"]["host"] == "web-portal:3001"
    assert (by_probe["api"]["last_ok"], by_probe["api"]["last_status_code"]) == (True, 200)
    assert by_probe["api"]["last_error_class"] is None
    assert (by_probe["crm"]["last_ok"], by_probe["crm"]["last_status_code"]) == (False, 503)
    assert by_probe["crm"]["last_error_class"] == "http_status"
    assert (by_probe["portal"]["last_ok"], by_probe["portal"]["last_error_class"]) == (
        False,
        "timeout",
    )
    for name in ("api", "crm", "portal"):
        assert by_probe[name]["checks_24h"] == 1
    assert Decimal(by_probe["api"]["percent_24h"]) == Decimal("100")
    assert Decimal(by_probe["crm"]["percent_24h"]) == Decimal("0")
    assert {f["probe"] for f in live["recent_failures"][:2]} == {"crm", "portal"}
    assert live["retention_days"] == 120
    assert "token" not in str(live)
    assert "hidden" not in str(live)

    # The running month is evaluated provisionally and never rated on a single check.
    result = asyncio.run(ap.evaluate_months_once(settings))
    assert result["provisional"] == 3
    month = _month(client, p, moment.date().replace(day=1))
    assert month["self_final"] is False
    assert {f["probe"] for f in month["self_probes"]} == {"api", "crm", "portal"}
    assert all(f["final"] is False and f["checks_total"] == 1 for f in month["self_probes"])


def test_purge_keeps_unevaluated_months_and_recent_points(
    client: TestClient,
    world: World,
    settings: Settings,
    database: Database,
    scenario: dict[str, date],
) -> None:
    p = bearer(login(client, world, "ae35padmin"))
    a, b, c = scenario["a"], scenario["b"], scenario["c"]
    t_a, t_b = _minutes(a), _minutes(b)
    before_a = _month(client, p, a)

    def count(where: str = "true") -> int:
        engine = create_engine(database.migrator_url)
        try:
            with engine.connect() as conn:
                return int(
                    conn.execute(
                        text(
                            f"SELECT count(*) FROM platform_availability_probe_point WHERE {where}"
                        )
                    ).scalar_one()
                )
        finally:
            engine.dispose()

    recent = count("slot >= now() - interval '1 day'")
    assert count() == 3 * t_a + 2 * t_b + 10_000 + recent

    # Retention is respected: with 40 days retention the points before (end of month A minus
    # 20 days) go, that is all of the older month B and the first part of month A, nothing of
    # the younger points.
    end_a = _at(a, 0, 0) + timedelta(minutes=t_a)

    async def partial(session: Any) -> int:
        return await ap.purge_points(session, end_a + timedelta(days=20), 40)

    assert _run_db(settings, partial) == 3 * (t_a - 20 * 1440) + 2 * t_b + 10_000
    assert (
        count(f"slot >= '{_at(a, 0, 0).isoformat()}' AND slot < '{end_a.isoformat()}'")
        == 3 * 20 * 1440
    )

    # Month C is old but was never evaluated: a direct purge must not touch it, the rest of
    # the frozen month A goes.
    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        _seed(conn, "api", _at(c, 0, 0), 1_000)
    engine.dispose()

    async def direct(session: Any) -> int:
        return await ap.purge_points(
            session, datetime.now(UTC), settings.availability_retention_days
        )

    assert _run_db(settings, direct) == 3 * 20 * 1440
    assert count() == 1_000 + recent

    # The Löschlauf evaluates the ended month first and then deletes its points; the points of
    # the current minute stay, the frozen month rows stay untouched.
    assert asyncio.run(ap.purge_points_once(settings)) == {"deleted": 1_000}
    assert count() == recent
    assert asyncio.run(ap.purge_points_once(settings)) == {"deleted": 0}
    after_a = _month(client, p, a)
    assert after_a["self_probes"] == before_a["self_probes"]
    month_c = _month(client, p, c)
    assert [f["probe"] for f in month_c["self_probes"]] == ["api"]
    assert month_c["self_probes"][0]["final"] is True
    assert month_c["self_probes"][0]["checks_total"] == 1_000
    assert month_c["self_target_met"] is None  # one measuring point only: no month rating
