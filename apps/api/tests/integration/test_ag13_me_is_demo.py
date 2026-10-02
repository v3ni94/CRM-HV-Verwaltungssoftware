"""AG13 (AF19-R): GET /auth/me serves the tenant demo flag (own world, prefix ``ag13``).

Expected: member of the demo tenant gets is_demo true, member of the real tenant false.
"""

import asyncio
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: object) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)  # type: ignore[arg-type]
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag13a-{RUN}", name=f"AG13 A {RUN}")
        d, _ = await services.provision_tenant(
            factory, slug=f"ag13d-{RUN}", name=f"AG13 D {RUN}", is_demo=True
        )
        world = World(tenant_a=a, tenant_b=d, app_url=settings.database_url.get_secret_value())  # type: ignore[attr-defined]
        for name, tenant_id in (("ag13real", a), ("ag13demo", d)):
            uid: uuid.UUID = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=False,
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant_id,
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


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def test_me_is_demo_follows_tenant(client: TestClient, world: World) -> None:
    demo = client.get("/api/v1/auth/me", headers=bearer(login(client, world, "ag13demo")))
    real = client.get("/api/v1/auth/me", headers=bearer(login(client, world, "ag13real")))
    assert demo.status_code == 200
    assert demo.json()["is_demo"] is True
    assert real.status_code == 200
    assert real.json()["is_demo"] is False


def test_me_requires_authentication(client: TestClient, world: World) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
