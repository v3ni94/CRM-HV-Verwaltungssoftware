"""AM14 (GAJ-610): address list, refused cut off date query, primary address after a merge."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services as platform
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
C = "/api/v1/contacts"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await platform.provision_tenant(factory, slug=f"am14a-{RUN}", name=f"AM14 A {RUN}")
        b, _ = await platform.provision_tenant(factory, slug=f"am14b-{RUN}", name=f"AM14 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("one", a, "tenant_admin"),
            ("two", a, "tenant_admin"),
            ("other", b, "tenant_admin"),
        ]:
            uid = await platform.create_user(
                factory, email=world.email(f"am14{name}"), display_name=name, password=PASSWORD
            )
            world.users[f"am14{name}"] = uid
            await platform.add_member(
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


def _contact(c: TestClient, h: dict[str, str], last: str, city: str) -> dict[str, Any]:
    body = {
        "kind": "person",
        "first_name": "Max",
        "last_name": last,
        "addresses": [{"street": "Weg", "house_number": "1", "city": city, "is_primary": True}],
    }
    r = c.post(C, json=body, headers=h)
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_addresses_list_and_as_of_refused(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "am14one"))
    other = bearer(login(client, world, "am14other"))
    contact = _contact(client, one, f"Adr{RUN}", "Hilden")
    r = client.get(f"{C}/{contact['id']}/addresses", headers=one)
    assert r.status_code == 200, r.text
    assert r.json()["history_available"] is False
    assert [a["city"] for a in r.json()["items"]] == ["Hilden"]
    refused = client.get(f"{C}/{contact['id']}/addresses?as_of=2025-01-01", headers=one)
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "MHVP-CONT-0034"
    assert refused.json()["open_question"] == "AM14-01"
    unknown = client.get(f"{C}/{contact['id']}/addresses?foo=1", headers=one)
    assert unknown.status_code == 422
    assert client.get(f"{C}/{contact['id']}/addresses", headers=other).status_code == 404
    assert client.get(f"{C}/{uuid.uuid4()}/addresses", headers=one).status_code == 404
    assert client.get(f"{C}/{contact['id']}/addresses").status_code == 401


def test_merge_keeps_one_primary_address(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "am14one"))
    two = bearer(login(client, world, "am14two"))
    src = _contact(client, one, f"Quelle{RUN}", "Erkrath")
    dst = _contact(client, one, f"Ziel{RUN}", "Hilden")
    p = client.post(
        "/api/v1/contact-merges",
        json={"source_id": src["id"], "target_id": dst["id"], "reason": "Dublette"},
        headers=one,
    )
    assert p.status_code == 201, p.text
    done = client.post(f"/api/v1/contact-merges/{p.json()['id']}/execute", json={}, headers=two)
    assert done.status_code == 200, done.text
    items = client.get(f"{C}/{dst['id']}/addresses", headers=one).json()["items"]
    assert sorted(a["city"] for a in items) == ["Erkrath", "Hilden"]
    assert [a["city"] for a in items if a["is_primary"]] == ["Hilden"]
