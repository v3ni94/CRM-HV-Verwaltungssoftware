"""GAJ-603 against PostgreSQL: POST /properties/{id}/owners refuses an overlapping period of
the same party and a share sum above 100 percent with 422; a following period and co-owners
up to 100 percent are accepted; another tenant gets 404, a reader 403. Rows are invented."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"am03a-{RUN}", name=f"AM03 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"am03b-{RUN}", name=f"AM03 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("am03admin", a, "tenant_admin"),
            ("am03reader", a, "read_only"),
            ("am03adminb", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _status(response: Any, code: int) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def test_owner_periods_and_share_sum(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "am03admin"))
    no = f"{(int(RUN, 16) + 7) % 900 + 100:03d}"
    prop = _status(
        client.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AM03 {no}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    url = f"/api/v1/properties/{prop['id']}/owners"
    p1, _ = _party(client, h, "Amdreia")
    p2, _ = _party(client, h, "Amdreib")
    p3, _ = _party(client, h, "Amdreic")

    first = {
        "party_id": p1,
        "valid_from": "2020-01-01",
        "valid_to": "2023-12-31",
        "share_percent": "60",
    }
    _status(client.post(url, json=first, headers=h), 201)
    # Same party, overlapping period: 422.
    overlap = {"party_id": p1, "valid_from": "2023-06-01"}
    body = _status(client.post(url, json=overlap, headers=h), 422)
    assert "bereits Eigentümer" in body["detail"]
    # Same party, following period: fine.
    _status(
        client.post(
            url, json={"party_id": p1, "valid_from": "2024-01-01", "share_percent": "60"}, headers=h
        ),
        201,
    )
    # Co-owner 40 percent: sum exactly 100.
    _status(
        client.post(
            url, json={"party_id": p2, "valid_from": "2022-01-01", "share_percent": "40"}, headers=h
        ),
        201,
    )
    # Third owner with share: from 2022 the sum exceeds 100 (60 + 40 + 1).
    body = _status(
        client.post(
            url, json={"party_id": p3, "valid_from": "2021-01-01", "share_percent": "1"}, headers=h
        ),
        422,
    )
    assert "01.01.2022" in body["detail"]
    assert "101" in body["detail"]
    # Without share (unknown co-ownership) no sum check.
    _status(client.post(url, json={"party_id": p3, "valid_from": "2021-01-01"}, headers=h), 201)

    reader = bearer(login(client, world, "am03reader"))
    _status(
        client.post(url, json={"party_id": p3, "valid_from": "2030-01-01"}, headers=reader), 403
    )
    other = bearer(login(client, world, "am03adminb"))
    _status(client.post(url, json={"party_id": p3, "valid_from": "2030-01-01"}, headers=other), 404)
