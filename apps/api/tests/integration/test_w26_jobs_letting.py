"""AP08 (GAM-510): task level tests of the letting beat jobs ``propose_rent_increases`` and
``hash_self_disclosure_tokens`` with two tenants, repetition and fault isolation.

Expected values by hand: rent 600,00 with a graduated step 650,00 thirty days ahead (inside the
60 day horizon) gives exactly one draft case 600,00 to 650,00 per tenant with the switch
``draft``; a second run adds none. A plain token ``t`` becomes ``sha256:`` plus the hex digest
of ``t``; a second run converts nothing and never hashes a hash again."""

import asyncio
import hashlib
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.core.clock import local_today
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.letting import tasks as letting_tasks
from mhvp.letting.models import Prospect, RentIncreaseCase, SelfDisclosureLink
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_an18_rent_increase_block import _contract
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
L = "/api/v1/letting"
ISOLATION_GAP = (
    "GAM-510/AP08: letting/tasks.py {job} has no per tenant error handling, a failure in "
    "tenant A stops tenant B (all other assertions of this test passed)"
)


async def _world(settings: Any) -> World:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"w26la-{RUN}", name=f"W26LA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"w26lb-{RUN}", name=f"W26LB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("w26ladmin", a), ("w26lother", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
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


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _failing_tenant(monkeypatch: pytest.MonkeyPatch, module: Any, bad: uuid.UUID) -> None:
    """Fault injection: the tenant transaction of ``bad`` raises inside the job."""
    original = module.tenant_transaction

    @asynccontextmanager
    async def wrapped(factory: Any, tenant_id: uuid.UUID) -> Any:
        if tenant_id == bad:
            raise RuntimeError("w26 injected tenant failure")
        async with original(factory, tenant_id) as session:
            yield session

    monkeypatch.setattr(module, "tenant_transaction", wrapped)


def _run(coro: Any) -> Any:
    """Runs a job; an injected failure may surface, the effect on the other tenant counts."""
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "w26 injected" not in str(exc):
            raise
        return None


async def _cases(settings: Any, tenant: uuid.UUID) -> list[tuple[str, str, str]]:
    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant) as session:
            rows = (await session.scalars(select(RentIncreaseCase))).all()
            return sorted((r.basis, f"{r.current_rent:.2f}", f"{r.target_rent:.2f}") for r in rows)
    finally:
        await engine.dispose()


def test_propose_rent_increases_two_tenants_repeat_and_isolation(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(database, redis_url)
    ha = bearer(login(client, world, "w26ladmin"))
    hb = bearer(login(client, world, "w26lother"))
    near = (local_today() + timedelta(days=30)).isoformat()
    for h, no in ((ha, "261"), (hb, "262")):
        contract, _, _ = _contract(client, h, no)
        steps = {"graduated_steps": [{"valid_from": near, "net": "650.00"}]}
        _ok(client.put(f"{L}/contracts/{contract}/index-terms", json=steps, headers=h))
    expected = [("graduated", "600.00", "650.00")]

    # Switch off in both tenants (default): the job drafts nothing.
    asyncio.run(letting_tasks.propose_rent_increases_once(settings))
    assert asyncio.run(_cases(settings, world.tenant_a)) == []
    assert asyncio.run(_cases(settings, world.tenant_b)) == []

    # Switch on in A only: one draft in A, none in B.
    draft = {"block_months": {}, "proposals": "draft"}
    _ok(client.put(f"{L}/rent-increase-settings", json=draft, headers=ha))
    asyncio.run(letting_tasks.propose_rent_increases_once(settings))
    assert asyncio.run(_cases(settings, world.tenant_a)) == expected
    assert asyncio.run(_cases(settings, world.tenant_b)) == []

    # Repetition: no second draft.
    asyncio.run(letting_tasks.propose_rent_increases_once(settings))
    assert asyncio.run(_cases(settings, world.tenant_a)) == expected

    # Failure in A must not keep B from its draft.
    _ok(client.put(f"{L}/rent-increase-settings", json=draft, headers=hb))
    _failing_tenant(monkeypatch, letting_tasks, world.tenant_a)
    _run(letting_tasks.propose_rent_increases_once(settings))
    monkeypatch.undo()
    isolated = asyncio.run(_cases(settings, world.tenant_b)) == expected
    assert asyncio.run(_cases(settings, world.tenant_a)) == expected
    # Next regular run catches B up, still exactly one draft per tenant.
    asyncio.run(letting_tasks.propose_rent_increases_once(settings))
    assert asyncio.run(_cases(settings, world.tenant_b)) == expected
    assert asyncio.run(_cases(settings, world.tenant_a)) == expected
    assert isolated, ISOLATION_GAP.format(job="propose_rent_increases_once")


def test_hash_self_disclosure_tokens_two_tenants_repeat_and_isolation(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(database, redis_url)
    plain: dict[uuid.UUID, str] = {}
    ids: dict[uuid.UUID, uuid.UUID] = {}
    for tenant, user, no in (
        (world.tenant_a, "w26ladmin", "271"),
        (world.tenant_b, "w26lother", "272"),
    ):
        h = bearer(login(client, world, user))
        _, unit, contact = _contract(client, h, no)
        plain[tenant] = f"w26-plain-{no}-{RUN}"

        async def seed(t: uuid.UUID = tenant, u: str = unit, c: str = contact) -> uuid.UUID:
            engine = create_app_engine(settings)
            try:
                async with tenant_transaction(create_session_factory(engine), t) as session:
                    prospect = Prospect(
                        tenant_id=t,
                        unit_id=uuid.UUID(u),
                        contact_id=uuid.UUID(c),
                        delete_after=local_today() + timedelta(days=365),
                    )
                    session.add(prospect)
                    await session.flush()
                    link = SelfDisclosureLink(
                        tenant_id=t,
                        prospect_id=prospect.id,
                        token=plain[t],
                        expires_at=datetime.now(UTC) + timedelta(days=14),
                    )
                    session.add(link)
                    await session.flush()
                    return link.id
            finally:
                await engine.dispose()

        ids[tenant] = asyncio.run(seed())

    def expected(t: uuid.UUID) -> str:
        return "sha256:" + hashlib.sha256(plain[t].encode()).hexdigest()

    async def token(t: uuid.UUID) -> str:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), t) as session:
                row = await session.get(SelfDisclosureLink, ids[t])
                assert row is not None
                return row.token
        finally:
            await engine.dispose()

    # Failure in A first: B is converted, A keeps its plain token for the next run.
    _failing_tenant(monkeypatch, letting_tasks, world.tenant_a)
    _run(letting_tasks.hash_self_disclosure_tokens_once(settings))
    isolated = asyncio.run(token(world.tenant_b)) == expected(world.tenant_b)
    assert asyncio.run(token(world.tenant_a)) == plain[world.tenant_a]
    monkeypatch.undo()

    first = asyncio.run(letting_tasks.hash_self_disclosure_tokens_once(settings))
    assert first["converted"] >= 1
    assert asyncio.run(token(world.tenant_a)) == expected(world.tenant_a)
    # Repetition: nothing converted, no hash of a hash.
    assert asyncio.run(letting_tasks.hash_self_disclosure_tokens_once(settings)) == {"converted": 0}
    for t in (world.tenant_a, world.tenant_b):
        assert asyncio.run(token(t)) == expected(t)
    assert isolated, ISOLATION_GAP.format(job="hash_self_disclosure_tokens_once")
