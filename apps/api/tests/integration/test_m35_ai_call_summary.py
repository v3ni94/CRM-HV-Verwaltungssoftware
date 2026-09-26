"""M35 Stufe 4 follow-up (docs/plans/M35-objektakte-uebernahme.md, docs/rules/M35-03.md):
`GET /api/v1/objektakte/ai-calls/summary`, the cost evaluation of the taken over objektakte
AI call protocol per property and per month. Happy path (sums recomputable from the dump),
filters, permission (`objektakte:read`), tenant separation."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m35_stufe4_permissions_users_aicalls import _dump

pytestmark = pytest.mark.integration
IMPORTS = "/api/v1/objektakte/imports"
SUMMARY = "/api/v1/objektakte/ai-calls/summary"


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aisum-{RUN}", name=f"AiSum {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aisumb-{RUN}", name=f"AiSum B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("aisadmin", a, "tenant_admin"),
            ("aisclerk", a, "standard"),
            ("aisreader", a, "read_only"),
            ("aiscaretaker", a, "caretaker"),
            ("aisother", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _apply(client: TestClient, world: World, headers: dict[str, str]) -> Any:
    return _ok(
        client.post(
            IMPORTS,
            params={"mode": "apply"},
            files={"file": ("dump.sql", _dump(world).encode("utf-8"), "application/sql")},
            headers=headers,
        )
    )


def test_summary_per_property_and_month(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "aisadmin", world.tenant_a))
    applied = _apply(client, world, admin)
    property_id = applied["id_map"]["objects_managedobject"]["12"]

    reader = bearer(login(client, world, "aisreader"))
    body = _ok(client.get(SUMMARY, headers=reader))
    # Dump: three calls in 2026-02, all on object 12, costs 0.001200 + 0.000300 + none.
    assert body["total"] == {
        "calls": 3,
        "tokens_in": 1000,
        "tokens_out": 70,
        "cost_eur": "0.001500",
    }
    assert body["by_property"] == [
        {
            "property_id": property_id,
            "property_number": "712",
            "property_name": "Haus Stufe vier",
            "calls": 3,
            "tokens_in": 1000,
            "tokens_out": 70,
            "cost_eur": "0.001500",
        }
    ]
    assert body["by_month"] == [
        {
            "month": "2026-02",
            "calls": 3,
            "tokens_in": 1000,
            "tokens_out": 70,
            "cost_eur": "0.001500",
        }
    ]

    # Period filter (inclusive days) and property filter.
    narrowed = _ok(
        client.get(
            SUMMARY,
            params={"property_id": property_id, "from": "2026-02-11", "to": "2026-02-11"},
            headers=reader,
        )
    )
    assert narrowed["total"]["calls"] == 1
    assert narrowed["total"]["tokens_in"] == 200
    assert narrowed["from"] == "2026-02-11"
    assert narrowed["property_id"] == property_id
    empty = _ok(client.get(SUMMARY, params={"from": "2027-01-01"}, headers=reader))
    assert empty["by_property"] == []
    assert empty["by_month"] == []
    assert empty["total"] == {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_eur": "0.000000"}

    invalid = client.get(SUMMARY, params={"from": "2026-03-01", "to": "2026-02-01"}, headers=reader)
    assert invalid.status_code in (400, 422), invalid.text


def test_summary_requires_objektakte_read(client: TestClient, world: World) -> None:
    caretaker = bearer(login(client, world, "aiscaretaker"))
    assert client.get(SUMMARY, headers=caretaker).status_code == 403
    assert client.get(SUMMARY).status_code == 401


def test_summary_is_tenant_separated(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "aisadmin", world.tenant_a))
    applied = _apply(client, world, admin)
    property_id = applied["id_map"]["objects_managedobject"]["12"]

    other = bearer(login(client, world, "aisother", world.tenant_b))
    body = _ok(client.get(SUMMARY, headers=other))
    assert body["total"]["calls"] == 0
    assert body["by_property"] == []
    filtered = _ok(client.get(SUMMARY, params={"property_id": property_id}, headers=other))
    assert filtered["total"]["calls"] == 0
