"""M2-05 cross tenant working view (``/api/v1/platform/overview``): a platform administrator
sees exactly the tenants of his active memberships, each read in its own tenant transaction;
no membership means no data (also for the superadmin of ADR 0011); tenant users get 403; every
read is recorded per tenant as ``platform.overview_viewed``."""

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration

OVERVIEW = "/api/v1/platform/overview"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ova-{RUN}", name=f"Overview A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ovb-{RUN}", name=f"Overview B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs: dict[str, tuple[bool, list[Any]]] = {
            # Platform administrator, member of both tenants.
            "ovboth": (True, [a, b]),
            # Platform administrator, member of A only.
            "ovone": (True, [a]),
            # Platform administrator without any membership.
            "ovnone": (True, []),
            # Tenant administrator of both tenants, no platform administrator.
            "ovuser": (False, [a, b]),
        }
        for name, (is_admin, tenants) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            for tenant in tenants:
                await services.add_member(
                    factory,
                    tenant_id=tenant,
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"Objekt {number}",
        "management_type": "rental",
        "street": "Beispielweg",
        "house_number": "7",
        "postal_code": "40789",
        "city": "Musterstadt",
    }
    return cast(dict[str, Any], _ok(c.post("/api/v1/properties", json=body, headers=h), 201))


def _ticket(c: TestClient, h: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"title": "Testfall"} | overrides
    return cast(dict[str, Any], _ok(c.post("/api/v1/tickets", json=body, headers=h), 201))


@pytest.fixture(scope="module")
def data(client: TestClient, world: World) -> dict[str, Any]:
    """One property and one open ticket per tenant, created by the tenant administrator
    ``ovuser`` inside each tenant (regular write path, no cross tenant write)."""
    out: dict[str, Any] = {}
    for key, tenant in (("a", world.tenant_a), ("b", world.tenant_b)):
        h = bearer(login(client, world, "ovuser", tenant_id=tenant))
        prop = _property(client, h, "901" if key == "a" else "902")
        priority = "urgent" if key == "b" else "normal"
        ticket = _ticket(
            client, h, title=f"Ticket {key}", property_id=prop["id"], priority=priority
        )
        out[key] = {"property": prop, "ticket": ticket}
    return out


def test_admin_with_two_memberships_sees_both_tenants(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "ovboth"))
    body = _ok(client.get(OVERVIEW, headers=h))
    by_tenant = {row["tenant_id"]: row for row in body["tenants"]}
    assert set(by_tenant) == {str(world.tenant_a), str(world.tenant_b)}
    for key, tenant in (("a", world.tenant_a), ("b", world.tenant_b)):
        row = by_tenant[str(tenant)]
        assert row["tenant_name"].startswith("Overview " + key.upper())
        assert row["properties"] == 1
        assert row["open_tickets"] == 1
        assert row["open_approvals"] == 0
        assert set(row["approvals"]) == {
            "release_gates",
            "bank_accounts",
            "mail",
            "dunning_runs",
            "direct_debits",
        }
    assert body["totals"]["properties"] == 2
    assert body["totals"]["open_tickets"] == 2

    tickets = _ok(client.get(f"{OVERVIEW}/tickets", headers=h))
    ids = [t["id"] for t in tickets]
    assert set(ids) == {data["a"]["ticket"]["id"], data["b"]["ticket"]["id"]}
    # Urgency first: the urgent ticket of tenant B comes before the normal one of tenant A.
    assert ids[0] == data["b"]["ticket"]["id"]
    assert tickets[0]["tenant_id"] == str(world.tenant_b)
    assert tickets[0]["tenant_name"].startswith("Overview B")

    properties = _ok(client.get(f"{OVERVIEW}/properties", headers=h))
    assert {p["id"] for p in properties} == {
        data["a"]["property"]["id"],
        data["b"]["property"]["id"],
    }
    assert all(p["open_tickets"] == 1 for p in properties)
    assert {p["tenant_id"] for p in properties} == {str(world.tenant_a), str(world.tenant_b)}


def test_admin_with_one_membership_sees_only_that_tenant(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "ovone"))
    body = _ok(client.get(OVERVIEW, headers=h))
    assert [row["tenant_id"] for row in body["tenants"]] == [str(world.tenant_a)]
    tickets = _ok(client.get(f"{OVERVIEW}/tickets", headers=h))
    assert [t["id"] for t in tickets] == [data["a"]["ticket"]["id"]]
    assert data["b"]["ticket"]["id"] not in {t["id"] for t in tickets}
    properties = _ok(client.get(f"{OVERVIEW}/properties", headers=h))
    assert [p["id"] for p in properties] == [data["a"]["property"]["id"]]


def test_admin_without_membership_sees_nothing(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "ovnone"))
    body = _ok(client.get(OVERVIEW, headers=h))
    assert body["tenants"] == []
    assert body["totals"]["properties"] == 0
    assert _ok(client.get(f"{OVERVIEW}/tickets", headers=h)) == []
    assert _ok(client.get(f"{OVERVIEW}/properties", headers=h)) == []


def test_superadmin_marker_grants_no_extra_tenant(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    padmin = bearer(login(client, world, "ovboth"))
    target = world.users["ovone"]
    try:
        _ok(client.put(f"/api/v1/platform/users/{target}/superadmin", headers=padmin))
        h = bearer(login(client, world, "ovone"))
        me = _ok(client.get("/api/v1/auth/me", headers=h))
        assert me["is_superadmin"] is True
        body = _ok(client.get(OVERVIEW, headers=h))
        assert [row["tenant_id"] for row in body["tenants"]] == [str(world.tenant_a)]
        tickets = _ok(client.get(f"{OVERVIEW}/tickets", headers=h))
        assert data["b"]["ticket"]["id"] not in {t["id"] for t in tickets}
    finally:
        client.delete(f"/api/v1/platform/users/{target}/superadmin", headers=padmin)


def test_tenant_user_is_forbidden(client: TestClient, world: World, data: dict[str, Any]) -> None:
    h = bearer(login(client, world, "ovuser", tenant_id=world.tenant_a))
    for path in (OVERVIEW, f"{OVERVIEW}/tickets", f"{OVERVIEW}/properties"):
        assert client.get(path, headers=h).status_code == 403, path
    assert client.get(OVERVIEW).status_code == 401


def _views(migrator_engine: Any, tenant_id: Any, user_id: Any) -> set[str]:
    """RLS is forced on ``domain_event`` (also for the owner role): bind the tenant first."""
    with migrator_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tenant_id)})
        rows = conn.execute(
            text(
                "SELECT payload->>'view' FROM domain_event "
                "WHERE type = 'platform.overview_viewed' AND actor_user_id = :u"
            ),
            {"u": str(user_id)},
        ).all()
    return {str(r[0]) for r in rows}


def test_read_is_recorded_per_tenant(
    client: TestClient, world: World, data: dict[str, Any], migrator_engine: Any
) -> None:
    h = bearer(login(client, world, "ovboth"))
    _ok(client.get(f"{OVERVIEW}/properties", headers=h))
    both = world.users["ovboth"]
    assert "properties" in _views(migrator_engine, world.tenant_a, both)
    assert "properties" in _views(migrator_engine, world.tenant_b, both)
    # The administrator without membership never produced a record in either tenant.
    none = world.users["ovnone"]
    assert _views(migrator_engine, world.tenant_a, none) == set()
    assert _views(migrator_engine, world.tenant_b, none) == set()
