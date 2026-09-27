"""Read after write on ``PATCH`` + ``GET /api/v1/properties/{id}`` under concurrency.

Finding of the CI run of 27.09.2026 (Playwright inline-edit.spec under load): after a
committed ``PATCH`` a directly following ``GET`` returned ``version: 1`` and empty fields.
This test drives the ASGI app with a real PostgreSQL through ``httpx.AsyncClient`` and
runs 20 concurrent workers, each with its own property, each doing ``PATCH`` followed by
``GET`` in a loop. Expected result, fixed in advance: every ``GET`` after a 200 ``PATCH``
returns exactly the patched city and the incremented version (1 + number of patches), the
``ETag`` header equals the version, and no field of the master data is lost.

Rules covered: one transaction per request with the tenant bound through ``set_config``
(ADR 0002, section 5.3), pooled connections carry no stale snapshot or open transaction,
``expire_on_commit=False`` never serves stale identity map state across requests.

Checked on 27.09.2026 without finding a cause in the API (this test passed with 100
PATCH + GET pairs across 20 workers): ``tenant_transaction`` binds the tenant per
transaction and the session is created per request; the engine uses the default
READ COMMITTED isolation, ``pool_pre_ping`` and rollback on return; the GET handler holds
no cache; ``serverFetch`` and the BFF route send ``cache: "no-store"``. The CI finding is
therefore attributed to the test environment (a second API instance or database behind
``MHVP_API_INTERNAL_URL``), which this test cannot reproduce.
"""

import asyncio
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration

WORKERS = 20
ROUNDS = 5


async def _world(settings: Any) -> World:
    """Own tenant and user so that credential changes in the shared session world (other
    test modules) cannot break this test."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"raw-{RUN}", name=f"RAW {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("rawadmin"), display_name="rawadmin", password=PASSWORD
        )
        world.users["rawadmin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


def _token(database: Database, redis_url: str, world: World) -> dict[str, str]:
    with TestClient(create_app(_settings(database, redis_url))) as client:
        return bearer(login(client, world, "rawadmin"))


async def _worker(
    client: httpx.AsyncClient, headers: dict[str, str], index: int, run: str
) -> list[str]:
    """Creates one property and alternates PATCH and GET. Returns a list of deviations."""
    problems: list[str] = []
    created = await client.post(
        "/api/v1/properties",
        json={
            "number": f"{800 + index}",
            "name": f"RAW {run} {index}",
            "management_type": "rental",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    prop = created.json()
    pid = prop["id"]
    version = prop["version"]
    assert version == 1
    for round_ in range(1, ROUNDS + 1):
        city = f"Stadt {index}-{round_}"
        patched = await client.patch(
            f"/api/v1/properties/{pid}",
            json={"city": city},
            headers={**headers, "If-Match": f'"{version}"'},
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()
        if body["city"] != city or body["version"] != version + 1:
            problems.append(f"PATCH {pid} round {round_}: {body['city']!r} v{body['version']}")
        version += 1
        read = await client.get(f"/api/v1/properties/{pid}", headers=headers)
        assert read.status_code == 200, read.text
        got: dict[str, Any] = read.json()
        expected = {
            "id": pid,
            "city": city,
            "version": version,
            "name": prop["name"],
            "number": prop["number"],
        }
        actual = {k: got.get(k) for k in expected}
        if actual != expected:
            problems.append(f"GET {pid} round {round_}: expected {expected}, got {actual}")
        if read.headers.get("etag") != f'"{version}"':
            problems.append(f"GET {pid} round {round_}: ETag {read.headers.get('etag')!r}")
    return problems


async def _run(database: Database, redis_url: str, headers: dict[str, str], run: str) -> list[str]:
    app = create_app(_settings(database, redis_url))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            results = await asyncio.gather(
                *(_worker(client, headers, i, run) for i in range(WORKERS))
            )
    return [p for sub in results for p in sub]


def test_get_after_patch_returns_new_state_under_concurrency(
    database: Database, redis_url: str, world: World
) -> None:
    headers = _token(database, redis_url, world)
    run = str(id(world))[-6:]
    problems = asyncio.run(_run(database, redis_url, headers, run))
    assert problems == [], "\n".join(problems)
