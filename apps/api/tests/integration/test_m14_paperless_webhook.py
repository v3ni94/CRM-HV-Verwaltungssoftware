"""Paperless post-consume webhook (task A30, master prompt 11.2/11.4, M14-05) against a fake
Paperless (httpx.MockTransport, never a live server) and moto S3. Expected values by hand:
a valid HMAC delivery indexes the Paperless document exactly once (idempotent on the Paperless
id); an invalid, missing or stale signature is 401 (MHVP-HOOK-0002); the same delivery again
is a replay, 409 (MHVP-HOOK-0003); with the tenant switch off no receipt draft is created;
with the switch on a draft is created from the XRechnung without a provider call; a secret of
tenant B never signs for tenant A and A's document is invisible in B."""

import asyncio
import json
import time
from collections.abc import Iterator
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.documents import paperless_webhook as hook
from mhvp.documents import routers as documents_routers
from mhvp.documents.paperless_search import PaperlessSearch
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
W = "/api/v1/documents/webhooks/paperless"
R = "/api/v1/receipts"
BUCKET = "mhvp-paperless-hook"
SECRET_A = "a-very-long-webhook-secret-for-tenant-a"
SECRET_B = "b-very-long-webhook-secret-for-tenant-b"
SLUG_A = f"pwa-{RUN}"
SLUG_B = f"pwb-{RUN}"


def _xrechnung() -> bytes:
    from tests.unit.test_m14_einvoice import UBL

    return UBL.replace("RE-2026-042", f"RE-PW-{RUN}").encode()


class FakePaperless:
    """Only the file download of M31's read-only client is needed here."""

    def __init__(self) -> None:
        self.token = "ppl-token-secret"
        self.downloads: list[int] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != f"Token {self.token}":
            return httpx.Response(401, json={"detail": "invalid token"})
        parts = request.url.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "documents"] and parts[3] == "download":
            doc_id = int(parts[2])
            self.downloads.append(doc_id)
            if doc_id == 404:
                return httpx.Response(404)
            return httpx.Response(
                200,
                content=_xrechnung(),
                headers={
                    "content-type": "application/xml",
                    "content-disposition": f'attachment; filename="rechnung-{doc_id}.xml"',
                },
            )
        return httpx.Response(404)


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        ai_inline=True,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG_A, name=f"Paperless A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=SLUG_B, name=f"Paperless B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("pwadmin", a), ("pwother", b)]:
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
def fake() -> FakePaperless:
    return FakePaperless()


@pytest.fixture
def client(
    database: Database, redis_url: str, fake: FakePaperless, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    class Patched(PaperlessSearch):
        def __init__(self, base_url: str, token: str, **kwargs: Any) -> None:
            super().__init__(
                base_url,
                token,
                client=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
                **kwargs,
            )

    monkeypatch.setattr(documents_routers, "PaperlessSearch", Patched)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _configure(
    client: TestClient, h: dict[str, str], fake: FakePaperless, *, secret: str, auto: bool
) -> Any:
    return _ok(
        client.put(
            "/api/v1/dms-connections/paperless",
            json={
                "enabled": True,
                "base_url": "https://paperless.example.internal",
                "secret": fake.token,
                "options": {},
                "webhook_secret": secret,
                "auto_receipt_intake": auto,
            },
            headers=h,
        )
    )


def _deliver(
    client: TestClient,
    tenant_key: str,
    secret: str,
    payload: dict[str, Any],
    *,
    timestamp: int | None = None,
    signature: str | None = None,
    via_path: bool = False,
) -> Any:
    raw = json.dumps(payload).encode()
    ts = timestamp if timestamp is not None else int(time.time())
    headers = {
        "Content-Type": "application/json",
        hook.TIMESTAMP_HEADER: str(ts),
        hook.SIGNATURE_HEADER: signature or hook.sign(secret, ts, raw),
    }
    if via_path:
        return client.post(f"{W}/{tenant_key}", content=raw, headers=headers)
    headers[hook.TENANT_HEADER] = tenant_key
    return client.post(W, content=raw, headers=headers)


def test_valid_signature_indexes_once_and_needs_no_login(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "pwadmin", world.tenant_a))
    out = _configure(client, h, fake, secret=SECRET_A, auto=False)
    assert out["has_webhook_secret"] is True
    assert out["auto_receipt_intake"] is False
    assert "webhook_secret" not in out  # write only

    first = _ok(_deliver(client, SLUG_A, SECRET_A, {"document_id": 501, "title": "Rechnung 501"}))
    assert first["status"] == "indexed"
    assert first["receipt_intake"] == "off"
    doc = _ok(client.get(f"/api/v1/documents/{first['document_id']}", headers=h))
    assert doc["title"] == "Rechnung 501"
    assert doc["filename"] == "rechnung-501.xml"
    assert doc["source"] == "import"
    assert fake.downloads == [501]

    # Same Paperless document again (new timestamp, so no replay): idempotent, no second file.
    again = _ok(
        _deliver(
            client,
            str(world.tenant_a),
            SECRET_A,
            {"document_id": 501},
            via_path=True,
            timestamp=int(time.time()) + 1,
        )
    )
    assert again["status"] == "already_indexed"
    assert again["document_id"] == first["document_id"]
    assert fake.downloads == [501]


def test_invalid_missing_or_stale_signature_is_401(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "pwadmin", world.tenant_a))
    _configure(client, h, fake, secret=SECRET_A, auto=False)
    wrong = _deliver(client, SLUG_A, "not-the-secret-of-tenant-a", {"document_id": 502})
    assert wrong.status_code == 401
    assert "MHVP-HOOK-0002" in wrong.text
    missing = client.post(W, content=b"{}", headers={hook.TENANT_HEADER: SLUG_A})
    assert missing.status_code == 401
    stale = _deliver(
        client, SLUG_A, SECRET_A, {"document_id": 502}, timestamp=int(time.time()) - 3600
    )
    assert stale.status_code == 401
    unknown_tenant = _deliver(client, f"nobody-{RUN}", SECRET_A, {"document_id": 502})
    assert unknown_tenant.status_code == 401
    assert fake.downloads == []
    docs = _ok(client.get("/api/v1/documents", params={"q": "502"}, headers=h))
    assert all(
        d.get("filename") != "rechnung-502.xml"
        for d in (docs["items"] if isinstance(docs, dict) else docs)
    )


def test_replay_of_the_same_delivery_is_409(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "pwadmin", world.tenant_a))
    _configure(client, h, fake, secret=SECRET_A, auto=False)
    ts = int(time.time())
    raw = json.dumps({"document_id": 503}).encode()
    sig = hook.sign(SECRET_A, ts, raw)
    _ok(_deliver(client, SLUG_A, SECRET_A, {"document_id": 503}, timestamp=ts, signature=sig))
    replay = _deliver(client, SLUG_A, SECRET_A, {"document_id": 503}, timestamp=ts, signature=sig)
    assert replay.status_code == 409
    assert "MHVP-HOOK-0003" in replay.text
    assert fake.downloads == [503]


def _drafts_for(client: TestClient, h: dict[str, str], document_id: str) -> list[Any]:
    rows = _ok(client.get(f"{R}/drafts", headers=h))["items"]
    return [d for d in rows if d["document_id"] == document_id]


def test_switch_off_creates_no_draft_and_switch_on_creates_one(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "pwadmin", world.tenant_a))
    _configure(client, h, fake, secret=SECRET_A, auto=False)
    off = _ok(_deliver(client, SLUG_A, SECRET_A, {"document_id": 504}))
    assert off["receipt_intake"] == "off"
    assert _drafts_for(client, h, off["document_id"]) == []

    on_cfg = _configure(client, h, fake, secret=SECRET_A, auto=True)
    assert on_cfg["auto_receipt_intake"] is True
    on = _ok(_deliver(client, SLUG_A, SECRET_A, {"document_id": 505}))
    assert on["receipt_intake"] == "queued"
    drafts = _drafts_for(client, h, on["document_id"])
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["source"] == "paperless"
    assert draft["status"] == "proposed"  # XRechnung: deterministic, no provider call
    assert draft["task_run_id"] is None
    assert draft["fields"]["invoice_number"]["value"] == f"RE-PW-{RUN}"

    # Already indexed documents are not extracted again on a repeated delivery.
    repeat = _ok(
        _deliver(client, SLUG_A, SECRET_A, {"document_id": 505}, timestamp=int(time.time()) + 1)
    )
    assert repeat["status"] == "already_indexed"
    assert repeat["receipt_intake"] == "off"
    assert len(_drafts_for(client, h, on["document_id"])) == 1
    _configure(client, h, fake, secret=SECRET_A, auto=False)


def test_tenant_separation(client: TestClient, world: World, fake: FakePaperless) -> None:
    ha = bearer(login(client, world, "pwadmin", world.tenant_a))
    hb = bearer(login(client, world, "pwother", world.tenant_b))
    _configure(client, ha, fake, secret=SECRET_A, auto=False)
    _configure(client, hb, fake, secret=SECRET_B, auto=False)
    # B's secret does not sign for A and vice versa.
    assert _deliver(client, SLUG_A, SECRET_B, {"document_id": 506}).status_code == 401
    assert _deliver(client, SLUG_B, SECRET_A, {"document_id": 506}).status_code == 401
    a_doc = _ok(_deliver(client, SLUG_A, SECRET_A, {"document_id": 506}))
    assert client.get(f"/api/v1/documents/{a_doc['document_id']}", headers=hb).status_code == 404
    # The same Paperless id in B is B's own document (index is per tenant).
    b_doc = _ok(_deliver(client, SLUG_B, SECRET_B, {"document_id": 506}))
    assert b_doc["status"] == "indexed"
    assert b_doc["document_id"] != a_doc["document_id"]
    assert (
        _ok(client.get(f"/api/v1/documents/{b_doc['document_id']}", headers=hb))["id"]
        == b_doc["document_id"]
    )


def test_oversized_body_is_413_before_any_check(client: TestClient, world: World) -> None:
    """Sicherheitsreview 1.22, Befund 2: a body above the limit is refused before the tenant
    or the signature is looked at, with the declared length as well as with the read length."""
    big = b"{" + b" " * hook.MAX_BODY_BYTES + b"}"
    declared = client.post(
        W,
        content=big,
        headers={"Content-Type": "application/json", hook.TENANT_HEADER: SLUG_A},
    )
    assert declared.status_code == 413, declared.text
    assert declared.json()["code"] == "MHVP-HOOK-0004"
    # A chunked delivery without Content-Length is measured after reading.
    chunked = client.post(
        W,
        content=iter([big[: len(big) // 2], big[len(big) // 2 :]]),
        headers={"Content-Type": "application/json", hook.TENANT_HEADER: SLUG_A},
    )
    assert chunked.status_code == 413, chunked.text
    # A small body still runs into the signature check, not the size check.
    small = client.post(W, content=b"{}", headers={hook.TENANT_HEADER: SLUG_A})
    assert small.status_code == 401
