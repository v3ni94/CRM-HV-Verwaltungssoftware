"""GA04-01, GA04-03, GA04-08: ticket.commented without internal text, contract alias types
and the ticket category catalog link (trigger from the free text category)."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.contracts.routers import CONTRACT_EVENT_ALIASES
from mhvp.core.webhook_tasks import dispatch_once
from mhvp.core.webhooks import EVENT_TYPES
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a69_webhooks import (
    _ok,
    _Receiver,
    _subscribe,
    receiver,  # noqa: F401
)
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
# ruff: noqa: F811


async def _world_ga04(settings: Any) -> World:
    """Own tenant and admin (ga04-{RUN}) so this module never shares users with test_a69."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"ga04-{RUN}", name=f"GA04 Events {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("ga04admin"), display_name="ga04admin", password=PASSWORD
        )
        world.users["ga04admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world_ga04(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def test_contract_aliases_are_catalogued() -> None:
    assert set(CONTRACT_EVENT_ALIASES.values()) == {"contract.changed", "contract_payment.changed"}
    assert set(CONTRACT_EVENT_ALIASES.values()) <= set(EVENT_TYPES)
    assert "bank_transaction.imported" in EVENT_TYPES
    assert "portal_account.activated" in EVENT_TYPES


def test_ticket_commented_event_and_category_id(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    receiver: str,
) -> None:
    h = bearer(login(client, world, "ga04admin"))
    _subscribe(client, h, f"{receiver}/ga04", ["ticket.commented"])
    category = f"Kat{RUN}"
    tpl: dict[str, Any] = _ok(
        client.post(
            "/api/v1/ticket-templates",
            json={"category": category, "title": "Vorlage"},
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post("/api/v1/tickets", json={"category": category, "title": "T"}, headers=h),
        201,
    )
    assert ticket["category_id"] == str(tpl["id"])
    free = _ok(
        client.post("/api/v1/tickets", json={"category": "Freitext", "title": "F"}, headers=h),
        201,
    )
    assert free["category_id"] is None
    secret_text = f"Geheim{RUN}"
    _ok(
        client.post(
            f"/api/v1/tickets/{ticket['id']}/comments",
            json={"body": secret_text, "internal": True},
            headers=h,
        ),
        201,
    )
    asyncio.run(dispatch_once(_settings(database, redis_url)))
    got = [
        (raw, json.loads(raw))
        for p, _, raw in _Receiver.received
        if p == "/ga04" and json.loads(raw)["type"] == "ticket.commented"
    ]
    mine = [g for g in got if g[1]["entity_id"] == ticket["id"]]
    assert len(mine) == 1
    assert mine[0][1]["payload"]["internal"] is True
    assert secret_text not in mine[0][0].decode()
