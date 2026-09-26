"""A42 (11.4, 15.1): document inbox job `mhvp.documents.process_inbox` against fake Paperless
and Drive endpoints plus a mailbox attachment; proposals only, watermark idempotent, accept
links, reject learns, permissions and tenant separation."""

import asyncio
import io
import json
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas

from mhvp.core.config import Settings
from mhvp.documents.blobs import BlobStore
from mhvp.documents.intake import process_inbox_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-inbox"
P = "/api/v1/documents/intake-proposals"
# Unique per run so connections of other test tenants (same database) never hit this fake.
PAPERLESS_URL = f"https://dms-ib-{RUN}.example.org"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=200_000,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ib-{RUN}", name=f"Eingang {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ic-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ibadmin", a, "tenant_admin"),
            ("ibcaretaker", a, "caretaker"),
            ("ibother", b, "tenant_admin"),
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


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 720, text)
    canvas.save()
    return buffer.getvalue()


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _eml(sender: str, subject: str, body: str, msg_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Absender <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Wed, 23 Sep 2026 09:00:00 +0200"
    msg.set_content(body)
    msg.add_attachment(
        _pdf(f"Kostenvoranschlag {body}"),
        maintype="application",
        subtype="pdf",
        filename="kva.pdf",
    )
    return bytes(msg)


class FakeInbox:
    """Paperless listing and download plus a Drive inbox folder, both read only."""

    def __init__(self) -> None:
        self.paperless: list[dict[str, Any]] = []
        self.paperless_bytes: dict[int, bytes] = {}
        self.drive: list[dict[str, Any]] = []
        self.drive_bytes: dict[str, bytes] = {}
        self.list_calls: list[dict[str, str]] = []

    def add_paperless(self, id_: int, title: str, added: str, content: str, **extra: Any) -> None:
        self.paperless.append(
            {
                "id": id_,
                "title": title,
                "added": added,
                "created": added,
                "content": content,
                "original_file_name": f"{title}.pdf",
                "tags": [],
                **extra,
            }
        )
        self.paperless_bytes[id_] = _pdf(content)

    def add_drive(self, id_: str, name: str, modified: str, content: str) -> None:
        self.drive.append(
            {"id": id_, "name": name, "mimeType": "application/pdf", "modifiedTime": modified}
        )
        self.drive_bytes[id_] = _pdf(content)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        if url.startswith(f"{PAPERLESS_URL}/api/"):
            assert request.headers["authorization"] == "Token paperless-token"
            if path == "/api/documents/":
                params = dict(request.url.params)
                self.list_calls.append(params)
                after = params.get("added__gt")
                rows = [d for d in self.paperless if not after or d["added"] > after]
                rows.sort(key=lambda d: d["added"])
                return httpx.Response(200, json={"count": len(rows), "results": rows})
            if path.endswith("/download/"):
                doc_id = int(path.split("/")[3])
                return httpx.Response(
                    200,
                    content=self.paperless_bytes[doc_id],
                    headers={
                        "content-type": "application/pdf",
                        "content-disposition": f'attachment; filename="p{doc_id}.pdf"',
                    },
                )
            return httpx.Response(404)
        if url.startswith("https://oauth2.googleapis.com/token"):
            return httpx.Response(200, json={"access_token": "drive-token"})
        if url.startswith("https://www.googleapis.com/drive/v3/files"):
            assert request.headers["authorization"] == "Bearer drive-token"
            params = dict(request.url.params)
            if params.get("alt") == "media":
                return httpx.Response(200, content=self.drive_bytes[path.rsplit("/", 1)[1]])
            q = params.get("q", "")
            assert "'inbox-1' in parents" in q
            after = None
            if "modifiedTime > '" in q:
                after = q.split("modifiedTime > '", 1)[1].split("'", 1)[0]
            rows = [f for f in self.drive if not after or f["modifiedTime"] > after]
            return httpx.Response(200, json={"files": rows})
        return httpx.Response(404)


def _run(fake: FakeInbox, database: Database, redis_url: str) -> dict[str, int]:
    settings = _settings(database, redis_url)

    async def go() -> dict[str, int]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            return await process_inbox_once(settings, client=http, blobs=BlobStore(settings))

    return asyncio.run(go())


def _setup(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "602",
                "name": "Am Fließ",
                "management_type": "rental",
                "street": "Hauptstraße",
                "house_number": "5",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Erika",
                "last_name": f"Eingang{RUN}",
                "emails": [{"email": f"erika{RUN}@example.com"}],
            },
            headers=h,
        )
    )
    categories = _ok(client.get("/api/v1/document-categories", headers=h), 200)
    invoice = next(c for c in categories if c["code"] == "invoice")
    rule = _ok(
        client.post(
            "/api/v1/objektakte/classification-rules",
            json={
                "name": "Rechnung im Text",
                "pattern_type": "text_keyword",
                "pattern_value": "Rechnung",
                "target_category_id": invoice["id"],
                "confidence": 0.9,
            },
            headers=h,
        )
    )
    _ok(
        client.put(
            "/api/v1/dms-connections/paperless",
            json={
                "enabled": True,
                "base_url": PAPERLESS_URL,
                "secret": "paperless-token",
            },
            headers=h,
        ),
        200,
    )
    _ok(
        client.put(
            "/api/v1/dms-connections/google_drive",
            json={
                "enabled": True,
                "secret": json.dumps({"client_secret": "s", "refresh_token": "r"}),
                "options": {
                    "root_folder_id": "root",
                    "client_id": "c",
                    "inbox_folder_id": "inbox-1",
                },
            },
            headers=h,
        ),
        200,
    )
    return {"property": prop, "contact": contact, "invoice": invoice, "rule": rule}


def _pending(client: TestClient, h: dict[str, str], **params: str) -> list[dict[str, Any]]:
    return list(_ok(client.get(P, params=params, headers=h), 200)["data"])


def test_inbox_proposals_from_paperless_drive_and_mail(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "ibadmin"))
    ctx = _setup(client, h)
    fake = FakeInbox()
    fake.add_paperless(
        101,
        "Rechnung Dachdecker",
        "2026-09-20T10:00:00+02:00",
        "Rechnung Nr. 4711 für Objekt 602, Hauptstraße 5, Monheim am Rhein",
        correspondent=None,
    )
    fake.add_paperless(
        102, "Sonstiges", "2026-09-21T10:00:00+02:00", "Ein Schreiben ohne Bezug", tags=[]
    )
    fake.add_drive(
        "dfile-1",
        "Angebot.pdf",
        "2026-09-22T08:00:00.000Z",
        f"Angebot von Erika Eingang{RUN} für das Haus",
    )
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "m.eml",
                    _eml(
                        f"erika{RUN}@example.com",
                        "Kostenvoranschlag Objekt 602",
                        "Anbei der Kostenvoranschlag.",
                        f"<inbox-{RUN}@example.test>",
                    ),
                    "message/rfc822",
                )
            },
            headers=h,
        )
    )
    msg = _ok(client.post("/api/v1/mail/ingest", json={"document_id": doc["id"]}, headers=h))
    assert len(msg["attachment_document_ids"]) == 1
    assert msg["contact_id"] == ctx["contact"]["id"], msg

    totals = _run(fake, database, redis_url)  # other test tenants share the database
    assert totals["paperless"] >= 2
    assert totals["google_drive"] >= 1
    assert totals["mailbox"] >= 1

    pending = _pending(client, h)
    by_source: dict[str, list[dict[str, Any]]] = {}
    for p in pending:
        by_source.setdefault(p["source"], []).append(p)
    assert set(by_source) == {"paperless", "google_drive", "mailbox"}

    invoice = next(p for p in by_source["paperless"] if "Dachdecker" in p["document_title"])
    proposed = invoice["proposed"]
    assert proposed["property_id"] == ctx["property"]["id"]
    assert proposed["property_number"] == "602"
    assert proposed["category_id"] == ctx["invoice"]["id"]
    assert proposed["classification"]["rule_id"] == ctx["rule"]["id"]
    assert proposed["confidence"] > 0.8
    assert any("Objektnummer 602" in r for r in proposed["reasons"])
    assert proposed["text_status"] == "extracted"
    # Nothing was linked or categorised without confirmation (rule 0.1.6).
    stored = _ok(client.get(f"/api/v1/documents/{invoice['document_id']}", headers=h), 200)
    assert stored["links"] == []
    assert stored["category_id"] is None

    mail = by_source["mailbox"][0]
    assert mail["document_id"] == msg["attachment_document_ids"][0]
    assert mail["proposed"]["contact_id"] == ctx["contact"]["id"]
    assert mail["proposed"]["property_number"] == "602"
    assert any("Absenderadresse" in r for r in mail["proposed"]["reasons"])

    drive = by_source["google_drive"][0]
    assert drive["document_title"] == "Angebot.pdf"
    assert drive["proposed"]["contact_id"] == ctx["contact"]["id"]

    # Watermarks stored; a second run finds nothing new and creates nothing twice.
    connections = {c["kind"]: c for c in _ok(client.get("/api/v1/dms-connections", headers=h), 200)}
    assert connections["paperless"]["options"]["intake_watermark"] == "2026-09-21T10:00:00+02:00"
    assert connections["google_drive"]["options"]["intake_watermark"] == "2026-09-22T08:00:00.000Z"
    again = _run(fake, database, redis_url)
    assert (again["paperless"], again["google_drive"], again["mailbox"]) == (0, 0, 0)
    assert fake.list_calls[-1]["added__gt"] == "2026-09-21T10:00:00+02:00"
    assert len(_pending(client, h)) == len(pending)

    # A new Paperless document after the watermark is picked up on the next run.
    fake.add_paperless(103, "Rechnung Maler", "2026-09-25T10:00:00+02:00", "Rechnung Maler 602")
    assert _run(fake, database, redis_url)["paperless"] >= 1
    assert len(_pending(client, h)) == len(pending) + 1

    # Accept: links and category are set only now; the proposal is decided once.
    accepted = _ok(client.post(f"{P}/{invoice['id']}/accept", headers=h), 200)
    assert accepted["decision"] == "accepted"
    assert accepted["final"]["property_id"] == ctx["property"]["id"]
    stored = _ok(client.get(f"/api/v1/documents/{invoice['document_id']}", headers=h), 200)
    assert {(x["entity_type"], x["entity_id"]) for x in stored["links"]} == {
        ("property", ctx["property"]["id"])
    }
    assert stored["category_id"] == ctx["invoice"]["id"]
    assert client.post(f"{P}/{invoice['id']}/accept", headers=h).status_code == 409

    # Accept with an override counts as modified.
    modified = _ok(
        client.post(
            f"{P}/{mail['id']}/accept",
            json={"contact_id": ctx["contact"]["id"], "category_id": ctx["invoice"]["id"]},
            headers=h,
        ),
        200,
    )
    assert modified["decision"] == "modified"
    stored = _ok(client.get(f"/api/v1/documents/{mail['document_id']}", headers=h), 200)
    assert {x["entity_type"] for x in stored["links"]} == {"property", "contact"}

    # Reject learns from the rule that fired; the next proposal of that rule scores lower.
    maler = next(p for p in _pending(client, h) if p["document_title"] == "Rechnung Maler")
    rejected = _ok(
        client.post(f"{P}/{maler['id']}/reject", json={"reason": "falsche Kategorie"}, headers=h),
        200,
    )
    assert rejected["decision"] == "rejected"
    fake.add_paperless(104, "Rechnung Gas", "2026-09-26T10:00:00+02:00", "Rechnung Gas 602")
    assert _run(fake, database, redis_url)["paperless"] >= 1
    gas = next(p for p in _pending(client, h) if p["document_title"] == "Rechnung Gas")
    assert gas["proposed"]["classification"]["rejected_examples"] == 1
    assert gas["proposed"]["classification"]["confidence"] == 0.45
    assert any("abgelehnt" in r for r in gas["proposed"]["reasons"])

    listed = _ok(client.get(P, params={"decision": "rejected"}, headers=h), 200)
    assert [p["id"] for p in listed["data"]] == [maler["id"]]
    events = _ok(
        client.get("/api/v1/tenant/events", params={"type": "document.intake_accepted"}, headers=h),
        200,
    )
    assert any(e["entity_id"] == invoice["document_id"] for e in events)


def test_inbox_permissions_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ibadmin"))
    pending = _pending(client, h, decision="all")
    assert pending, "the first test creates proposals"
    caretaker = bearer(login(client, world, "ibcaretaker"))
    assert client.get(P, headers=caretaker).status_code == 403
    assert client.post(f"{P}/{pending[0]['id']}/accept", headers=caretaker).status_code == 403
    other = bearer(login(client, world, "ibother"))
    assert _ok(client.get(P, params={"decision": "all"}, headers=other), 200)["data"] == []
    assert client.get(f"{P}/{pending[0]['id']}", headers=other).status_code == 404
    assert client.post(f"{P}/{pending[0]['id']}/reject", headers=other).status_code == 404
