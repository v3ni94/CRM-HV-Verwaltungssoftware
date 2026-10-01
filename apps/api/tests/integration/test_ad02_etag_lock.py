"""If-Match under row lock (AD02, AC01-01, ADR 0012): two concurrent writes with the same
ETag, exactly one gets 200 and the other 412. Tenant separation (404) and 403 unchanged.
Own test world with prefix ``ad02``."""

import asyncio
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
R = "/api/v1/automation/rules"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ad02-{RUN}", name=f"AD02 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ad02b-{RUN}", name=f"AD02 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("ad02admin", "tenant_admin", a),
            ("ad02ro", "read_only", a),
            ("ad02adminb", "tenant_admin", b),
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


def _rule(client: TestClient, h: dict[str, str], name: str) -> dict[str, Any]:
    response = client.post(
        R,
        json={
            "name": name,
            "active": False,
            "trigger_kind": "event",
            "trigger_event_type": "message.received",
            "conditions": {
                "op": "and",
                "conditions": [
                    {"field": "entity.from_address", "op": "eq", "value": "x@ad02.example"}
                ],
            },
            "actions": [
                {
                    "type": "assign_record",
                    "target": "message",
                    "dimension": "contact",
                    "value": "00000000-0000-7000-8000-000000000000",
                }
            ],
        },
        headers=h,
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_concurrent_if_match_one_wins(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "ad02admin", world.tenant_a))
    rule = _rule(client, h, f"AD02 Regel {RUN}")
    url = f"{R}/{rule['id']}"
    got = client.get(url, headers=h)
    assert got.status_code == 200, got.text
    etag = got.headers["ETag"]
    settings = _settings(database, redis_url)
    barrier = threading.Barrier(2)

    def write(n: int) -> int:
        with TestClient(create_app(settings)) as own:
            barrier.wait()
            return own.patch(
                url, json={"name": f"AD02 Regel {RUN} {n}"}, headers={**h, "If-Match": etag}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(write, range(2)))
    assert codes == [200, 412]
    after = client.get(url, headers=h)
    assert after.headers["ETag"] != etag
    assert after.json()["name"] in {f"AD02 Regel {RUN} 0", f"AD02 Regel {RUN} 1"}


def test_locked_load_keeps_tenant_and_permission(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ad02admin", world.tenant_a))
    rule = _rule(client, h, f"AD02 Fremd {RUN}")
    url = f"{R}/{rule['id']}"
    etag = client.get(url, headers=h).headers["ETag"]
    other = bearer(login(client, world, "ad02adminb", world.tenant_b))
    assert (
        client.patch(url, json={"name": "x"}, headers={**other, "If-Match": etag}).status_code
        == 404
    )
    ro = bearer(login(client, world, "ad02ro", world.tenant_a))
    assert (
        client.patch(url, json={"name": "x"}, headers={**ro, "If-Match": etag}).status_code == 403
    )
    stale = client.patch(
        url, json={"name": f"AD02 Fremd {RUN} 2"}, headers={**h, "If-Match": '"t1"'}
    )
    assert stale.status_code == 412
    ok = client.patch(url, json={"name": f"AD02 Fremd {RUN} 2"}, headers={**h, "If-Match": etag})
    assert ok.status_code == 200, ok.text


def test_load_for_etag_unit() -> None:
    from mhvp.core.etag import load_for_etag
    from mhvp.core.problems import ProblemError

    class _S:
        def __init__(self, row: Any) -> None:
            self.row, self.kw = row, {}

        async def get(self, model: Any, entity_id: Any, **kw: Any) -> Any:
            self.kw = kw
            return self.row

    class _Row:
        tenant_id = "a"

    s = _S(_Row())
    assert asyncio.run(load_for_etag(s, object, 1, "a")) is s.row
    assert s.kw == {"with_for_update": True}
    with pytest.raises(ProblemError):
        asyncio.run(load_for_etag(s, object, 1, "b"))
    with pytest.raises(ProblemError):
        asyncio.run(load_for_etag(_S(None), object, 1))
