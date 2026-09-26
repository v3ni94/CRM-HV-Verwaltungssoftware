"""Upload of CRM documents to objektakte (26.09.2026, docs/integrations/objektakte.md).

objektakte is never called: the job talks to an ``httpx.MockTransport`` that answers in the shape
of endpoints 6 and 7. Covers the routing (exactly one property through a property, unit or ticket
link, switch, tenant), that a routed document gets no Paperless mirror, the job states pending,
submitted, done and failed, the 503 postponement, a duplicate in objektakte, the filing endpoint
and the webhook ``document.filed`` with ``crm_document_id`` linking the existing CRM document."""

import asyncio
import json
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink, DocumentMirror
from mhvp.main import create_app
from mhvp.objektakte import upload as objektakte_upload
from mhvp.objektakte.dms_models import ObjektakteUpload
from mhvp.objektakte.remote import ObjektakteClient
from mhvp.objektakte.webhook import sign
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _unit

pytestmark = pytest.mark.integration
BASE = "/api/v1/integrations/objektakte"
API_URL = "https://uebernahme.example.test/api/crm/v1/"
TOKEN = "test-token-up-" + RUN
SECRET = "test-webhook-up-" + RUN
SLUG = f"oakup-{RUN}"
PDF = b"%PDF-1.4 Testinhalt Upload"
BUCKET = "mhvp-docs-up"


def _configured(database: Database, redis_url: str, **overrides: object) -> Any:
    values: dict[str, object] = {
        "objektakte_api_url": API_URL,
        "objektakte_api_token": SecretStr(TOKEN),
        "objektakte_webhook_secret": SecretStr(SECRET),
        "objektakte_tenant": SLUG,
        "objektakte_upload_enabled": True,
        "s3_endpoint_url": "https://s3.us-east-1.amazonaws.com",
        "s3_access_key_id": SecretStr("testing"),
        "s3_secret_access_key": SecretStr("testing"),
        "s3_bucket": BUCKET,
    }
    values.update(overrides)
    return base_settings(database, redis_url, **values)


def _state(doc_id: int, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": doc_id,
        "title": "Rechnung Hausmeister",
        "doc_type": "rechnung",
        "category": "03_Buchhaltung",
        "subfolder": "03_2026",
        "status": status,
        "drive_file_id": "drive-501" if status == "filed" else None,
        "drive_url": "https://drive.google.com/file/d/drive-501/view"
        if status == "filed"
        else None,
        "sha256": "c" * 64,
        "filed_at": "2026-09-26T10:00:00+00:00" if status == "filed" else None,
        "mime_type": "application/pdf",
        "size_bytes": len(PDF),
        "crm_document_id": None,
        "paperless_id": 9001 if status == "filed" else None,
        "object_number": "317",
        "open_review_cases": 0,
        "deleted": False,
        "duplicate_of": None,
        **extra,
    }


class FakeObjektakte:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []
        self.post_status = 202
        self.post_body: dict[str, Any] = _state(501, "registered")
        self.get_body: dict[str, Any] = _state(501, "filed")

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        path = request.url.path.removeprefix("/api/crm/v1/")
        if request.method == "POST" and path.endswith("/documents/"):
            body = request.read().decode("latin-1")
            self.posts.append({"path": path, "body": body})
            if self.post_status >= 400:
                return httpx.Response(self.post_status, json={"error": "abgelehnt im Test"})
            crm_id = body.split('name="crm_document_id"')[1].split("\r\n\r\n")[1].split("\r\n")[0]
            return httpx.Response(
                self.post_status, json={**self.post_body, "crm_document_id": crm_id}
            )
        if request.method == "GET" and path.startswith("documents/"):
            self.gets.append(path)
            return httpx.Response(200, json=self.get_body)
        return httpx.Response(404, json={"error": "Nicht gefunden"})


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG, name=f"Upload {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"oakupb-{RUN}", name=f"Up B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("upadmin", a), ("upother", b)):
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
    return asyncio.run(_world(_configured(database, redis_url)))


@pytest.fixture
def fake() -> FakeObjektakte:
    return FakeObjektakte()


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def make_client(
    database: Database, redis_url: str, s3: None
) -> Iterator[Callable[..., TestClient]]:
    opened: list[TestClient] = []

    def _make(**overrides: object) -> TestClient:
        client = TestClient(create_app(_configured(database, redis_url, **overrides)))
        client.__enter__()
        opened.append(client)
        return client

    yield _make
    for client in opened:
        client.__exit__(None, None, None)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(client: TestClient, h: dict[str, str], number: str) -> str:
    found = _ok(client.get("/api/v1/properties", params={"page_size": 200}, headers=h))
    for item in found["items"]:
        if item["number"] == number:
            return str(item["id"])
    body = {"number": number, "name": f"Haus {number}", "management_type": "hoa"}
    return str(_ok(client.post("/api/v1/properties", json=body, headers=h), 201)["id"])


def _paperless_on(client: TestClient, h: dict[str, str]) -> None:
    body = {"enabled": True, "base_url": "https://dms.example.org", "secret": "paperless-token"}
    _ok(client.put("/api/v1/dms-connections/paperless", json=body, headers=h))


def _upload(client: TestClient, h: dict[str, str], links: list[dict[str, str]]) -> str:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("rechnung.pdf", PDF, "application/pdf")},
        data={"title": "Rechnung Hausmeister", "links": json.dumps(links)},
        headers=h,
    )
    return str(_ok(response, 201)["id"])


def _link(entity_type: str, entity_id: str) -> dict[str, str]:
    return {"entity_type": entity_type, "entity_id": entity_id, "role": "original"}


async def _rows(settings: Any, tenant_id: uuid.UUID, document_id: str) -> dict[str, Any]:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            doc_id = uuid.UUID(document_id)
            upload = await session.scalar(
                select(ObjektakteUpload).where(ObjektakteUpload.document_id == doc_id)
            )
            mirrors = (
                await session.scalars(
                    select(DocumentMirror.kind).where(DocumentMirror.document_id == doc_id)
                )
            ).all()
            document = await session.get(Document, doc_id)
            links = (
                await session.scalars(
                    select(DocumentLink.entity_type).where(DocumentLink.document_id == doc_id)
                )
            ).all()
            return {
                "upload": None
                if upload is None
                else {
                    "status": upload.status,
                    "hints": upload.hints,
                    "object_number": upload.object_number,
                    "objektakte_document_id": upload.objektakte_document_id,
                    "attempts": upload.attempts,
                    "last_error": upload.last_error,
                    "next_attempt_at": upload.next_attempt_at,
                    "remote": upload.remote,
                },
                "mirrors": sorted(m.value for m in mirrors),
                "source_meta": document.source_meta if document else None,
                "links": sorted(links),
            }
    finally:
        await engine.dispose()


async def _run_job(settings: Any, tenant_id: uuid.UUID, fake: FakeObjektakte, now: datetime) -> int:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        client = ObjektakteClient(API_URL, TOKEN, transport=httpx.MockTransport(fake.handler))
        async with client, tenant_transaction(factory, tenant_id) as session:
            return await objektakte_upload.process_tenant(session, client, BlobStore(settings), now)
    finally:
        await engine.dispose()


def test_routing_skips_crm_mirrors_and_job_files_document(
    make_client: Callable[..., TestClient],
    world: World,
    fake: FakeObjektakte,
    database: Database,
    redis_url: str,
) -> None:
    settings = _configured(database, redis_url)
    client = make_client()
    h = bearer(login(client, world, "upadmin"))
    _paperless_on(client, h)
    prop = _property(client, h, "317")
    unit = _unit(client, h, prop, "7")
    doc_id = _upload(client, h, [_link("unit", unit)])

    rows = asyncio.run(_rows(settings, world.tenant_a, doc_id))
    assert rows["upload"]["status"] == "pending"
    assert rows["upload"]["object_number"] == "317"
    assert rows["upload"]["hints"] == {"title": "Rechnung Hausmeister", "unit_labels": ["WE 7"]}
    assert "paperless" not in rows["mirrors"]
    filing = _ok(client.get(f"{BASE}/documents/{doc_id}/filing", headers=h))
    assert filing["routed"] is True
    assert filing["status"] == "pending"

    now = datetime.now(UTC) + timedelta(seconds=5)
    assert asyncio.run(_run_job(settings, world.tenant_a, fake, now)) == 1
    assert len(fake.posts) == 1
    assert fake.posts[0]["path"] == "objects/317/documents/"
    assert f"\r\n\r\n{doc_id}\r\n" in fake.posts[0]["body"]
    assert '"unit_labels": ["WE 7"]' in fake.posts[0]["body"]
    rows = asyncio.run(_rows(settings, world.tenant_a, doc_id))
    assert rows["upload"]["status"] == "submitted"
    assert rows["upload"]["objektakte_document_id"] == 501

    # Not due yet: nothing happens; after the poll interval the filed state is taken over
    assert asyncio.run(_run_job(settings, world.tenant_a, fake, now)) == 0
    later = now + timedelta(seconds=objektakte_upload.POLL_SECONDS + 1)
    assert asyncio.run(_run_job(settings, world.tenant_a, fake, later)) == 1
    assert fake.gets == ["documents/501/"]
    rows = asyncio.run(_rows(settings, world.tenant_a, doc_id))
    assert rows["upload"]["status"] == "done"
    assert rows["upload"]["last_error"] is None
    oak = rows["source_meta"]["objektakte"]
    assert oak["drive_file_id"] == "drive-501"
    assert oak["paperless_id"] == 9001
    assert oak["category"] == "03_Buchhaltung"
    assert "property" in rows["links"]
    filing = _ok(client.get(f"{BASE}/documents/{doc_id}/filing", headers=h))
    assert filing["status"] == "done"
    assert filing["paperless_id"] == 9001
    assert filing["drive_url"] == "https://drive.google.com/file/d/drive-501/view"


def test_not_routed_without_single_property_or_switch(
    make_client: Callable[..., TestClient], world: World, database: Database, redis_url: str
) -> None:
    settings = _configured(database, redis_url)
    client = make_client()
    h = bearer(login(client, world, "upadmin"))
    _paperless_on(client, h)
    first, second = _property(client, h, "317"), _property(client, h, "318")
    two = _upload(client, h, [_link("property", first), _link("property", second)])
    none = _upload(client, h, [])
    off_client = make_client(objektakte_upload_enabled=False)
    off = _upload(off_client, h, [_link("property", first)])
    for doc_id in (two, none, off):
        rows = asyncio.run(_rows(settings, world.tenant_a, doc_id))
        assert rows["upload"] is None
        assert "paperless" in rows["mirrors"], doc_id
        filing = _ok(client.get(f"{BASE}/documents/{doc_id}/filing", headers=h))
        assert filing == {"routed": False, "document_id": doc_id}

    # Another tenant than OBJEKTAKTE_TENANT never uploads
    hb = bearer(login(client, world, "upother"))
    other_prop = _property(client, hb, "317")
    other = _upload(client, hb, [_link("property", other_prop)])
    assert asyncio.run(_rows(settings, world.tenant_b, other))["upload"] is None


def test_deferred_rejected_and_duplicate(
    make_client: Callable[..., TestClient],
    world: World,
    fake: FakeObjektakte,
    database: Database,
    redis_url: str,
) -> None:
    settings = _configured(database, redis_url)
    client = make_client()
    h = bearer(login(client, world, "upadmin"))
    prop = _property(client, h, "317")
    now = datetime.now(UTC) + timedelta(seconds=5)

    fake.post_status = 503
    deferred = _upload(client, h, [_link("property", prop)])
    asyncio.run(_run_job(settings, world.tenant_a, fake, now))
    row = asyncio.run(_rows(settings, world.tenant_a, deferred))["upload"]
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    assert row["next_attempt_at"] >= now + timedelta(seconds=objektakte_upload.DEFER_SECONDS - 1)

    fake.post_status = 409
    rejected = _upload(client, h, [_link("property", prop)])
    asyncio.run(_run_job(settings, world.tenant_a, fake, now))
    row = asyncio.run(_rows(settings, world.tenant_a, rejected))["upload"]
    assert row["status"] == "failed"
    assert "abgelehnt im Test" in row["last_error"]
    # Manual retry through the existing mirror action
    _ok(client.post(f"/api/v1/documents/{rejected}/mirror", headers=h))
    assert asyncio.run(_rows(settings, world.tenant_a, rejected))["upload"]["status"] == "pending"

    fake.post_status = 200
    fake.post_body = _state(
        502, "duplicate", sha256="d" * 64, duplicate_of={**_state(400, "filed"), "id": 400}
    )
    duplicate = _upload(client, h, [_link("property", prop)])
    later = now + timedelta(seconds=objektakte_upload.DEFER_SECONDS + 5)
    asyncio.run(_run_job(settings, world.tenant_a, fake, later))
    rows = asyncio.run(_rows(settings, world.tenant_a, duplicate))
    assert rows["upload"]["status"] == "done"
    assert rows["upload"]["remote"]["duplicate_of"] == 400
    assert rows["source_meta"]["objektakte"]["objektakte_document_id"] == 400


def test_webhook_with_crm_document_id_links_existing_document(
    make_client: Callable[..., TestClient], world: World, database: Database, redis_url: str
) -> None:
    settings = _configured(database, redis_url)
    client = make_client()
    h = bearer(login(client, world, "upadmin"))
    prop = _property(client, h, "317")
    doc_id = _upload(client, h, [_link("property", prop)])
    payload = {
        "event": "document.filed",
        "occurred_at": "2026-09-26T10:00:00+00:00",
        "object_number": "317",
        # a different hash than the CRM original (objektakte may store a converted file)
        "document": {**_state(777, "filed"), "sha256": "e" * 64, "crm_document_id": doc_id},
    }
    raw = json.dumps(payload).encode()
    response = client.post(
        f"{BASE}/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Objektakte-Signature": sign(SECRET, raw),
            "X-Objektakte-Event": "document.filed",
        },
    )
    body = _ok(response)
    assert body["document_id"] == doc_id
    assert body["outcome"] in ("linked", "updated")
    rows = asyncio.run(_rows(settings, world.tenant_a, doc_id))
    assert rows["upload"]["status"] == "done"
    assert rows["source_meta"]["objektakte"]["objektakte_document_id"] == 777
    assert rows["source_meta"]["objektakte"]["paperless_id"] == 9001
