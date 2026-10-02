"""AI07 (GAH-206, GAH-207, GAH-202, GAH-212): outgoing webhook administration, failure counter,
objektakte timestamp header and WhatsApp status order. Own test world (prefix ai07)."""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.webhooks import (
    RETRY_SCHEDULE_SECONDS,
    WebhookDelivery,
    WebhookSubscription,
    attempt_delivery,
)
from mhvp.main import create_app
from mhvp.objektakte.webhook import sign, sign_timestamped
from mhvp.platform import services
from mhvp.sla.models import WhatsAppConfig, WhatsAppDelivery
from mhvp.workspace.models import Notification
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
RUN = "7-" + uuid.uuid4().hex[:6]
SLUG = f"ai07-{RUN}"
SECRET = f"ai07-hook-{RUN}"
WA_SECRET = f"ai07-wa-{RUN}"
OA_URL = "/api/v1/integrations/objektakte/webhook"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        objektakte_webhook_secret=SecretStr(SECRET),
        objektakte_tenant=SLUG,
        whatsapp_app_secret=SecretStr(WA_SECRET),
    )


class _W(World):
    def email(self, name: str) -> str:
        return f"ai07{name}-{RUN}@example.org"


async def _world(settings: Any) -> _W:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG, name=f"AI07 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ai07b-{RUN}", name=f"AI07 B {RUN}")
        world = _W(tenant_a=a, tenant_b=b)
        for name, tenant, role in [
            ("admin", a, "tenant_admin"),
            ("reader", a, "read_only"),
            ("other", b, "tenant_admin"),
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
def world(database: Database, redis_url: str) -> _W:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _hook(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    return _ok(
        client.post(
            "/api/v1/tenant/webhooks",
            json={"url": "http://127.0.0.1:9/a", "event_types": ["contact.updated"]},
            headers=h,
        ),
        201,
    )


def test_patch_rotate_and_test_delivery(client: TestClient, world: _W) -> None:
    h = bearer(login(client, world, "admin"))
    created = _hook(client, h)
    hid = created["id"]
    patched = _ok(
        client.patch(
            f"/api/v1/tenant/webhooks/{hid}",
            json={"url": "http://127.0.0.1:9/b", "description": "Neu"},
            headers=h,
        )
    )
    assert (patched["url"], patched["description"]) == ("http://127.0.0.1:9/b", "Neu")
    assert patched["consecutive_failures"] == 0
    bad = client.patch(f"/api/v1/tenant/webhooks/{hid}", json={"url": "ftp://x"}, headers=h)
    assert bad.status_code in (400, 422)
    long = client.patch(f"/api/v1/tenant/webhooks/{hid}", json={"url": "x" * 2001}, headers=h)
    assert long.status_code == 422

    rotated = _ok(client.post(f"/api/v1/tenant/webhooks/{hid}/rotate-secret", headers=h))
    assert rotated["secret"]
    assert rotated["secret"] != created["secret"]
    test = _ok(client.post(f"/api/v1/tenant/webhooks/{hid}/test", headers=h), 202)
    deliveries = _ok(client.get(f"/api/v1/tenant/webhooks/{hid}/deliveries", headers=h))
    assert [d["id"] for d in deliveries] == [test["delivery_id"]]

    reader = bearer(login(client, world, "reader"))
    for path in ("rotate-secret", "test"):
        assert (
            client.post(f"/api/v1/tenant/webhooks/{hid}/{path}", headers=reader).status_code == 403
        )
    other = bearer(login(client, world, "other"))
    for path in ("rotate-secret", "test"):
        assert (
            client.post(f"/api/v1/tenant/webhooks/{hid}/{path}", headers=other).status_code == 404
        )
    assert (
        client.patch(f"/api/v1/tenant/webhooks/{hid}", json={"description": "x"}, headers=other)
    ).status_code == 404


def test_settings_endpoint(client: TestClient, world: _W) -> None:
    h = bearer(login(client, world, "admin"))
    assert _ok(client.get("/api/v1/tenant/webhook-settings", headers=h)) == {
        "auto_disable_after": None,
        "objektakte_require_timestamp": False,
    }
    bad = client.put("/api/v1/tenant/webhook-settings", json={"auto_disable_after": 0}, headers=h)
    assert bad.status_code == 422
    reader = bearer(login(client, world, "reader"))
    assert client.put("/api/v1/tenant/webhook-settings", json={}, headers=reader).status_code == 403
    assert client.get("/api/v1/tenant/webhook-settings?x=1", headers=h).status_code == 422


async def _fail_final(settings: Any, tenant: uuid.UUID, delivery_id: str, code: int) -> Any:
    engine = create_app_engine(settings)
    transport = httpx.MockTransport(lambda _r: httpx.Response(code))
    try:
        factory = create_session_factory(engine)
        async with (
            httpx.AsyncClient(transport=transport) as http,
            tenant_transaction(factory, tenant) as session,
        ):
            delivery = await session.get(WebhookDelivery, uuid.UUID(delivery_id))
            assert delivery is not None
            delivery.attempts = len(RETRY_SCHEDULE_SECONDS)
            await attempt_delivery(session, delivery, client=http, allow_private=True)
            hook = await session.get(WebhookSubscription, delivery.subscription_id)
            assert hook is not None
            notes = (
                await session.scalars(select(Notification).where(Notification.entity_id == hook.id))
            ).all()
            return delivery.status.value, hook.consecutive_failures, hook.active, len(notes)
    finally:
        await engine.dispose()


def test_failure_counter_notifies_and_optional_auto_disable(
    client: TestClient, world: _W, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "admin"))
    hid = _hook(client, h)["id"]

    def test_delivery() -> str:
        return str(
            _ok(client.post(f"/api/v1/tenant/webhooks/{hid}/test", headers=h), 202)["delivery_id"]
        )

    # Default: only notify, never deactivate.
    first = asyncio.run(_fail_final(settings, world.tenant_a, test_delivery(), 500))
    assert first[:3] == ("failed", 1, True)
    assert first[3] >= 1
    listed = {x["id"]: x for x in _ok(client.get("/api/v1/tenant/webhooks", headers=h))}
    assert listed[hid]["consecutive_failures"] == 1
    assert listed[hid]["last_failure_at"]

    _ok(client.put("/api/v1/tenant/webhook-settings", json={"auto_disable_after": 2}, headers=h))
    second = asyncio.run(_fail_final(settings, world.tenant_a, test_delivery(), 500))
    assert second[:3] == ("failed", 2, False)
    listed = {x["id"]: x for x in _ok(client.get("/api/v1/tenant/webhooks", headers=h))}
    assert listed[hid]["disabled_reason"] == "consecutive_failures"

    again = _ok(client.patch(f"/api/v1/tenant/webhooks/{hid}", json={"active": True}, headers=h))
    assert (again["consecutive_failures"], again["disabled_reason"]) == (0, None)
    ok = asyncio.run(_fail_final(settings, world.tenant_a, test_delivery(), 204))
    assert ok[:3] == ("succeeded", 0, True)
    _ok(client.put("/api/v1/tenant/webhook-settings", json={"auto_disable_after": None}, headers=h))


def _oa_body(n: str) -> bytes:
    return json.dumps({"event": "object.taken_over", "object_number": n, "document": None}).encode()


def test_objektakte_timestamp_window_replay_and_size(client: TestClient, world: _W) -> None:
    h = bearer(login(client, world, "admin"))
    base = {"content-type": "application/json", "X-Objektakte-Event": "object.taken_over"}
    body = _oa_body("A7" + RUN[-4:])
    now = int(time.time())
    stamped = {
        **base,
        "X-MHVP-Timestamp": str(now),
        "X-Objektakte-Signature": sign_timestamped(SECRET, now, body),
    }
    assert _ok(client.post(OA_URL, content=body, headers=stamped))["status"] == "processed"
    # replay within the window: idempotent duplicate
    assert _ok(client.post(OA_URL, content=body, headers=stamped))["status"] == "duplicate"
    stale = now - 600
    old = {
        **base,
        "X-MHVP-Timestamp": str(stale),
        "X-Objektakte-Signature": sign_timestamped(SECRET, stale, body),
    }
    assert client.post(OA_URL, content=body, headers=old).status_code == 401
    # body-only signature together with a timestamp header is refused
    mixed = {**base, "X-MHVP-Timestamp": str(now), "X-Objektakte-Signature": sign(SECRET, body)}
    assert client.post(OA_URL, content=body, headers=mixed).status_code == 401
    # legacy without header still works while the switch is off
    legacy_body = _oa_body("B7" + RUN[-4:])
    legacy = {**base, "X-Objektakte-Signature": sign(SECRET, legacy_body)}
    assert _ok(client.post(OA_URL, content=legacy_body, headers=legacy))["status"] == "processed"
    # switch on: legacy refused
    _ok(
        client.put(
            "/api/v1/tenant/webhook-settings",
            json={"objektakte_require_timestamp": True},
            headers=h,
        )
    )
    other_body = _oa_body("C7" + RUN[-4:])
    refused = {**base, "X-Objektakte-Signature": sign(SECRET, other_body)}
    assert client.post(OA_URL, content=other_body, headers=refused).status_code == 401
    _ok(
        client.put(
            "/api/v1/tenant/webhook-settings",
            json={"objektakte_require_timestamp": False},
            headers=h,
        )
    )
    # oversized: 413 (declared length and real body)
    big = b"{" + b" " * (256 * 1024) + b"}"
    assert client.post(OA_URL, content=big, headers=legacy).status_code == 413


async def _wa_setup(settings: Any, tenant: uuid.UUID, wamid: str) -> None:
    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant) as session:
            if await session.scalar(select(WhatsAppConfig)) is None:
                session.add(WhatsAppConfig(tenant_id=tenant))
            session.add(
                WhatsAppDelivery(
                    tenant_id=tenant,
                    wa_message_id=wamid,
                    to="+490",
                    template_name="t",
                    status="sent",
                )
            )
    finally:
        await engine.dispose()


async def _wa_status(settings: Any, tenant: uuid.UUID, wamid: str) -> str:
    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant) as session:
            row = await session.scalar(
                select(WhatsAppDelivery).where(WhatsAppDelivery.wa_message_id == wamid)
            )
            assert row is not None
            return row.status
    finally:
        await engine.dispose()


def _wa_post(client: TestClient, statuses: list[dict[str, Any]]) -> None:
    body = json.dumps({"entry": [{"changes": [{"value": {"statuses": statuses}}]}]}).encode()
    sig = "sha256=" + hmac.new(WA_SECRET.encode(), body, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/v1/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert response.json()["status"] == "ok"


def test_whatsapp_status_never_goes_back(
    client: TestClient, world: _W, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    wamid = f"wamid.ai07.{RUN}"
    asyncio.run(_wa_setup(settings, world.tenant_a, wamid))
    now = str(int(time.time()))
    _wa_post(client, [{"id": wamid, "status": "bogus", "timestamp": now}])
    assert asyncio.run(_wa_status(settings, world.tenant_a, wamid)) == "sent"
    _wa_post(client, [{"id": wamid, "status": "read", "timestamp": now}])
    _wa_post(client, [{"id": wamid, "status": "delivered", "timestamp": now}])
    assert asyncio.run(_wa_status(settings, world.tenant_a, wamid)) == "read"
    wamid2 = wamid + "b"
    asyncio.run(_wa_setup(settings, world.tenant_a, wamid2))
    old = str(int(time.time()) - 8 * 24 * 3600)
    _wa_post(client, [{"id": wamid2, "status": "delivered", "timestamp": old}])
    assert asyncio.run(_wa_status(settings, world.tenant_a, wamid2)) == "sent"
