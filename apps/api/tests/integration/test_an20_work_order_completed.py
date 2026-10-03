"""AN20 (GAK-302, GAK-303): ``work_order.completed`` (section 12) is emitted exactly once on
every path to DONE: CRM step, provider portal and the automation service."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import func, select

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a55_a58_portal_attachments import _rental
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an20-a-{RUN}", name=f"AN20 A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("an20admin"), display_name="an20admin", password=PASSWORD
        )
        world.users["an20admin"] = uid
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


async def _count(settings: Any, tenant_id: uuid.UUID, order_id: str) -> dict[str, int]:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.events import DomainEvent

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            rows = (
                await session.execute(
                    select(DomainEvent.type, func.count())
                    .where(DomainEvent.entity_id == uuid.UUID(order_id))
                    .group_by(DomainEvent.type)
                )
            ).all()
            return dict(rows)
    finally:
        await engine.dispose()


def _order(c: TestClient, world: World, number: str, portal: bool = False) -> dict[str, Any]:
    h = bearer(login(c, world, "an20admin", tenant_id=world.tenant_a))
    prop_id, _ = _rental(c, h, number)
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"AN20 Betrieb {number} {RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    oid = _ok(
        c.post(
            "/api/v1/work-orders",
            json={"property_id": prop_id, "provider_contact_id": provider, "description": "Rohr"},
            headers=h,
        ),
        201,
    )["id"]
    out: dict[str, Any] = {"h": h, "oid": oid}
    if portal:
        out["pv"] = _portal_user(c, h, world, f"an20prov{number}", provider)
    for status in ("requested", "approved"):
        _ok(c.post(f"/api/v1/work-orders/{oid}/steps", json={"status": status}, headers=h))
    _ok(
        c.post(
            f"/api/v1/work-orders/{oid}/steps",
            json={"status": "scheduled", "scheduled_at": "2026-10-06T14:00:00Z"},
            headers=h,
        )
    )
    return out


def test_crm_path_emits_completed_once(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    s = _order(client, world, "871")
    h, oid = s["h"], s["oid"]
    _ok(client.post(f"/api/v1/work-orders/{oid}/steps", json={"status": "in_progress"}, headers=h))
    assert "work_order.completed" not in asyncio.run(
        _count(_settings(database, redis_url), world.tenant_a, oid)
    )
    done = {"status": "done", "completion_report": "erledigt"}
    _ok(client.post(f"/api/v1/work-orders/{oid}/steps", json=done, headers=h))
    # A repeat is refused by the flow and does not double the event.
    assert client.post(f"/api/v1/work-orders/{oid}/steps", json=done, headers=h).status_code >= 400
    counts = asyncio.run(_count(_settings(database, redis_url), world.tenant_a, oid))
    assert counts["work_order.completed"] == 1
    assert counts["work_order.done"] == 1


def test_portal_path_emits_completed_once(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    s = _order(client, world, "872", portal=True)
    oid = s["oid"]
    body = {"report": "Rohr gedichtet"}
    _ok(client.post(f"{P}/work-orders/{oid}/complete", json=body, headers=s["pv"]))
    assert (
        client.post(f"{P}/work-orders/{oid}/complete", json=body, headers=s["pv"]).status_code
        >= 400
    )
    counts = asyncio.run(_count(_settings(database, redis_url), world.tenant_a, oid))
    assert counts["work_order.done"] == 1
    assert counts["work_order.completed"] == 1


def test_automation_path_emits_completed_once(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.automation.services import _set_order_field
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    s = _order(client, world, "873")
    oid = s["oid"]
    _ok(
        client.post(
            f"/api/v1/work-orders/{oid}/steps", json={"status": "in_progress"}, headers=s["h"]
        )
    )
    settings = _settings(database, redis_url)

    async def run() -> None:
        from mhvp.automation.models import AutomationRule

        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                rule = AutomationRule(
                    tenant_id=world.tenant_a,
                    name="AN20 Regel",
                    trigger_kind="event",
                    trigger_event_type="work_order.in_progress",
                    conditions={},
                    actions=[],
                )
                session.add(rule)
                await session.flush()
                await _set_order_field(
                    session,
                    world.tenant_a,
                    rule,
                    uuid.uuid4(),
                    uuid.UUID(oid),
                    "status",
                    "done",
                    False,
                )
        finally:
            await engine.dispose()

    asyncio.run(run())
    counts = asyncio.run(_count(settings, world.tenant_a, oid))
    assert counts["work_order.done"] == 1
    assert counts["work_order.completed"] == 1
