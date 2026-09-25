"""M35 Stufe 3 part 5 backend: CRUD for `objektakte_classification_rule` (list, create, edit,
activate/deactivate, delete), used by the CRM rules settings page."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte/classification-rules"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(database, redis_url)


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m35rules-{RUN}", name=f"R {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in (("rulesadmin", "tenant_admin"), ("rulesreader", "read_only")):
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
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_rules_crud_and_authorization(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "rulesadmin"))
    reader = bearer(login(client, world, "rulesreader"))

    forbidden = client.post(
        BASE,
        json={
            "name": "Test",
            "pattern_type": "filename_regex",
            "pattern_value": "test",
        },
        headers=reader,
    )
    assert forbidden.status_code == 403

    created = _ok(
        client.post(
            BASE,
            json={
                "name": "Verwalterbestellung",
                "pattern_type": "text_keyword",
                "pattern_value": "bestellung (des|zum|zur) verwalt",
                "priority": 200,
                "confidence": 0.9,
            },
            headers=admin,
        ),
        201,
    )
    assert created["active"] is True

    listed = _ok(client.get(BASE, headers=reader))
    assert any(r["id"] == created["id"] for r in listed)

    patched = _ok(client.patch(f"{BASE}/{created['id']}", json={"active": False}, headers=admin))
    assert patched["active"] is False

    unknown_category = client.post(
        BASE,
        json={
            "name": "x",
            "pattern_type": "filename_regex",
            "pattern_value": "x",
            "target_category_id": str(uuid.uuid4()),
        },
        headers=admin,
    )
    assert unknown_category.status_code == 404

    deleted = client.delete(f"{BASE}/{created['id']}", headers=admin)
    assert deleted.status_code == 204
    after = _ok(client.get(BASE, headers=admin))
    assert not any(r["id"] == created["id"] for r in after)
