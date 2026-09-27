"""Learning examples retention (ADR 0010 addendum 27.09.2026, M7-04): tenant setting
``ai_learning_examples_retention_months`` (default 24), the daily job that deletes older
examples with a journal event per tenant, and the soft delete of a contact through an import
undo removing the contact's examples."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.ai import imports
from mhvp.ai.examples import RETENTION_EVENT
from mhvp.ai.jobs import examples_retention_once
from mhvp.ai.models import AiExample, AiTask
from mhvp.contacts.models import Contact, ContactKind
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration

S = "/api/v1/tenant/settings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ret-{RUN}", name=f"Ret {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ret2-{RUN}", name=f"Ret2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("retadmin"), display_name="retadmin", password=PASSWORD
        )
        world.users["retadmin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


@pytest.fixture(scope="module")
def world(settings: Any) -> World:
    return asyncio.run(_world(settings))


@pytest.fixture(scope="module")
def client(settings: Any) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _example(tenant_id: uuid.UUID, created_at: datetime, **features: Any) -> AiExample:
    return AiExample(
        tenant_id=tenant_id,
        task=AiTask.TICKET_RESOLUTION,
        features={"ticket_id": str(uuid.uuid4()), **features},
        result={"kind": "auskunft_erteilt"},
        created_at=created_at,
    )


async def _seed(settings: Any, tenant_id: uuid.UUID, rows: list[AiExample]) -> None:
    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            session.add_all(rows)
    finally:
        await engine.dispose()


async def _examples(settings: Any, tenant_id: uuid.UUID) -> list[AiExample]:
    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            return list(await session.scalars(select(AiExample)))
    finally:
        await engine.dispose()


async def _events(settings: Any, tenant_id: uuid.UUID) -> list[DomainEvent]:
    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            return list(
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.type == RETENTION_EVENT)
                    .order_by(DomainEvent.occurred_at)
                )
            )
    finally:
        await engine.dispose()


def test_setting_default_and_validation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "retadmin"))
    assert _ok(client.get(S, headers=h))["ai_learning_examples_retention_months"] == 24
    assert (
        client.patch(S, json={"ai_learning_examples_retention_months": 0}, headers=h).status_code
        == 422
    )
    assert (
        client.patch(S, json={"ai_learning_examples_retention_months": 121}, headers=h).status_code
        == 422
    )
    body = _ok(client.patch(S, json={"ai_learning_examples_retention_months": 6}, headers=h))
    assert body["ai_learning_examples_retention_months"] == 6


def test_retention_job_deletes_old_examples_per_tenant(
    client: TestClient, world: World, settings: Any
) -> None:
    """Tenant A keeps 6 months (set above), tenant B the default 24: an example 7 months old
    is deleted in A and kept in B; every tenant run is journaled with counts."""
    now = datetime.now(UTC)
    old, fresh = now - timedelta(days=7 * 31), now - timedelta(days=3)
    asyncio.run(
        _seed(
            settings,
            world.tenant_a,
            [_example(world.tenant_a, old), _example(world.tenant_a, fresh)],
        )
    )
    asyncio.run(_seed(settings, world.tenant_b, [_example(world.tenant_b, old)]))

    report = asyncio.run(examples_retention_once(settings))
    assert report["errors"] == []
    assert report["tenants"] >= 2
    assert report["deleted"] >= 1

    remaining_a = asyncio.run(_examples(settings, world.tenant_a))
    assert [r.created_at >= fresh - timedelta(seconds=1) for r in remaining_a] == [True]
    assert len(asyncio.run(_examples(settings, world.tenant_b))) == 1

    event = asyncio.run(_events(settings, world.tenant_a))[-1]
    assert event.payload["retention_months"] == 6
    assert event.payload["deleted"] == 1
    assert event.payload["before"] == 2
    assert event.payload["remaining"] == 1
    event_b = asyncio.run(_events(settings, world.tenant_b))[-1]
    assert event_b.payload == {**event_b.payload, "retention_months": 24, "deleted": 0}


def test_import_undo_soft_delete_removes_contact_examples(world: World, settings: Any) -> None:
    """``imports._remove("contact", id)`` soft deletes the contact and drops its examples in
    the same transaction (ADR 0010, addendum 27.09.2026)."""

    async def run() -> tuple[bool, int]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                contact = Contact(
                    tenant_id=world.tenant_a,
                    kind=ContactKind.PERSON,
                    last_name=f"Retention {RUN}",
                    display_name=f"Retention {RUN}",
                )
                session.add(contact)
                await session.flush()
                session.add(
                    _example(
                        world.tenant_a,
                        datetime.now(UTC),
                        entitaeten={"contact_id": str(contact.id)},
                    )
                )
                await session.flush()
                contact_id = contact.id
            async with tenant_transaction(factory, world.tenant_a) as session:
                await imports._remove(session, "contact", contact_id)
            async with tenant_transaction(factory, world.tenant_a) as session:
                row = await session.get(Contact, contact_id)
                left = list(
                    await session.scalars(
                        select(AiExample).where(
                            AiExample.features["entitaeten"]["contact_id"].astext == str(contact_id)
                        )
                    )
                )
                return row is not None and row.deleted_at is not None, len(left)
        finally:
            await engine.dispose()

    soft_deleted, left = asyncio.run(run())
    assert soft_deleted is True
    assert left == 0
