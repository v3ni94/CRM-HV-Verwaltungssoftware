"""M21: SLA-Regeln, Uhren, Bereitschaft und Notfallalarme (Übernahme aus dem Immoware Hub).

Smoke test: Ticket anlegen startet die Uhr, eine SLA-Regel steuert Reaktions- und Lösungsfrist,
Uhren lassen sich pausieren/fortsetzen, Bereitschaft und Kalender sind über die Router erreichbar.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"sla-{RUN}", name=f"SLA {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("m21admin", "tenant_admin"),
            ("m21read", "read_only"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_ticket_creation_starts_clock_and_rules_govern_it(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m21admin"))
    reader = bearer(login(client, world, "m21read"))

    rule = _ok(
        client.post(
            "/api/v1/sla/rules",
            json={
                "name": "Dringend",
                "priority": "urgent",
                "response_minutes": 240,
                "resolution_minutes": 2880,
                "clock_type": "business",
            },
            headers=h,
        ),
        201,
    )
    assert (
        client.post(
            "/api/v1/sla/rules",
            json={
                "name": "Verboten",
                "priority": "normal",
                "response_minutes": 60,
                "resolution_minutes": 120,
            },
            headers=reader,
        ).status_code
        == 403
    )

    step = _ok(
        client.post(
            f"/api/v1/sla/rules/{rule['id']}/steps",
            json={
                "step_no": 1,
                "after_minutes": 0,
                "notify_user_ids": [str(world.users["m21admin"])],
                "channel": "internal",
            },
            headers=h,
        ),
        201,
    )
    assert step["rule_id"] == rule["id"]

    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Rohrbruch Keller", "priority": "urgent"},
            headers=h,
        ),
        201,
    )

    clock = _ok(client.get(f"/api/v1/sla/tickets/{ticket['id']}/sla", headers=h))
    assert clock["ticket_id"] == ticket["id"]
    assert clock["rule_id"] == rule["id"]
    assert clock["state"] == "running"
    assert clock["color"] == "green"
    assert clock["due_response_at"] is not None
    assert clock["due_resolution_at"] is not None

    clocks = _ok(client.get("/api/v1/sla/clocks", headers=h))
    assert any(c["id"] == clock["id"] for c in clocks)

    paused = _ok(client.post(f"/api/v1/sla/clocks/{clock['id']}/pause", headers=h))
    assert paused["state"] == "paused"
    resumed = _ok(client.post(f"/api/v1/sla/clocks/{clock['id']}/resume", headers=h))
    assert resumed["state"] == "running"

    assert client.get("/api/v1/sla/rules", headers=reader).status_code == 200
    assert client.post(f"/api/v1/sla/clocks/{clock['id']}/pause", headers=reader).status_code == 403


def test_on_call_and_calendar(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m21admin"))
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    on_call = _ok(
        client.post(
            "/api/v1/sla/on-call",
            json={
                "user_id": str(world.users["m21admin"]),
                "starts_at": (now - timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(hours=8)).isoformat(),
                "note": "Wochenendbereitschaft",
            },
            headers=h,
        ),
        201,
    )
    current = _ok(client.get("/api/v1/sla/on-call/current", headers=h))
    assert current is not None
    assert current["id"] == on_call["id"]

    calendar = _ok(
        client.put(
            "/api/v1/sla/calendar",
            json={
                "weekdays": [0, 1, 2, 3, 4],
                "opens_at": "08:00",
                "closes_at": "16:30",
                "timezone": "Europe/Berlin",
                "holidays": ["2026-12-25"],
            },
            headers=h,
        )
    )
    assert calendar["holidays"] == ["2026-12-25"]
    fetched = _ok(client.get("/api/v1/sla/calendar", headers=h))
    assert fetched == calendar

    alerts = _ok(client.get("/api/v1/sla/alerts", headers=h))
    assert isinstance(alerts, list)


def test_presets_create_rules_once_and_keep_existing(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m21admin"))
    first = _ok(client.post("/api/v1/sla/rules/presets", headers=h), 201)
    assert {r["priority"] for r in first} == {"immediate", "urgent", "high", "normal", "low"}
    assert all(r["active"] for r in first)
    listed = _ok(client.get("/api/v1/sla/rules", headers=h))
    assert len(listed) >= 5
    second = _ok(client.post("/api/v1/sla/rules/presets", headers=h), 201)
    assert {r["id"] for r in second} == {r["id"] for r in first}
    calendar = _ok(client.get("/api/v1/sla/calendar", headers=h))
    assert calendar["closes_at"].startswith("17:00")


def test_sms_gateway_config_hides_secret_and_test_reports_errors(
    client: TestClient, world: World
) -> None:
    """M35: GET/PUT /sla/sms-gateway ohne Secret in der Antwort, Test ohne aktives Gateway
    liefert einen Fehlertext, Lesende dürfen nicht ändern."""
    h = bearer(login(client, world, "m21admin"))
    empty = _ok(client.get("/api/v1/sla/sms-gateway", headers=h))
    assert empty["enabled"] is False
    assert empty["auth_header_set"] is False

    bad = client.put(
        "/api/v1/sla/sms-gateway",
        json={"enabled": False, "body_template": '{"to": {to}}'},
        headers=h,
    )
    assert bad.status_code == 422, bad.text

    saved = _ok(
        client.put(
            "/api/v1/sla/sms-gateway",
            json={
                "enabled": False,
                "url": "https://gateway.example/api/sms",
                "auth_header_name": "X-Api-Key",
                "auth_header_value": "geheim-m35",
                "body_template": '{"to": "{to}", "text": "{text}", "from": "{sender}"}',
                "sender": "MHVP",
            },
            headers=h,
        )
    )
    assert saved["auth_header_set"] is True
    assert "geheim-m35" not in str(saved)
    kept = _ok(
        client.put(
            "/api/v1/sla/sms-gateway",
            json={**{k: v for k, v in saved.items() if k != "auth_header_set"}},
            headers=h,
        )
    )
    assert kept["auth_header_set"] is True

    result = _ok(
        client.post("/api/v1/sla/sms-gateway/test", json={"to": "+49 170 1234567"}, headers=h)
    )
    assert result["ok"] is False
    assert "deaktiviert" in result["error"]
    assert "geheim-m35" not in str(result)

    reader = bearer(login(client, world, "m21read"))
    denied = client.put("/api/v1/sla/sms-gateway", json={"enabled": False}, headers=reader)
    assert denied.status_code == 403
