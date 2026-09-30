"""P21: webhook catalogue validation and delivery headers (S12-02, S12-08), rule test mode
(S15-04), tenant job schedules (S15-03), handover defects to tickets (S13-01)."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.automation.job_schedule import in_window
from mhvp.automation.tasks import process_events_once
from mhvp.core.webhooks import WebhookSubscription, is_known_event_type, matches
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m30_handover import _ok, _unit

pytestmark = pytest.mark.integration
H = "/api/v1/handover/protocols"
A = "/api/v1/automation"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p21-{RUN}", name=f"P21 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p21b-{RUN}", name=f"P21 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("p21admin", a, "tenant_admin"),
            ("p21reader", a, "read_only"),
            ("p21other", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    import boto3
    from moto import mock_aws

    from tests.integration.test_m30_handover import BUCKET

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def test_event_type_matching_and_catalogue() -> None:
    assert is_known_event_type("*")
    assert is_known_event_type("journal_entry.posted")
    assert is_known_event_type("ticket.*")
    assert not is_known_event_type("nope.created")
    assert not is_known_event_type("nope.*")
    sub = WebhookSubscription(event_types=["ticket.*"])
    assert matches(sub, "ticket.created")
    assert not matches(sub, "contact.created")


def test_window_logic() -> None:
    now = datetime(2026, 9, 30, 4, 30, tzinfo=UTC)  # 06:30 Europe/Berlin
    assert in_window(None, now)
    assert in_window("06:00", now)
    assert not in_window("06:45", now)
    assert not in_window("05:00", now)


def test_webhook_validation_and_job_schedules(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p21admin"))
    other = bearer(login(client, world, "p21other"))
    reader = bearer(login(client, world, "p21reader"))
    bad = client.post(
        "/api/v1/tenant/webhooks",
        json={"url": "https://example.org/x", "event_types": ["nope.created"]},
        headers=h,
    )
    assert bad.status_code == 422

    jobs = _ok(client.get(f"{A}/job-schedules", headers=h))
    assert any(j["job_key"] == "accounting-dunning-run" and j["enabled"] for j in jobs)
    put = _ok(
        client.put(
            f"{A}/job-schedules/accounting-dunning-run",
            json={"enabled": False, "run_at": "07:15"},
            headers=h,
        )
    )
    assert put["enabled"] is False
    assert client.put(f"{A}/job-schedules/unknown", json={}, headers=h).status_code == 422
    assert (
        client.put(
            f"{A}/job-schedules/accounting-dunning-run", json={"run_at": "25:00"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{A}/job-schedules/accounting-dunning-run", json={"enabled": True}, headers=reader
        ).status_code
        == 403
    )
    mine = {j["job_key"]: j for j in _ok(client.get(f"{A}/job-schedules", headers=h))}
    assert mine["accounting-dunning-run"]["run_at"] == "07:15"
    theirs = {j["job_key"]: j for j in _ok(client.get(f"{A}/job-schedules", headers=other))}
    assert theirs["accounting-dunning-run"]["configured"] is False


def test_rule_test_mode_writes_dry_run_only(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "p21admin"))
    asyncio.run(process_events_once(settings))
    rule = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": f"Testmodus {RUN}",
                "active": True,
                "test_mode": True,
                "trigger_event_type": "ticket.created",
                "conditions": {"field": "entity.category", "op": "eq", "value": "Testmodus"},
                "actions": [{"type": "set_ticket_field", "field": "priority", "value": "high"}],
            },
            headers=h,
        ),
        201,
    )
    assert rule["test_mode"] is True
    ticket = _ok(
        client.post("/api/v1/tickets", json={"title": "Probe", "category": "Testmodus"}, headers=h),
        201,
    )
    asyncio.run(process_events_once(settings, now=datetime.now(UTC) + timedelta(seconds=30)))
    assert _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))["priority"] == "normal"
    runs = _ok(client.get(f"{A}/runs", params={"rule_id": rule["id"]}, headers=h))
    items = runs["items"] if isinstance(runs, dict) else runs
    assert [r["status"] for r in items] == ["dry_run"]


def test_defects_to_tickets(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p21admin"))
    other = bearer(login(client, world, "p21other"))
    reader = bearer(login(client, world, "p21reader"))
    _, unit_id = _unit(client, h)
    p = _ok(client.post(H, json={"kind": "rental", "unit_id": unit_id}, headers=h), 201)
    pid = p["id"]
    for title, status in (("Kratzer", "new"), ("Altschaden", "pre_existing")):
        _ok(
            client.post(
                f"{H}/{pid}/defects",
                json={"title": title, "priority": "high", "defect_status": status},
                headers=h,
            ),
            201,
        )
    assert client.post(f"{H}/{pid}/defects/tickets", json={}, headers=reader).status_code == 403
    assert client.post(f"{H}/{pid}/defects/tickets", json={}, headers=other).status_code == 404
    done = _ok(client.post(f"{H}/{pid}/defects/tickets", json={}, headers=h), 201)
    assert len(done["created"]) == 1
    again = _ok(client.post(f"{H}/{pid}/defects/tickets", json={}, headers=h), 201)
    assert again["created"] == []
    ticket = _ok(client.get(f"/api/v1/tickets/{done['created'][0]['ticket_id']}", headers=h))
    assert ticket["priority"] == "high"
    assert "Kratzer" in ticket["title"]
    assert _ok(client.get(f"{H}/{pid}", headers=h))["ticket_number"] == str(
        done["created"][0]["number"]
    )
