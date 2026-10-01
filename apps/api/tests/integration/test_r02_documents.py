"""R02 (Q03 rest): shared mailbox distribution by token (Q03-02, M6-04), direct upload switch
(Q03-01, S12-06) and the redaction API as used by the CRM (Q03-03, M25-01)."""

import asyncio
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.documents.blobs import BlobStore
from mhvp.documents.intake import process_inbox_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_process_inbox import BUCKET, _ok, _pdf, _settings

pytestmark = pytest.mark.integration

MAILBOX = "belege@example.de"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r2a-{RUN}", name=f"R02a {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r2b-{RUN}", name=f"R02b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("r2hub", a, "tenant_admin"),
            ("r2care", a, "caretaker"),
            ("r2target", b, "tenant_admin"),
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


@pytest.fixture(scope="module")
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _h(client: TestClient, world: World, name: str) -> dict[str, str]:
    return bearer(login(client, world, name))


def _eml(to: str, sender: str, subject: str, msg_id: str, text: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = sender, to, subject, msg_id
    msg["Date"] = "Wed, 23 Sep 2026 09:00:00 +0200"
    msg.set_content(text)
    msg.add_attachment(_pdf(text), maintype="application", subtype="pdf", filename="beleg.pdf")
    return bytes(msg)


def _ingest(client: TestClient, h: dict[str, str], eml: bytes) -> dict[str, Any]:
    doc = _ok(
        client.post(
            "/api/v1/documents", files={"file": ("m.eml", eml, "message/rfc822")}, headers=h
        )
    )
    return _ok(client.post("/api/v1/mail/ingest", json={"document_id": doc["id"]}, headers=h))  # type: ignore[no-any-return]


def _run(database: Database, redis_url: str) -> dict[str, int]:
    settings = _settings(database, redis_url)

    async def go() -> dict[str, int]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(404))
        ) as http:
            return await process_inbox_once(settings, client=http, blobs=BlobStore(settings))

    return asyncio.run(go())


def _proposals(client: TestClient, h: dict[str, str]) -> list[dict[str, Any]]:
    params = {"source": "forward", "decision": "all", "page_size": 100}
    body = _ok(client.get("/api/v1/documents/intake-proposals", params=params, headers=h), 200)
    return list(body["data"])


def test_direct_upload_switch_default_off_permission_and_tenant(
    client: TestClient, world: World
) -> None:
    hub, care, target = (_h(client, world, n) for n in ("r2hub", "r2care", "r2target"))
    assert _ok(client.get("/api/v1/document-direct-upload", headers=hub), 200) == {"enabled": False}
    assert (
        client.put(
            "/api/v1/document-direct-upload", json={"enabled": True}, headers=care
        ).status_code
        == 403
    )
    assert (
        client.put("/api/v1/document-direct-upload", json={"enabled": "x"}, headers=hub).status_code
        == 422
    )
    assert _ok(
        client.put("/api/v1/document-direct-upload", json={"enabled": True}, headers=hub), 200
    )["enabled"]
    assert _ok(client.get("/api/v1/document-direct-upload", headers=hub), 200)["enabled"] is True
    assert (
        _ok(client.get("/api/v1/document-direct-upload", headers=target), 200)["enabled"] is False
    )
    # Structured entries in the settings do not break the tenant settings read.
    assert client.get("/api/v1/tenant/settings", headers=hub).status_code == 200


def test_shared_mailbox_distribution_by_token(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    hub, target = _h(client, world, "r2hub"), _h(client, world, "r2target")
    body = {"mailbox_address": MAILBOX, "allowed_senders": []}
    hub_cfg = _ok(
        client.put(
            "/api/v1/document-intake-address", json={**body, "distribute": True}, headers=hub
        ),
        200,
    )
    assert hub_cfg["distribute"] is True
    target_cfg = _ok(
        client.put(
            "/api/v1/document-intake-address",
            json={**body, "allowed_senders": ["@lieferant.de"]},
            headers=target,
        ),
        200,
    )
    assert target_cfg["distribute"] is False
    ok_sender = "Lieferant <rechnung@lieferant.de>"
    _ingest(
        client,
        hub,
        _eml(target_cfg["address"], ok_sender, "Rechnung Z", f"<r2a-{RUN}@x>", "Beleg Z"),
    )
    _ingest(
        client,
        hub,
        _eml(target_cfg["address"], "Fremd <x@spam.org>", "Spam", f"<r2b-{RUN}@x>", "Beleg S"),
    )
    _ingest(
        client,
        hub,
        _eml("belege+unbekannt@example.de", ok_sender, "Unbekannt", f"<r2c-{RUN}@x>", "Beleg U"),
    )
    before = len(_proposals(client, target))
    first = _run(database, redis_url)
    assert first["distributed"] >= 1
    after = _proposals(client, target)
    assert len(after) == before + 1
    # Idempotent: a second run hands nothing over again.
    _run(database, redis_url)
    assert len(_proposals(client, target)) == before + 1
    # The hub tenant does not process the foreign forward itself.
    assert _proposals(client, hub) == []


def test_distribution_needs_hub_switch(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    hub, target = _h(client, world, "r2hub"), _h(client, world, "r2target")
    cfg = _ok(client.get("/api/v1/document-intake-address", headers=target), 200)
    _ok(
        client.put(
            "/api/v1/document-intake-address",
            json={"mailbox_address": MAILBOX, "distribute": False},
            headers=hub,
        ),
        200,
    )
    _ingest(
        client,
        hub,
        _eml(
            cfg["address"], "Lieferant <rechnung@lieferant.de>", "Aus", f"<r2d-{RUN}@x>", "Beleg A"
        ),
    )
    before = len(_proposals(client, target))
    _run(database, redis_url)
    assert len(_proposals(client, target)) == before
