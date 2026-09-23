"""M6 acceptance: upload, link, full text search, retention lock, letters on the tenant letterhead,
serial letters, mirroring to Paperless and Google Drive (6.7, 6.9.5, 11)."""

import asyncio
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from mhvp.core.config import Settings
from mhvp.documents.blobs import BlobStore
from mhvp.documents.tasks import mirror_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-docs"

COMPANY = {
    "name": "Hausverwaltung Müller GmbH",
    "legal_form": "GmbH",
    "street": "Rheinpromenade 13",
    "postal_code": "40789",
    "city": "Monheim am Rhein",
    "register_court": "Amtsgericht Düsseldorf",
    "register_number": "HRB 104762",
    "management": ["Timo Müller"],
    "management_title": "Geschäftsführer",
    "website": "www.muellerhv.de",
}


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
        a, _ = await services.provision_tenant(factory, slug=f"d-{RUN}", name=f"Dokumente {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"e-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m6admin", a, "tenant_admin"),
            ("m6second", a, "tenant_admin"),
            ("m6caretaker", a, "caretaker"),
            ("m6other", b, "tenant_admin"),
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


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
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


def _upload(
    c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str, **form: str
) -> Any:
    return c.post("/api/v1/documents", files={"file": (name, data, mime)}, data=form, headers=h)


def _contact(c: TestClient, h: dict[str, str], last: str, **extra: Any) -> dict[str, Any]:
    body = {
        "kind": "person",
        "first_name": "Erika",
        "last_name": f"{last}{RUN}",
        "addresses": [
            {
                "street": "Rheinpromenade",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            }
        ],
        **extra,
    }
    return _ok(c.post("/api/v1/contacts", json=body, headers=h))  # type: ignore[no-any-return]


def test_upload_link_search_download_and_isolation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m6admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "601",
                "name": "Rheinpromenade",
                "management_type": "rental",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    categories = _ok(client.get("/api/v1/document-categories", headers=h), 200)
    invoice = next(c for c in categories if c["code"] == "invoice")
    assert invoice["drive_folder"] == "03_Buchhaltung"
    links = json.dumps([{"entity_type": "property", "entity_id": prop["id"]}])
    original = _pdf(f"Dachrinnenreinigung {RUN}")
    doc = _ok(
        _upload(
            client,
            h,
            "rechnung.pdf",
            original,
            "application/pdf",
            title="Rechnung Dachrinne",
            category_id=invoice["id"],
            links=links,
        )
    )
    assert doc["text_status"] == "extracted"
    assert doc["storage"] == "minio"
    assert doc["links"][0]["entity_type"] == "property"
    again = _ok(_upload(client, h, "kopie.pdf", original, "application/pdf"))
    assert again["duplicate_of"] == [doc["id"]]

    found = _ok(
        client.get("/api/v1/documents", params={"q": "Dachrinnenreinigung"}, headers=h), 200
    )
    assert {d["id"] for d in found["items"]} >= {doc["id"], again["id"]}
    assert any("<<" in (d["snippet"] or "") for d in found["items"])
    linked = _ok(
        client.get(
            "/api/v1/documents",
            params={"entity_type": "property", "entity_id": prop["id"]},
            headers=h,
        ),
        200,
    )
    assert [d["id"] for d in linked["items"]] == [doc["id"]]
    content = client.get(f"/api/v1/documents/{doc['id']}/content", headers=h)
    assert content.status_code == 200
    assert content.content.startswith(b"%PDF-")
    assert content.headers["x-content-type-options"] == "nosniff"

    photo = _ok(_upload(client, h, "foto.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png"))
    assert photo["text_status"] == "pending"
    assert _upload(client, h, "x.exe", b"MZ\x90\x00", "application/x-msdownload").status_code == 422
    fake = _upload(client, h, "fake.pdf", b"MZ not a pdf", "application/pdf")
    assert fake.status_code == 422
    assert fake.json()["code"] == "MHVP-DOC-0003"
    assert _upload(client, h, "big.txt", b"x" * 200_001, "text/plain").status_code == 422
    bad_link = json.dumps([{"entity_type": "invoice", "entity_id": prop["id"]}])
    assert _upload(client, h, "a.txt", b"abc", "text/plain", links=bad_link).status_code == 422

    contact = _contact(client, h, "Link")
    linked_doc = _ok(
        client.post(
            f"/api/v1/documents/{doc['id']}/links",
            json={"entity_type": "contact", "entity_id": contact["id"]},
            headers=h,
        )
    )
    assert len(linked_doc["links"]) == 2
    assert (
        client.post(
            f"/api/v1/documents/{doc['id']}/links",
            json={"entity_type": "contact", "entity_id": contact["id"]},
            headers=h,
        ).status_code
        == 409
    )
    link_id = next(x["id"] for x in linked_doc["links"] if x["entity_type"] == "contact")
    unlinked = _ok(client.delete(f"/api/v1/documents/{doc['id']}/links/{link_id}", headers=h), 200)
    assert len(unlinked["links"]) == 1
    patched = _ok(
        client.patch(
            f"/api/v1/documents/{doc['id']}",
            json={"title": "Rechnung Dachrinne 2026", "visibility": ["tenant", "owner"]},
            headers=h,
        ),
        200,
    )
    assert patched["visibility"] == ["tenant", "owner"]
    assert (
        client.patch(
            f"/api/v1/documents/{doc['id']}", json={"visibility": ["public"]}, headers=h
        ).status_code
        == 422
    )

    other = bearer(login(client, world, "m6other"))
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/documents/{doc['id']}/content", headers=other).status_code == 404
    caretaker = bearer(login(client, world, "m6caretaker"))
    assert client.get("/api/v1/documents", headers=caretaker).status_code == 403


def test_retention_blocks_deletion_until_released_profile_expired(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "m6admin"))
    doc = _ok(_upload(client, h, "beleg.txt", b"Beleg", "text/plain"))
    url = f"/api/v1/documents/{doc['id']}"
    refused = client.delete(url, headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-DOC-0001"
    profile = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"test_{RUN}",
                "legal_basis": "Testprofil ohne Rechtsquelle",
                "retention_years": 1,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )
    _ok(
        client.patch(
            url,
            json={"retention_profile_id": profile["id"], "retention_until": "2020-12-31"},
            headers=h,
        ),
        200,
    )
    assert client.delete(url, headers=h).status_code == 409  # profile not released
    own = client.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=h)
    assert own.status_code == 403  # four eyes
    second = bearer(login(client, world, "m6second"))
    released = _ok(
        client.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=second), 200
    )
    assert released["released_by"] == str(world.users["m6second"])
    _ok(client.post(f"{url}/hold", json={"reason": "Rechtsstreit Beispiel"}, headers=h), 200)
    held = client.delete(url, headers=h)
    assert held.status_code == 409
    assert "Löschungssperre" in held.json()["detail"]
    _ok(
        client.request("DELETE", f"{url}/hold", json={"reason": "Verfahren beendet"}, headers=h),
        200,
    )
    assert client.delete(url, headers=h).status_code == 204
    assert client.get(url, headers=h).status_code == 404


def test_letters_on_letterhead_and_serial_letters(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m6admin"))
    templates = _ok(client.get("/api/v1/document-templates", headers=h), 200)
    free = next(t for t in templates if t["code"] == "free_letter")
    anna = _contact(client, h, "Brief", salutation="Frau")
    firma = _contact(client, h, "Firma")
    letter = {
        "template_id": free["id"],
        "contact_id": anna["id"],
        "letter_date": "2026-09-23",
        "fields": {"betreff": "Ablesetermin", "text": "Der Ablesetermin ist am 01.10.2026."},
    }
    incomplete = client.post("/api/v1/letters", json=letter, headers=h)
    assert incomplete.status_code == 422
    assert incomplete.json()["code"] == "MHVP-DOC-0004"
    band = [{"color": "#87888A", "from": 0, "to": 0.4}, {"color": "#E6A83C", "from": 0.4, "to": 1}]
    _ok(
        client.patch(
            "/api/v1/tenant/settings",
            json={"company": COMPANY, "branding": {"letter_band": band}},
            headers=h,
        ),
        200,
    )

    missing = client.post("/api/v1/letters", json={**letter, "fields": {"betreff": "x"}}, headers=h)
    assert missing.status_code == 422
    assert missing.json()["code"] == "MHVP-DOC-0002"
    preview = client.post("/api/v1/letters/preview", json=letter, headers=h)
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    text = PdfReader(io.BytesIO(preview.content)).pages[0].extract_text()
    assert f"Sehr geehrte Frau Brief{RUN}," in text
    assert "Amtsgericht Düsseldorf, HRB 104762" in text
    assert "23.09.2026" in text
    assert (
        _ok(client.get("/api/v1/documents", params={"q": "Ablesetermin"}, headers=h), 200)["total"]
        == 0
    )

    doc = _ok(client.post("/api/v1/letters", json=letter, headers=h))
    assert doc["source"] == "generated"
    assert doc["title"] == "Ablesetermin"
    assert {(x["entity_type"], x["role"]) for x in doc["links"]} == {("contact", "generated")}

    injected = {**letter, "fields": {"betreff": "<b>fett</b> & Co", "text": "{{ 7 * 7 }}"}}
    safe = client.post("/api/v1/letters/preview", json=injected, headers=h)
    assert safe.status_code == 200
    safe_text = PdfReader(io.BytesIO(safe.content)).pages[0].extract_text()
    assert "<b>fett</b> & Co" in safe_text  # escaped, not interpreted
    assert "{{ 7 * 7 }}" in safe_text  # values are not evaluated as templates

    bad = client.post(
        "/api/v1/document-templates",
        json={"code": "broken", "name": "x", "subject": "{{ a", "body": "b"},
        headers=h,
    )
    assert bad.status_code == 422
    v1 = _ok(
        client.post(
            "/api/v1/document-templates",
            json={
                "code": f"info_{RUN}",
                "name": "Info",
                "subject": "Info {{ felder.thema }}",
                "body": "{{ empfaenger.anrede }}\n\nHinweis zu {{ felder.thema }}.",
            },
            headers=h,
        )
    )
    v2 = _ok(
        client.post(
            "/api/v1/document-templates",
            json={
                "code": f"info_{RUN}",
                "name": "Info",
                "subject": "Hinweis {{ felder.thema }}",
                "body": "{{ empfaenger.anrede }}\n\n{{ felder.thema }}.",
            },
            headers=h,
        )
    )
    assert v2["version"] == 2
    old = client.post(
        "/api/v1/letters",
        json={**letter, "template_id": v1["id"], "fields": {"thema": "Heizung"}},
        headers=h,
    )
    assert old.status_code == 422  # inactive version

    serial = _ok(
        client.post(
            "/api/v1/letters/serial",
            json={
                "template_id": v2["id"],
                "contact_ids": [anna["id"], firma["id"]],
                "fields": {"thema": "Heizungswartung"},
            },
            headers=h,
        )
    )
    assert len(serial["documents"]) == 2
    assert {d["links"][0]["entity_id"] for d in serial["documents"]} == {anna["id"], firma["id"]}
    no_address = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Ohne", "last_name": f"Adresse{RUN}"},
            headers=h,
        )
    )
    before = _ok(client.get("/api/v1/documents", params={"q": "Heizungswartung"}, headers=h), 200)[
        "total"
    ]
    failed = client.post(
        "/api/v1/letters/serial",
        json={
            "template_id": v2["id"],
            "contact_ids": [anna["id"], no_address["id"]],
            "fields": {"thema": "Heizungswartung"},
        },
        headers=h,
    )
    assert failed.status_code == 422
    after = _ok(client.get("/api/v1/documents", params={"q": "Heizungswartung"}, headers=h), 200)[
        "total"
    ]
    assert after == before  # all or none
    assert (
        client.post(
            "/api/v1/letters/serial",
            json={"template_id": v2["id"], "contact_ids": [anna["id"], anna["id"]]},
            headers=h,
        ).status_code
        == 422
    )


class FakeDms:
    """Minimal Paperless-ngx and Google Drive endpoints for the mirror job."""

    def __init__(self) -> None:
        self.paperless_uploads: list[dict[str, Any]] = []
        self.drive_folders: dict[str, tuple[str, str]] = {}
        self.drive_files: list[dict[str, Any]] = []
        self.fail_paperless = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://dms.example.org/api/"):
            assert request.headers["authorization"] == "Token paperless-token"
            path = request.url.path
            if self.fail_paperless:
                return httpx.Response(503)
            if path.endswith("/post_document/"):
                self.paperless_uploads.append({"body": request.content})
                return httpx.Response(200, json="task-1")
            if path.endswith("/tasks/"):
                return httpx.Response(200, json=[{"status": "SUCCESS", "related_document": 42}])
            if request.method == "GET":
                return httpx.Response(200, json={"results": []})
            return httpx.Response(201, json={"id": 7})
        if url.startswith("https://oauth2.googleapis.com/token"):
            return httpx.Response(200, json={"access_token": "drive-token"})
        if url.startswith("https://www.googleapis.com/drive/v3/files"):
            assert request.headers["authorization"] == "Bearer drive-token"
            if request.method == "GET":
                q = request.url.params["q"]
                hits = [
                    {"id": i}
                    for i, (name, parent) in self.drive_folders.items()
                    if f"name = '{name}'" in q and f"'{parent}' in parents" in q
                ]
                return httpx.Response(200, json={"files": hits})
            meta = json.loads(request.content)
            folder_id = f"f{len(self.drive_folders)}"
            self.drive_folders[folder_id] = (meta["name"], meta["parents"][0])
            return httpx.Response(200, json={"id": folder_id})
        if url.startswith("https://www.googleapis.com/upload/drive/v3/files"):
            self.drive_files.append({"body": request.content})
            return httpx.Response(200, json={"id": "drive-file-1"})
        return httpx.Response(404)


def test_mirror_to_paperless_and_drive(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "m6admin"))
    assert (
        client.put(
            "/api/v1/dms-connections/paperless", json={"enabled": True}, headers=h
        ).status_code
        == 422
    )
    _ok(
        client.put(
            "/api/v1/dms-connections/paperless",
            json={
                "enabled": True,
                "base_url": "https://dms.example.org",
                "secret": "paperless-token",
            },
            headers=h,
        ),
        200,
    )
    assert (
        client.put(
            "/api/v1/dms-connections/google_drive",
            json={
                "enabled": True,
                "secret": "{}",
                "options": {"root_folder_id": "root", "client_id": "c"},
            },
            headers=h,
        ).status_code
        == 422
    )
    drive = _ok(
        client.put(
            "/api/v1/dms-connections/google_drive",
            json={
                "enabled": True,
                "secret": json.dumps({"client_secret": "s", "refresh_token": "r"}),
                "options": {"root_folder_id": "root", "client_id": "c"},
            },
            headers=h,
        ),
        200,
    )
    assert drive["has_secret"] is True
    assert "secret" not in drive
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "602",
                "name": "Objekt",
                "management_type": "rental",
                "street": "Hauptstraße",
                "house_number": "5",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    categories = _ok(client.get("/api/v1/document-categories", headers=h), 200)
    invoice = next(c for c in categories if c["code"] == "invoice")
    doc = _ok(
        _upload(
            client,
            h,
            "r.pdf",
            _pdf("Rechnung"),
            "application/pdf",
            category_id=invoice["id"],
            links=json.dumps([{"entity_type": "property", "entity_id": prop["id"]}]),
        )
    )
    assert {m["kind"]: m["status"] for m in doc["mirrors"]} == {
        "paperless": "pending",
        "google_drive": "pending",
    }

    fake = FakeDms()
    settings = _settings(database, redis_url)

    async def run(now: datetime | None = None) -> dict[str, int]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            return await mirror_once(settings, client=http, blobs=BlobStore(settings), now=now)

    asyncio.run(run())
    state = {
        m["kind"]: m
        for m in _ok(client.get(f"/api/v1/documents/{doc['id']}", headers=h), 200)["mirrors"]
    }
    assert state["google_drive"]["status"] == "done"
    assert state["google_drive"]["external_ref"] == "drive-file-1"
    assert state["paperless"]["status"] == "pending"
    assert state["paperless"]["last_error"] == "lookup tags: HTTP 503"
    names = {name for name, _ in fake.drive_folders.values()}
    assert names == {"602 Monheim am Rhein, Hauptstraße 5", "03_Buchhaltung"}

    fake.fail_paperless = False
    asyncio.run(run(datetime.now(UTC) + timedelta(minutes=2)))  # after the first backoff
    state = {
        m["kind"]: m
        for m in _ok(client.get(f"/api/v1/documents/{doc['id']}", headers=h), 200)["mirrors"]
    }
    assert state["paperless"]["status"] == "done"
    assert state["paperless"]["external_ref"] == "42"
    body = fake.paperless_uploads[0]["body"]
    assert b'name="title"' in body
    assert b'name="tags"' in body
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 409
