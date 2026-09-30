"""M2-02 (Objektzuordnung je Mitgliedschaft) and M2-03 (WebAuthn prepared) over the API:
happy path, authorization (403), tenant separation (404), validation (422)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    _settings,
    bearer,
    login,
    login_password_only,
)

pytestmark = pytest.mark.integration
T = "/api/v1/tenant"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p14-{RUN}", name=f"P14 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p14b-{RUN}", name=f"P14 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("p14admin", a, "tenant_admin"),
            ("p14admin_b", b, "tenant_admin"),
            ("p14clerk", a, "standard"),
            ("p14reader", a, "read_only"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _membership_id(client: TestClient, h: dict[str, str], user_id: uuid.UUID) -> str:
    rows = client.get(f"{T}/members", headers=h)
    assert rows.status_code == 200, rows.text
    return next(str(r["membership_id"]) for r in rows.json() if r["user_id"] == str(user_id))


def _property(client: TestClient, h: dict[str, str], number: str) -> str:
    body = {
        "number": number,
        "name": f"Objekt {number}",
        "management_type": "hoa",
        "street": "Rheinpromenade",
        "house_number": "13",
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    response = client.post("/api/v1/properties", json=body, headers=h)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_member_property_assignment(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p14admin"))
    prop = _property(client, h, "701")
    member = _membership_id(client, h, world.users["p14clerk"])
    ok = client.put(f"{T}/members/{member}/properties", json={"property_ids": [prop]}, headers=h)
    assert ok.status_code == 204, ok.text
    row = next(
        r for r in client.get(f"{T}/members", headers=h).json() if r["membership_id"] == member
    )
    assert row["property_ids"] == [prop]
    # Validation: unknown property is refused.
    bad = client.put(
        f"{T}/members/{member}/properties", json={"property_ids": [str(uuid.uuid4())]}, headers=h
    )
    assert bad.status_code == 422, bad.text
    # Authorization: a reader may not change assignments.
    reader = bearer(login_password_only(client, world, "p14reader"))
    denied = client.put(
        f"{T}/members/{member}/properties", json={"property_ids": []}, headers=reader
    )
    assert denied.status_code == 403, denied.text
    # Tenant separation: the admin of tenant B does not find the membership of tenant A.
    hb = bearer(login(client, world, "p14admin_b"))
    foreign = client.put(f"{T}/members/{member}/properties", json={"property_ids": []}, headers=hb)
    assert foreign.status_code == 404, foreign.text
    # Empty list removes the restriction.
    cleared = client.put(f"{T}/members/{member}/properties", json={"property_ids": []}, headers=h)
    assert cleared.status_code == 204, cleared.text


def test_webauthn_prepared_not_available(client: TestClient, world: World) -> None:
    h = bearer(login_password_only(client, world, "p14clerk"))
    status = client.get("/api/v1/auth/webauthn/status", headers=h)
    assert status.status_code == 200, status.text
    assert status.json()["available"] is False
    assert client.get("/api/v1/auth/webauthn/credentials", headers=h).json() == []
    options = client.post("/api/v1/auth/webauthn/register/options", headers=h)
    assert options.status_code == 503
    assert options.json()["code"] == "MHVP-AUTH-0012"
    missing = client.delete(f"/api/v1/auth/webauthn/credentials/{uuid.uuid4()}", headers=h)
    assert missing.status_code == 404
    assert client.get("/api/v1/auth/webauthn/status").status_code == 401
