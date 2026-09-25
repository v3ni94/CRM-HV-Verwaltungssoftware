"""M13-04: outgoing invoice numbering PREFIX-JJJJ-000001, gapless and per tenant/year, allocated
under a locked counter row (operator decision 25.09.2026)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.accounting import numbering
from mhvp.core import crypto
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"num-{RUN}", name=f"Nummer {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("numadmin"), display_name="num", password=PASSWORD
        )
        world.users["numadmin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_gapless_and_concurrent_allocation(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "numadmin"))
    _ok(client.patch("/api/v1/tenant/billing-settings", json={"invoice_prefix": "TST"}, headers=h))

    async def run() -> list[str]:
        from mhvp.core.db.engine import create_app_engine, create_session_factory

        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)

        async def one() -> str:
            async with tenant_transaction(factory, world.tenant_a) as session:
                return await numbering.allocate_invoice_number(session, world.tenant_a, 2026)

        try:
            return list(await asyncio.gather(*(one() for _ in range(20))))
        finally:
            await engine.dispose()

    numbers = asyncio.run(run())
    assert sorted(numbers) == [f"TST-2026-{n:06d}" for n in range(1, 21)]
    assert len(set(numbers)) == 20


def test_missing_prefix_blocks_allocation(database: Database, redis_url: str) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.problems import ErrorCodes, ProblemError

    async def _bare_tenant() -> Any:
        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            tenant_id, _ = await services.provision_tenant(
                factory, slug=f"num-noprefix-{RUN}", name=f"Ohne Kürzel {RUN}"
            )
            return tenant_id
        finally:
            await engine.dispose()

    # A tenant with no billing settings row and no prefix at all.
    other = asyncio.run(_bare_tenant())

    async def run() -> str | None:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, other) as session:
                try:
                    await numbering.allocate_invoice_number(session, other, 2026)
                except ProblemError as exc:
                    return exc.error.code
                return None
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == ErrorCodes.BILLING_PREFIX_MISSING.code
