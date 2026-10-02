"""AH20 (GAG-31, GAG-10): rule templates and the demo flag in GET /auth/me (prefix ``ah20``).

Expected: GET /automation/rule-templates lists the examples to authorised readers only
(401/403), rejects unknown query parameters (422); a template copied through POST
/automation/rules is created inactive, is invisible to another tenant and a second copy under
the same name is refused (409). /auth/me serves is_demo for every role of a tenant.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.automation.templates import RULE_TEMPLATES
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
        a, _ = await services.provision_tenant(factory, slug=f"ah20a-{RUN}", name=f"AH20 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ah20b-{RUN}", name=f"AH20 B {RUN}")
        d, _ = await services.provision_tenant(
            factory, slug=f"ah20d-{RUN}", name=f"AH20 D {RUN}", is_demo=True
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("ah20admin", "tenant_admin", a),
            ("ah20care", "caretaker", a),
            ("ah20broker", "insurance_broker", a),
            ("ah20adminb", "tenant_admin", b),
            ("ah20demoadmin", "tenant_admin", d),
            ("ah20democare", "caretaker", d),
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


def test_templates_list_permissions_and_validation(client: TestClient, world: World) -> None:
    admin = _h(client, world, "ah20admin")
    res = client.get(f"{A}/rule-templates", headers=admin)
    assert res.status_code == 200, res.text
    items = res.json()
    assert [t["key"] for t in items] == [t["key"] for t in RULE_TEMPLATES]
    assert all({"name", "trigger_kind", "actions"} <= set(t) for t in items)
    # Caretaker reads tickets and may therefore read the examples; no role, no access.
    assert (
        client.get(f"{A}/rule-templates", headers=_h(client, world, "ah20care")).status_code == 200
    )
    assert (
        client.get(f"{A}/rule-templates", headers=_h(client, world, "ah20broker")).status_code
        == 403
    )
    assert client.get(f"{A}/rule-templates").status_code == 401
    assert client.get(f"{A}/rule-templates?foo=1", headers=admin).status_code == 422


def test_event_type_catalogue_permissions_and_validation(client: TestClient, world: World) -> None:
    """GAH-307: GET /automation/event-types lists the emitted types to authorised readers."""
    from mhvp.automation.event_catalog import ALL_EVENT_TYPES, EVENT_CATALOG

    res = client.get(f"{A}/event-types", headers=_h(client, world, "ah20admin"))
    assert res.status_code == 200, res.text
    assert res.json()["event_types"] == list(ALL_EVENT_TYPES)
    assert "contract.created" in EVENT_CATALOG
    care = _h(client, world, "ah20care")
    assert client.get(f"{A}/event-types", headers=care).status_code == 200
    assert (
        client.get(f"{A}/event-types", headers=_h(client, world, "ah20broker")).status_code == 403
    )
    assert client.get(f"{A}/event-types").status_code == 401
    assert client.get(f"{A}/event-types?x=1", headers=care).status_code == 422


def test_template_copy_is_inactive_tenant_bound_and_unique(
    client: TestClient, world: World
) -> None:
    admin = _h(client, world, "ah20admin")
    template = client.get(f"{A}/rule-templates", headers=admin).json()[0]
    body = {k: v for k, v in template.items() if k != "key"}
    created = client.post(f"{A}/rules", json=body, headers=admin)
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["active"] is False
    assert rule["name"] == template["name"]
    # The same template twice is a name conflict, the caretaker may not copy at all.
    assert client.post(f"{A}/rules", json=body, headers=admin).status_code == 409
    care = _h(client, world, "ah20care")
    assert client.post(f"{A}/rules", json=body, headers=care).status_code == 403
    # Tenant separation: B sees neither the rule nor can it read it by id, and may copy again.
    other = _h(client, world, "ah20adminb")
    names = [r["name"] for r in client.get(f"{A}/rules", headers=other).json()]
    assert template["name"] not in names
    assert client.get(f"{A}/rules/{rule['id']}", headers=other).status_code == 404
    assert client.post(f"{A}/rules", json=body, headers=other).status_code == 201


def test_me_serves_is_demo_for_every_role(client: TestClient, world: World) -> None:
    expected = {
        "ah20admin": False,
        "ah20care": False,
        "ah20adminb": False,
        "ah20demoadmin": True,
        "ah20democare": True,
    }
    for name, flag in expected.items():
        res = client.get("/api/v1/auth/me", headers=_h(client, world, name))
        assert res.status_code == 200, res.text
        assert res.json()["is_demo"] is flag, name
