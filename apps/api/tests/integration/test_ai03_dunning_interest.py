"""AI03 (GAH-110, GAH-113): day count switch of the default interest and the Basiszinssatz
hint plus check points. The default stays days/365; the switch is per tenant (RLS), needs
``accounting:approve`` and accepts only the two variants."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
URL = "/api/v1/accounting/dunning-interest"


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ai03-a-{RUN}", name=f"AI03 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ai03-b-{RUN}", name=f"AI03 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ai03admin", a, "tenant_admin"),
            ("ai03read", a, "read_only"),
            ("ai03other", b, "tenant_admin"),
        ]:
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
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_ai03_day_count_switch_and_base_rate_hint(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ai03admin"))
    ro = bearer(login(client, world, "ai03read"))
    other = bearer(login(client, world, "ai03other"))

    start = _ok(client.get(URL, headers=ro))
    assert start["day_count"] == "act_365_fixed" == start["default_day_count"]
    assert set(start["day_counts"]) == {"act_365_fixed", "act_act"}
    assert start["question"] == "AI03-01"
    assert start["base_rate_stale"] is True  # no rate maintained yet
    assert "Kein Basiszinssatz" in start["base_rate_hint"]
    assert client.get(URL, params={"x": "1"}, headers=h).status_code == 422

    assert client.put(URL, json={"day_count": "act_act"}, headers=ro).status_code == 403
    assert client.put(URL, json={"day_count": "30_360"}, headers=h).status_code == 422
    assert client.put(URL, json={"day_count": "act_act", "x": 1}, headers=h).status_code == 422
    changed = _ok(client.put(URL, json={"day_count": "act_act"}, headers=h))
    assert changed["day_count"] == "act_act"
    # Tenant separation: the other tenant keeps its default.
    assert _ok(client.get(URL, headers=other))["day_count"] == "act_365_fixed"

    boundary = start["current_half_year_from"]
    _ok(
        client.post(
            "/api/v1/accounting/dunning-interest-rates",
            json={"valid_from": boundary, "base_rate": "1.27", "source": "Testwert AI03"},
            headers=h,
        ),
        201,
    )
    fresh = _ok(client.get(URL, headers=h))
    assert fresh["base_rate_stale"] is False
    assert fresh["base_rate_hint"] is None
    assert fresh["latest_rate_valid_from"] == boundary
    assert _ok(client.get(URL, headers=other))["base_rate_stale"] is True

    assert client.post(f"{URL}/base-rate-checkpoints", headers=ro).status_code == 403
    created = _ok(client.post(f"{URL}/base-rate-checkpoints", headers=h))
    assert [c["effective_from"] for c in created] == start["next_change_dates"]
    assert all(c["status"] == "draft" and c["rule_id"] == "AI03-Basiszinssatz" for c in created)
    assert _ok(client.post(f"{URL}/base-rate-checkpoints", headers=h)) == []
    listed = _ok(
        client.get(
            "/api/v1/accounting/rule-versions/checkpoints",
            params={"lead_days": 400, "on": local_today().isoformat()},
            headers=h,
        )
    )
    assert {c["effective_from"] for c in listed if c["rule_id"] == "AI03-Basiszinssatz"} == set(
        start["next_change_dates"]
    )
    assert _ok(client.get("/api/v1/accounting/rule-versions/checkpoints", headers=other)) == []
    _ok(client.put(URL, json={"day_count": "act_365_fixed"}, headers=h))
