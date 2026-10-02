"""AF10 (wave 17): GAB-07 central document.created, GAB-04 Paperless full text after the
mirror, GAB-11 tenant switch invoice_intake_auto (extract_invoice as proposal, default off),
GAE-35 trash aware objektakte import and tenant export. Paperless only through the existing
adapter with an httpx MockTransport fake; no network."""

import asyncio
import io
import uuid
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent
from mhvp.documents import intake, tasks, trash
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    DmsConnection,
    Document,
    DocumentMirror,
    DocumentSource,
    MirrorStatus,
    StorageKind,
    TextStatus,
)
from mhvp.documents.services import store_document
from mhvp.main import create_app
from mhvp.objektakte import objektakte_import as oi
from mhvp.platform import services
from mhvp.platform.models import Tenant
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _property

pytestmark = pytest.mark.integration
BUCKET = "mhvp-af10-docs"
P = "/api/v1/documents/intake-proposals"
SWITCH = "/api/v1/document-invoice-intake-auto"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=200_000,
        ai_inline=True,
    )


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af10a-{RUN}", name=f"AF10 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af10b-{RUN}", name=f"AF10 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af10admin", a, "tenant_admin"),
            ("af10view", a, "read_only"),
            ("af10other", b, "tenant_admin"),
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    for i, line in enumerate(lines):
        canvas.drawString(72, 720 - 16 * i, line)
    canvas.save()
    return buffer.getvalue()


def _upload(client: TestClient, h: dict[str, str], name: str, *lines: str) -> str:
    doc = _ok(
        client.post(
            "/api/v1/documents", files={"file": (name, _pdf(*lines), "application/pdf")}, headers=h
        ),
        201,
    )
    return str(doc["id"])


def _db(
    database: Database,
    redis_url: str,
    tenant_id: uuid.UUID,
    work: Callable[[Any], Coroutine[Any, Any, Any]],
) -> Any:
    settings = _settings(database, redis_url)

    async def go() -> Any:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _created_events(
    database: Database, redis_url: str, tenant: uuid.UUID, doc_id: str
) -> list[dict[str, Any]]:
    async def work(session: Any) -> list[dict[str, Any]]:
        rows = await session.scalars(
            select(DomainEvent).where(
                DomainEvent.type == "document.created", DomainEvent.entity_id == uuid.UUID(doc_id)
            )
        )
        return [dict(r.payload) for r in rows.all()]

    return _db(database, redis_url, tenant, work)  # type: ignore[no-any-return]


# GAB-07 ---------------------------------------------------------------------------------


def test_document_created_once_per_source(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "af10admin"))
    uploaded = _upload(client, h, "Notiz.pdf", "Notiz AF10")
    events = _created_events(database, redis_url, world.tenant_a, uploaded)
    assert len(events) == 1, "no duplicate emission by the router"
    assert events[0]["source"] == "upload"

    settings = _settings(database, redis_url)

    async def generated(session: Any) -> str:
        document = await store_document(
            session,
            BlobStore(settings),
            tenant_id=world.tenant_a,
            data=b"%PDF-1.4 generated",
            title="Brief AF10",
            filename="brief.pdf",
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[],
            created_by=None,
            event_payload={"letter": "af10"},
        )
        return str(document.id)

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        gen_id = _db(database, redis_url, world.tenant_a, generated)
    events = _created_events(database, redis_url, world.tenant_a, gen_id)
    assert len(events) == 1
    assert events[0]["source"] == "generated"
    assert events[0]["letter"] == "af10"
    # Tenant separation: the other tenant sees no event of tenant A.
    assert _created_events(database, redis_url, world.tenant_b, gen_id) == []


# GAB-04 ---------------------------------------------------------------------------------


def test_paperless_full_text_is_taken_over_after_the_mirror(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "af10admin"))
    doc_id = uuid.UUID(_upload(client, h, "Scan.pdf", "Scan"))
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/tasks/":
            return httpx.Response(200, json=[{"status": "SUCCESS", "related_document": 77}])
        if request.url.path == "/api/documents/77/" and request.method == "GET":
            return httpx.Response(200, json={"id": 77, "content": "Rechnung 4711 OCR Volltext"})
        return httpx.Response(200, json={"results": [{"id": 1}], "id": 1})

    async def prepare(session: Any) -> None:
        document = await session.get(Document, doc_id)
        document.ocr_text, document.text_status = None, TextStatus.PENDING
        session.add(
            DmsConnection(
                tenant_id=world.tenant_a,
                kind=StorageKind.PAPERLESS,
                enabled=True,
                base_url="http://paperless.invalid",
                secret="token",
                options={},
            )
        )
        session.add(
            DocumentMirror(
                tenant_id=world.tenant_a,
                document_id=doc_id,
                kind=StorageKind.PAPERLESS,
                status=MirrorStatus.SUBMITTED,
                external_ref="task:af10",
            )
        )

    _db(database, redis_url, world.tenant_a, prepare)
    settings = _settings(database, redis_url)

    async def run(session: Any) -> None:
        tenant = await session.get(Tenant, world.tenant_a)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await tasks.mirror_tenant(session, tenant, BlobStore(settings), http)

    _db(database, redis_url, world.tenant_a, run)

    async def check(session: Any) -> tuple[Any, ...]:
        document = await session.get(Document, doc_id)
        mirror = await session.scalar(
            select(DocumentMirror).where(DocumentMirror.document_id == doc_id)
        )
        return document.text_status, document.ocr_text, mirror.status, mirror.external_ref

    status, text, mirror_status, ref = _db(database, redis_url, world.tenant_a, check)
    assert (status, mirror_status, ref) == (TextStatus.EXTRACTED, MirrorStatus.DONE, "77")
    assert text == "Rechnung 4711 OCR Volltext"
    assert "GET /api/documents/77/" in calls
    # Searchable through the generated search vector.
    found = _ok(client.get("/api/v1/documents", params={"q": "Volltext"}, headers=h))
    assert str(doc_id) in [d["id"] for d in found["items"]]

    async def cleanup(session: Any) -> None:
        connection = await session.scalar(select(DmsConnection))
        connection.enabled = False

    _db(database, redis_url, world.tenant_a, cleanup)


# GAB-11 ---------------------------------------------------------------------------------


def _propose(database: Database, redis_url: str, tenant: uuid.UUID, doc_id: str) -> None:
    async def work(session: Any) -> None:
        document = await session.get(Document, uuid.UUID(doc_id))
        result = await intake.analyse(session, tenant, document, source="mailbox")
        assert await intake.propose(session, tenant, document, result) is not None

    _db(database, redis_url, tenant, work)


def _drafts(client: TestClient, h: dict[str, str], doc_id: str) -> list[Any]:
    rows = _ok(client.get("/api/v1/receipts/drafts", headers=h))["items"]
    return [d for d in rows if d["document_id"] == doc_id]


def test_invoice_intake_switch(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "af10admin"))
    hv = bearer(login(client, world, "af10view"))
    hb = bearer(login(client, world, "af10other", world.tenant_b))
    assert _ok(client.get(SWITCH, headers=h)) == {"enabled": False}
    assert client.put(SWITCH, json={"enabled": True}, headers=hv).status_code == 403
    assert client.put(SWITCH, json={"enabled": "ja"}, headers=h).status_code == 422
    assert client.put(SWITCH, json={"enabled": True, "x": 1}, headers=h).status_code == 422

    prop = _property(client, h, "810", "rental")

    def accept(doc_id: str) -> dict[str, Any]:
        _propose(database, redis_url, world.tenant_a, doc_id)
        rows = [p for p in _ok(client.get(P, headers=h))["data"] if p["document_id"] == doc_id]
        out = _ok(
            client.post(f"{P}/{rows[0]['id']}/accept", json={"property_id": prop["id"]}, headers=h)
        )
        return {f["kind"]: f for f in out["final"]["followups"]}

    # Off (default): the invoice hint stays proposed, no receipt draft.
    off_doc = _upload(client, h, "Rechnung Aus.pdf", "Rechnung Nr. AF10-1", "Betrag 100,00 EUR")
    off = accept(off_doc)
    assert off["invoice"]["status"] == "proposed"
    assert "receipt_intake" not in off["invoice"]
    assert _drafts(client, h, off_doc) == []

    assert _ok(client.put(SWITCH, json={"enabled": True}, headers=h)) == {"enabled": True}
    assert _ok(client.get(SWITCH, headers=h)) == {"enabled": True}
    assert _ok(client.get(SWITCH, headers=hb)) == {"enabled": False}, "per tenant"

    # On: the receipt extraction starts as a proposal (draft, nothing posted or approved).
    on_doc = _upload(client, h, "Rechnung Ein.pdf", "Rechnung Nr. AF10-2", "Betrag 200,00 EUR")
    on = accept(on_doc)
    assert on["invoice"]["status"] == "confirmed"
    assert on["invoice"]["receipt_intake"] == "started"
    drafts = _drafts(client, h, on_doc)
    assert len(drafts) == 1
    assert drafts[0]["source"] == "upload"
    assert drafts[0]["status"] in ("extracting", "proposed", "failed")
    _ok(client.put(SWITCH, json={"enabled": False}, headers=h))


# GAE-35 ---------------------------------------------------------------------------------


def test_reimport_restores_a_trashed_document(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "af10admin"))
    doc_id = uuid.UUID(_upload(client, h, "Objektakte.pdf", "Objektakte"))
    row = {"id": f"af10-{RUN}", "current_name": "Akte.pdf", "status": "registered"}

    async def trash_it(session: Any) -> None:
        document = await session.get(Document, doc_id)
        document.source_system, document.source_id = oi.SOURCE_SYSTEM, row["id"]
        await trash.move_to_trash(
            session, document, tenant_id=world.tenant_a, actor_user_id=None, days=30
        )

    _db(database, redis_url, world.tenant_a, trash_it)
    assert client.get(f"/api/v1/documents/{doc_id}", headers=h).status_code == 404

    async def reimport(session: Any) -> dict[str, uuid.UUID]:
        result = oi.ImportResult()
        return await oi._import_documents(
            session,
            world.tenant_a,
            [row],
            {},
            {},
            {},
            {},
            lambda kind: None,
            lambda kind: None,
            result,
        )

    mapping = _db(database, redis_url, world.tenant_a, reimport)
    assert mapping[row["id"]] == doc_id, "same row, no uq_document_source conflict"
    assert _ok(client.get(f"/api/v1/documents/{doc_id}", headers=h))["id"] == str(doc_id)

    async def restored(session: Any) -> list[Any]:
        rows = await session.scalars(
            select(DomainEvent).where(
                DomainEvent.type == trash.EVENT_RESTORED, DomainEvent.entity_id == doc_id
            )
        )
        return [r.payload for r in rows.all()]

    events = _db(database, redis_url, world.tenant_a, restored)
    assert len(events) == 1
    assert events[0]["reimport"] is True
