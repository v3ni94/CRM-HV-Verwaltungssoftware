"""AO11 (AN07): GET /automation/rules and /rules/{id} serve the typed AutomationRuleOut with the
boolean ``needs_ai_approval``; sparse ``fields`` keep working, other tenants get 404, readers
without the permission 403 (prefix ``ao11``)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/automation"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ao11a-{RUN}", name=f"AO11 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ao11b-{RUN}", name=f"AO11 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("ao11admin", "tenant_admin", a),
            ("ao11broker", "insurance_broker", a),
            ("ao11adminb", "tenant_admin", b),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _h(client: TestClient, world: World, name: str) -> dict[str, str]:
    return bearer(login(client, world, name))


def _rule(headers: dict[str, str], client: TestClient, name: str) -> dict[str, Any]:
    template = client.get(f"{A}/rule-templates", headers=headers).json()[0]
    return {**{k: v for k, v in template.items() if k != "key"}, "name": name}


def test_rule_list_and_read_are_typed(client: TestClient, world: World) -> None:
    admin = _h(client, world, "ao11admin")
    rule = _rule(admin, client, f"AO11 Regel {RUN}")
    created = client.post(f"{A}/rules", json=rule, headers=admin)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    listed = client.get(f"{A}/rules", headers=admin)
    assert listed.status_code == 200
    row = next(r for r in listed.json() if r["id"] == rule_id)
    assert row["needs_ai_approval"] is False
    assert client.get(f"{A}/rules/{rule_id}", headers=admin).json()["needs_ai_approval"] is False
    sparse = client.get(f"{A}/rules?fields=name", headers=admin).json()
    assert {"id", "name"} <= set(sparse[0])
    assert "needs_ai_approval" not in sparse[0]
    schema = client.get("/api/v1/openapi.json").json()["components"]["schemas"]["AutomationRuleOut"]
    assert schema["properties"]["needs_ai_approval"]["type"] == "boolean"


def test_rule_routes_authz_and_tenant_separation(client: TestClient, world: World) -> None:
    admin = _h(client, world, "ao11admin")
    created = client.post(
        f"{A}/rules",
        json=_rule(admin, client, f"AO11 Fremd {RUN}"),
        headers=admin,
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    assert client.get(f"{A}/rules").status_code == 401
    assert client.get(f"{A}/rules", headers=_h(client, world, "ao11broker")).status_code == 403
    other = _h(client, world, "ao11adminb")
    assert client.get(f"{A}/rules/{rule_id}", headers=other).status_code == 404
    assert rule_id not in [r["id"] for r in client.get(f"{A}/rules", headers=other).json()]
    assert client.get(f"{A}/rules?bogus=1", headers=admin).status_code == 422
