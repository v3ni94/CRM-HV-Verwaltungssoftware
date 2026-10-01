"""AD10 (GB16-01, GB16-02): maintenance windows with banner feed and monthly availability.

Expected values by hand (February 2025 has 28 days = 2.419.200 s, one window of 2 hours = 7.200 s):
* api 99,700 percent: downtime 2.419.200 * 0,003 = 7.257,6 s, minus 7.200 s planned = 57,6 s,
  adjusted 100 - 57,6 / 2.419.200 * 100 = 99,99761905, shown as 99,998.
* crm 99,400 percent: downtime 14.515,2 s, unplanned 7.315,2 s, adjusted 99,69761905 = 99,698.
* portal 99,900 percent. The weakest point decides: gross 99,4 (target missed), adjusted
  99,698 (target 99,5 met)."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import BUCKET, _settings

pytestmark = pytest.mark.integration
W = "/api/v1/platform/maintenance-windows"
CURRENT = "/api/v1/platform/maintenance/current"
AV = "/api/v1/platform/availability"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ad10a-{RUN}", name=f"AD10 A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, is_admin in (("ad10admin", False), ("ad10padmin", True)):
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


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _body(start: datetime, end: datetime, tag: str, **extra: Any) -> dict[str, Any]:
    return {
        "starts_at": _iso(start),
        "ends_at": _iso(end),
        "text_de": f"Wartung {tag} {RUN}",
        "text_en": f"Maintenance {tag} {RUN}",
        **extra,
    }


def test_maintenance_banner_feed_and_audit(client: TestClient, world: World) -> None:
    p = bearer(login(client, world, "ad10padmin"))
    t = bearer(login(client, world, "ad10admin"))
    now = datetime.now(UTC)
    soon = _ok(
        client.post(
            W, json=_body(now + timedelta(hours=10), now + timedelta(hours=12), "soon"), headers=p
        ),
        201,
    )
    far = _ok(
        client.post(
            W, json=_body(now + timedelta(hours=100), now + timedelta(hours=102), "far"), headers=p
        ),
        201,
    )
    far_notice = _ok(
        client.post(
            W,
            json=_body(
                now + timedelta(hours=100),
                now + timedelta(hours=102),
                "farnotice",
                notice_hours=200,
            ),
            headers=p,
        ),
        201,
    )
    gone = _ok(
        client.post(
            W, json=_body(now + timedelta(hours=5), now + timedelta(hours=6), "gone"), headers=p
        ),
        201,
    )
    assert (soon["phase"], far["phase"], far_notice["phase"]) == (
        "announced",
        "scheduled",
        "announced",
    )

    # Public feed without login: announced inside the lead time (48 h), not the far window,
    # not the cancelled one.
    _ok(client.patch(f"{W}/{gone['id']}", json={"cancel": True}, headers=p))
    feed = _ok(client.get(CURRENT))
    ids = {i["id"] for i in feed["items"]}
    assert soon["id"] in ids
    assert far_notice["id"] in ids
    assert far["id"] not in ids
    assert gone["id"] not in ids
    item = next(i for i in feed["items"] if i["id"] == soon["id"])
    assert item["text_de"] == f"Wartung soon {RUN}"
    assert item["text_en"] == f"Maintenance soon {RUN}"
    assert item["phase"] == "announced"

    # An active window switches the status.
    active = _ok(
        client.post(
            W, json=_body(now - timedelta(hours=1), now + timedelta(hours=1), "active"), headers=p
        ),
        201,
    )
    assert active["phase"] == "active"
    feed = _ok(client.get(CURRENT))
    assert feed["status"] == "maintenance"
    assert {i["id"]: i["phase"] for i in feed["items"]}[active["id"]] == "active"
    _ok(
        client.patch(
            f"{W}/{active['id']}", json={"ends_at": _iso(now + timedelta(hours=3))}, headers=p
        )
    )
    assert (
        client.patch(f"{W}/{gone['id']}", json={"text_de": "neu abc"}, headers=p).status_code == 422
    )

    # Authorization, validation, unknown query parameters.
    assert client.get(W, headers=t).status_code == 403
    assert (
        client.post(W, json=_body(now, now + timedelta(hours=1), "x"), headers=t).status_code == 403
    )
    assert client.get(W).status_code in (401, 403)
    bad_period = _body(now + timedelta(hours=2), now + timedelta(hours=1), "bad")
    assert client.post(W, json=bad_period, headers=p).status_code == 422
    naive = {**_body(now, now + timedelta(hours=1), "naive"), "starts_at": "2030-01-01T10:00:00"}
    assert client.post(W, json=naive, headers=p).status_code == 422
    assert client.post(W, json={**bad_period, "extra": 1}, headers=p).status_code == 422
    assert client.get(CURRENT + "?x=1").status_code in (401, 422)
    assert (
        client.patch(
            f"{W}/00000000-0000-0000-0000-000000000000", json={"cancel": True}, headers=p
        ).status_code
        == 404
    )

    # Platform audit holds creation, change and cancellation.
    events = _ok(client.get("/api/v1/platform/audit-events?limit=200", headers=p))["items"]
    mine = [e for e in events if e["target_id"] in (soon["id"], gone["id"], active["id"])]
    assert sorted(e["action"] for e in mine if e["target_id"] == gone["id"]) == [
        "maintenance_window_cancelled",
        "maintenance_window_created",
    ]
    assert "maintenance_window_updated" in {
        e["action"] for e in mine if e["target_id"] == active["id"]
    }
    assert all(e["actor_user_id"] == str(world.users["ad10padmin"]) for e in mine)
    for window in (soon, far, far_notice, active):
        _ok(client.patch(f"{W}/{window['id']}", json={"cancel": True}, headers=p))


def test_monthly_availability_against_target(
    client: TestClient, world: World, migrator_engine: Any
) -> None:
    # The database persists between runs: start from an empty February 2025 (windows and figures).
    with migrator_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM platform_availability_measurement WHERE month = '2025-02-01'")
        )
        conn.execute(text("DELETE FROM platform_maintenance_window WHERE starts_at < '2025-03-01'"))
    p = bearer(login(client, world, "ad10padmin"))
    t = bearer(login(client, world, "ad10admin"))
    window = _ok(
        client.post(
            W,
            json={
                "starts_at": "2025-02-10T02:00:00+00:00",
                "ends_at": "2025-02-10T04:00:00+00:00",
                "text_de": "Wartung Februar",
                "text_en": "Maintenance February",
            },
            headers=p,
        ),
        201,
    )
    try:
        for probe, pct in (("api", "99.700"), ("crm", "99.400")):
            _ok(
                client.put(
                    AV,
                    json={
                        "month": "2025-02",
                        "probe": probe,
                        "uptime_percent": pct,
                        "source_note": "Uptime Kuma, 30 Tage",
                    },
                    headers=p,
                )
            )
        # incomplete month: no verdict
        part = next(
            m
            for m in _ok(client.get(AV + "?months=36", headers=p))["months"]
            if m["month"] == "2025-02"
        )
        assert part["target_met"] is None
        assert part["target_met_adjusted"] is None
        figure = _ok(
            client.put(
                AV,
                json={
                    "month": "2025-02",
                    "probe": "portal",
                    "uptime_percent": "99.900",
                    "source_note": "Uptime Kuma, 30 Tage",
                },
                headers=p,
            )
        )
        assert figure["target_met"] is True
        out = _ok(client.get(AV + "?months=36", headers=p))
        assert Decimal(out["target_percent"]) == Decimal("99.5")
        feb = next(m for m in out["months"] if m["month"] == "2025-02")
        assert feb["month_seconds"] == 2_419_200
        assert feb["planned_downtime_seconds"] == 7_200
        by_probe = {f["probe"]: f for f in feb["probes"]}
        assert Decimal(by_probe["api"]["adjusted_percent"]) == Decimal("99.998")
        assert Decimal(by_probe["crm"]["adjusted_percent"]) == Decimal("99.698")
        assert by_probe["crm"]["target_met"] is False
        assert by_probe["crm"]["target_met_adjusted"] is True
        assert Decimal(feb["actual_percent"]) == Decimal("99.4")
        assert Decimal(feb["adjusted_percent"]) == Decimal("99.698")
        assert feb["target_met"] is False
        assert feb["target_met_adjusted"] is True

        # Correction replaces the figure and is audited with the old value.
        _ok(
            client.put(
                AV,
                json={
                    "month": "2025-02",
                    "probe": "crm",
                    "uptime_percent": "99.600",
                    "source_note": "korrigiert",
                },
                headers=p,
            )
        )
        feb = next(
            m
            for m in _ok(client.get(AV + "?months=36", headers=p))["months"]
            if m["month"] == "2025-02"
        )
        assert feb["target_met"] is True
        events = _ok(
            client.get(
                "/api/v1/platform/audit-events?limit=200&action=availability_measurement_recorded",
                headers=p,
            )
        )
        crm = [e for e in events["items"] if e["target_id"] == "2025-02:crm"]
        assert any(e["payload"]["before"] == "99.40000000" for e in crm)
    finally:
        _ok(client.patch(f"{W}/{window['id']}", json={"cancel": True}, headers=p))

    # Authorization and validation.
    ok = {"month": "2025-02", "probe": "api", "uptime_percent": "99.9", "source_note": "Kuma"}
    assert client.put(AV, json=ok, headers=t).status_code == 403
    assert client.get(AV, headers=t).status_code == 403
    assert client.put(AV, json=ok).status_code in (401, 403)
    for bad in (
        {**ok, "uptime_percent": "100.1"},
        {**ok, "uptime_percent": "-1"},
        {**ok, "month": "2025-13"},
        {**ok, "month": "2099-01"},
        {**ok, "probe": "db"},
        {**ok, "source_note": ""},
    ):
        assert client.put(AV, json=bad, headers=p).status_code == 422, bad
    assert client.get(AV + "?foo=1", headers=p).status_code == 422
