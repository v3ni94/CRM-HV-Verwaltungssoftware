"""M29 Stufe 4 (docs/plans/M29-dms.md): DMS page data from objektakte, webhook and import
proposals of the owner and tenant lists.

objektakte is never called: every request goes to an ``httpx.MockTransport`` with recorded
answers in the shape of the contract (docs/integrations/objektakte.md). Covers the happy path,
switched off connection (no URL/token, other tenant), upstream failures as 502, authorization
(caretaker without ``objektakte:read``, read only role on writing endpoints), tenant separation
(tenant B sees nothing of tenant A), webhook signature, idempotency and matching over
``drive_file_id`` and ``sha256``, and that a released proposal writes no master data."""

import asyncio
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.models import (
    Document,
    DocumentLink,
    DocumentSource,
    StorageKind,
    TextStatus,
)
from mhvp.main import create_app
from mhvp.objektakte.dms_models import ObjektakteWebhookReceipt
from mhvp.objektakte.webhook import sign
from mhvp.platform import services
from mhvp.properties.models import ManagementType, Property
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _unit

pytestmark = pytest.mark.integration
BASE = "/api/v1/integrations/objektakte"
API_URL = "https://uebernahme.example.test/api/crm/v1/"
TOKEN = "test-token-" + RUN
SECRET = "test-webhook-" + RUN
SLUG = f"m29dms-{RUN}"
SHA_UPLOAD = "a" * 64
SHA_FILED = "b" * 64


def _configured(database: Database, redis_url: str, **overrides: object) -> Any:
    values: dict[str, object] = {
        "objektakte_api_url": API_URL,
        "objektakte_api_token": SecretStr(TOKEN),
        "objektakte_webhook_secret": SecretStr(SECRET),
        "objektakte_tenant": SLUG,
    }
    values.update(overrides)
    return base_settings(database, redis_url, **values)


def _object(number: str, **extra: Any) -> dict[str, Any]:
    return {
        "number": number,
        "name": f"Objekt {number}",
        "archived": False,
        "takeover_status": "in_progress",
        "open_review_cases": 3,
        "completeness": {"required": 10, "present": 7, "missing": 3, "percent": 70.0},
        "drive_folder_id": f"folder-{number}",
        "drive_folder_url": f"https://drive.google.com/drive/folders/folder-{number}",
        "updated_at": "2026-09-25T10:00:00Z",
        **extra,
    }


def _doc(doc_id: int, sha: str, drive: str | None, title: str) -> dict[str, Any]:
    return {
        "id": doc_id,
        "title": title,
        "doc_type": "Teilungserklärung",
        "category": "02_Stammakte",
        "subfolder": None,
        "status": "filed",
        "drive_file_id": drive,
        "drive_url": f"https://drive.google.com/file/d/{drive}/view" if drive else None,
        "sha256": sha,
        "filed_at": "2026-09-24T08:00:00Z",
        "mime_type": "application/pdf",
        "size_bytes": 1234,
    }


class FakeObjektakte:
    """Recorded answers of the five endpoints; ``fail`` switches every call to an error."""

    def __init__(self, owners: list[dict[str, Any]], docs: list[dict[str, Any]]) -> None:
        self.owners = owners
        self.docs = docs
        self.fail: int | None = None
        self.calls: list[httpx.Request] = []

    def _page(self, rows: list[dict[str, Any]], request: httpx.Request) -> dict[str, Any]:
        page = int(request.url.params.get("page", "1"))
        size = int(request.url.params.get("page_size", "100"))
        chunk = rows[(page - 1) * size : page * size]
        return {"count": len(rows), "page": page, "page_size": size, "results": chunk}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert request.method == "GET"
        if self.fail is not None:
            return httpx.Response(self.fail, json={"detail": "kaputt"})
        path = request.url.path.removeprefix("/api/crm/v1/")
        if path == "objects/":
            return httpx.Response(200, json=self._page([_object("291"), _object("77")], request))
        if path == "objects/291/":
            return httpx.Response(
                200,
                json=_object(
                    "291",
                    address={"street": "Testweg", "house_number": "1", "zip": None, "city": None},
                    missing_documents=[
                        {
                            "category": "02_Stammakte",
                            "subfolder": None,
                            "label": "Teilungserklärung",
                        }
                    ],
                    open_cases_by_type={"classification/low_confidence": 3},
                ),
            )
        if path == "objects/291/documents/":
            return httpx.Response(200, json=self._page(self.docs, request))
        if path == "objects/291/owners/":
            return httpx.Response(200, json=self._page(self.owners, request))
        if path == "objects/291/tenants/":
            return httpx.Response(200, json=self._page([], request))
        return httpx.Response(404, json={"detail": "Nicht gefunden."})


async def _world(settings: Any) -> tuple[World, dict[str, Any]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, Any] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG, name=f"DMS {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"m29dmsb-{RUN}", name=f"DMS B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("dmsadmin", a, "tenant_admin"),
            ("dmscaretaker", a, "caretaker"),
            ("dmsreader", a, "read_only"),
            ("dmsother", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        async with tenant_transaction(factory, a) as session:
            upload = Document(
                tenant_id=a,
                title="Hochgeladen",
                filename="hochgeladen.pdf",
                mime_type="application/pdf",
                size=10,
                sha256=SHA_UPLOAD,
                storage=StorageKind.MINIO,
                storage_ref="ref-upload",
                text_status=TextStatus.EXTRACTED,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            session.add(upload)
            await session.flush()
            ids["upload"] = upload.id
        async with tenant_transaction(factory, b) as session:
            session.add(
                Property(
                    tenant_id=b, number="291", name="Fremd", management_type=ManagementType.HOA
                )
            )
        return world, ids
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world_and_ids(database: Database, redis_url: str) -> tuple[World, dict[str, Any]]:
    return asyncio.run(_world(_configured(database, redis_url)))


@pytest.fixture
def fake() -> FakeObjektakte:
    return FakeObjektakte(owners=[], docs=[])


@pytest.fixture
def make_client(
    database: Database, redis_url: str, fake: FakeObjektakte
) -> Iterator[Callable[..., TestClient]]:
    opened: list[TestClient] = []

    def _make(**overrides: object) -> TestClient:
        app = create_app(_configured(database, redis_url, **overrides))
        app.state.objektakte_transport = httpx.MockTransport(fake.handler)
        client = TestClient(app)
        client.__enter__()
        opened.append(client)
        return client

    yield _make
    for client in opened:
        client.__exit__(None, None, None)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    """Property 291 of tenant A, created once through the API (with its WEG community)."""
    found = _ok(client.get("/api/v1/properties", params={"page_size": 200}, headers=h))
    for item in found["items"]:
        if item["number"] == "291":
            return dict(item)
    body = {"number": "291", "name": "Haus DMS", "management_type": "hoa"}
    return dict(_ok(client.post("/api/v1/properties", json=body, headers=h), 201))


def test_switched_off_and_other_tenant(
    make_client: Callable[..., TestClient], world_and_ids: tuple[World, dict[str, Any]]
) -> None:
    world, _ = world_and_ids
    off = make_client(objektakte_api_url=None, objektakte_api_token=None)
    h = bearer(login(off, world, "dmsadmin"))
    assert _ok(off.get(f"{BASE}/status", headers=h)) == {
        "configured": False,
        "reason": "not_configured",
        "webhook_configured": False,
        "upload_enabled": False,
    }
    refused = off.get(f"{BASE}/objects", headers=h)
    assert refused.status_code == 502
    assert refused.json()["code"] == "MHVP-OAK-0001"

    client = make_client()
    hb = bearer(login(client, world, "dmsother"))
    assert _ok(client.get(f"{BASE}/status", headers=hb))["reason"] == "other_tenant"
    other = client.get(f"{BASE}/objects", headers=hb)
    assert other.status_code == 502
    assert other.json()["code"] == "MHVP-OAK-0001"


def test_objects_detail_and_upstream_errors(
    make_client: Callable[..., TestClient],
    world_and_ids: tuple[World, dict[str, Any]],
    fake: FakeObjektakte,
) -> None:
    world, _ = world_and_ids
    client = make_client()
    h = bearer(login(client, world, "dmsadmin"))
    prop = _property(client, h)
    assert _ok(client.get(f"{BASE}/status", headers=h))["configured"] is True

    tiles = _ok(client.get(f"{BASE}/objects", headers=h))
    assert tiles["total"] == 2
    by_number = {t["number"]: t for t in tiles["items"]}
    assert by_number["291"]["property_id"] == prop["id"]
    assert by_number["291"]["completeness"]["missing"] == 3
    assert by_number["77"]["property_id"] is None  # "077" is not a property of tenant A

    detail = _ok(client.get(f"{BASE}/objects/291", headers=h))
    assert detail["missing_documents"][0]["label"] == "Teilungserklärung"
    assert detail["property_id"] == prop["id"]
    assert detail["crm_document_count"] == 0

    missing = client.get(f"{BASE}/objects/999", headers=h)
    assert missing.status_code == 404
    assert missing.json()["code"] == "MHVP-OAK-0003"

    for status in (500, 401):
        fake.fail = status
        failed = client.get(f"{BASE}/objects", headers=h)
        assert failed.status_code == 502, failed.text
        assert failed.json()["code"] == "MHVP-OAK-0002"
        assert TOKEN not in failed.text
    fake.fail = None

    caretaker = bearer(login(client, world, "dmscaretaker"))
    assert client.get(f"{BASE}/objects", headers=caretaker).status_code == 403
    assert client.get(f"{BASE}/status", headers=caretaker).status_code == 403


def test_documents_link_by_drive_id_and_sha256(
    make_client: Callable[..., TestClient],
    world_and_ids: tuple[World, dict[str, Any]],
    fake: FakeObjektakte,
    database: Database,
    redis_url: str,
) -> None:
    """Three objektakte documents: 9001 has the content hash of an uploaded CRM document (linked,
    not duplicated), 9002 is new (created as Drive document), 9003 is invalid (no sha256) and is
    counted, never guessed. A second backfill changes nothing."""
    world, ids = world_and_ids
    fake.docs = [
        _doc(9001, SHA_UPLOAD, "drive-9001", "Teilungserklärung"),
        _doc(9002, SHA_FILED, "drive-9002", "Energieausweis"),
        {**_doc(9003, SHA_FILED, None, "Kaputt"), "sha256": None},
    ]
    client = make_client()
    h = bearer(login(client, world, "dmsadmin"))
    prop = _property(client, h)

    page = _ok(client.get(f"{BASE}/objects/291/documents", headers=h))
    assert page["count"] == 3
    rows = {r["id"]: r for r in page["results"]}
    assert rows[9001]["crm_document_id"] == str(ids["upload"])
    assert rows[9002]["crm_document_id"] is None

    reader = bearer(login(client, world, "dmsreader"))
    assert client.post(f"{BASE}/objects/291/documents/link", headers=reader).status_code == 403

    first = _ok(client.post(f"{BASE}/objects/291/documents/link", headers=h))
    assert (first["created"], first["linked"], first["invalid"]) == (1, 1, 1)
    assert first["property_id"] == prop["id"]
    again = _ok(client.post(f"{BASE}/objects/291/documents/link", headers=h))
    assert (again["created"], again["linked"], again["unchanged"]) == (0, 0, 2)

    page = _ok(client.get(f"{BASE}/objects/291/documents", headers=h))
    created_id = {r["id"]: r for r in page["results"]}[9002]["crm_document_id"]
    assert created_id is not None
    doc = _ok(client.get(f"/api/v1/documents/{created_id}", headers=h))
    assert doc["storage"] == "google_drive"
    assert doc["sha256"] == SHA_FILED
    detail = _ok(client.get(f"{BASE}/objects/291", headers=h))
    assert detail["crm_document_count"] >= 2

    async def _check() -> tuple[int, str | None]:
        engine = create_app_engine(_configured(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), world.tenant_a) as s:
                count = await s.scalar(
                    select(func.count(Document.id)).where(Document.sha256 == SHA_UPLOAD)
                )
                upload = await s.get(Document, ids["upload"])
                assert upload is not None
                return int(count or 0), upload.source_system
        finally:
            await engine.dispose()

    count, source_system = asyncio.run(_check())
    assert count == 1  # linked, not duplicated
    assert source_system is None  # provenance of the upload untouched


def test_webhook_signature_idempotency_and_events(
    make_client: Callable[..., TestClient],
    world_and_ids: tuple[World, dict[str, Any]],
    database: Database,
    redis_url: str,
) -> None:
    world, _ = world_and_ids
    client = make_client()
    h = bearer(login(client, world, "dmsadmin"))
    prop = _property(client, h)
    body = json.dumps(
        {
            "event": "document.filed",
            "occurred_at": "2026-09-26T09:00:00Z",
            "object_number": "291",
            "document": _doc(9100, "c" * 64, "drive-9100", "Wirtschaftsplan 2027"),
        }
    ).encode()
    url = f"{BASE}/webhook"
    headers = {"content-type": "application/json", "X-Objektakte-Event": "document.filed"}

    assert client.post(url, content=body, headers=headers).status_code == 401
    wrong = {**headers, "X-Objektakte-Signature": sign("falsch", body)}
    assert client.post(url, content=body, headers=wrong).status_code == 401
    signed = {**headers, "X-Objektakte-Signature": sign(SECRET, body)}
    mismatch = {**signed, "X-Objektakte-Event": "object.taken_over"}
    assert client.post(url, content=body, headers=mismatch).status_code == 422

    first = _ok(client.post(url, content=body, headers=signed))
    assert first["status"] == "processed"
    assert first["outcome"] == "created"
    assert first["property_id"] == prop["id"]
    repeat = _ok(client.post(url, content=body, headers=signed))
    assert repeat["status"] == "duplicate"
    assert repeat["document_id"] == first["document_id"]

    # the same document announced again with a new body (other timestamp) is still a duplicate
    body2 = body.replace(b"09:00:00Z", b"09:05:00Z")
    again = _ok(
        client.post(
            url, content=body2, headers={**headers, "X-Objektakte-Signature": sign(SECRET, body2)}
        )
    )
    assert again["status"] == "duplicate"

    taken = json.dumps(
        {
            "event": "object.taken_over",
            "occurred_at": "2026-09-26T10:00:00Z",
            "object_number": "291",
            "document": None,
        }
    ).encode()
    taken_headers = {
        "content-type": "application/json",
        "X-Objektakte-Event": "object.taken_over",
        "X-Objektakte-Signature": sign(SECRET, taken),
    }
    recorded = _ok(client.post(url, content=taken, headers=taken_headers))
    assert (recorded["status"], recorded["outcome"]) == ("processed", "recorded")
    assert _ok(client.post(url, content=taken, headers=taken_headers))["status"] == "duplicate"

    invalid = json.dumps({"event": "document.filed", "object_number": "291"}).encode()
    bad = client.post(
        url,
        content=invalid,
        headers={**headers, "X-Objektakte-Signature": sign(SECRET, invalid)},
    )
    assert bad.status_code == 422

    async def _check() -> tuple[int, int, int]:
        engine = create_app_engine(_configured(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as s:
                docs = await s.scalar(
                    select(func.count(Document.id)).where(
                        Document.source_system == "objektakte", Document.source_id == "9100"
                    )
                )
                links = await s.scalar(
                    select(func.count(DocumentLink.id)).where(
                        DocumentLink.document_id == uuid.UUID(first["document_id"])
                    )
                )
                receipts = await s.scalar(select(func.count(ObjektakteWebhookReceipt.id)))
            async with tenant_transaction(factory, world.tenant_b) as s:
                assert await s.scalar(select(func.count(ObjektakteWebhookReceipt.id))) == 0
            return int(docs or 0), int(links or 0), int(receipts or 0)
        finally:
            await engine.dispose()

    assert asyncio.run(_check()) == (1, 1, 2)

    # without a configured secret every delivery is refused
    off = make_client(objektakte_webhook_secret=None)
    assert off.post(url, content=body, headers=signed).status_code == 401


def _person(client: TestClient, h: dict[str, str], last_name: str) -> tuple[str, str]:
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Anna", "last_name": last_name},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    return str(party["id"]), str(contact["display_name"])


def test_owner_list_proposal_test_run_and_release(
    make_client: Callable[..., TestClient],
    world_and_ids: tuple[World, dict[str, Any]],
    fake: FakeObjektakte,
) -> None:
    """CRM: unit 01 owned by Anna Eins, unit 02 by Anna Zwei, unit 03 without owner. objektakte:
    Anna Eins on 01 (unchanged), Bernd Anders on 02 (conflict), Clara Neu on 03 (new), Dora
    Fremd on "WE 99" (unit unknown). Anna Zwei is then only in the CRM. Expected counts by hand.
    Neither the test run nor the release changes contacts or contracts."""
    world, _ = world_and_ids
    client = make_client()
    h = bearer(login(client, world, "dmsadmin"))
    prop = _property(client, h)
    units = {n: _unit(client, h, prop["id"], n) for n in ("01", "02", "03")}
    one, one_name = _person(client, h, f"Eins{RUN}")
    two, _ = _person(client, h, f"Zwei{RUN}")
    ownership = {
        "kind": "ownership",
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
    }
    for unit, party in ((units["01"], one), (units["02"], two)):
        _ok(
            client.post(
                "/api/v1/contracts",
                json={**ownership, "unit_id": unit, "party_id": party},
                headers=h,
            ),
            201,
        )
    fake.owners = [
        {
            "id": 1,
            "display_name": one_name,
            "unit_labels": ["WE 01"],
            "share": "100/1000",
            "email_masked": "a***@example.org",
            "iban_masked": "DE89 **** **** 3000",
        },
        {"id": 2, "display_name": "Bernd Anders", "unit_labels": ["02"], "share": None},
        {"id": 3, "display_name": "Clara Neu", "unit_labels": ["WE 03"], "share": None},
        {"id": 4, "display_name": "Dora Fremd", "unit_labels": ["WE 99"], "share": None},
    ]
    contacts_before = _ok(client.get("/api/v1/contacts", headers=h))["total"]

    listing = _ok(client.get(f"{BASE}/objects/291/owners", headers=h))
    assert listing["total"] == 4
    assert "iban_masked" not in listing["items"][0]
    assert "email_masked" not in listing["items"][0]

    reader = bearer(login(client, world, "dmsreader"))
    denied = client.post(
        f"{BASE}/objects/291/person-proposals", json={"kind": "owners"}, headers=reader
    )
    assert denied.status_code == 403

    proposal = _ok(
        client.post(f"{BASE}/objects/291/person-proposals", json={"kind": "owners"}, headers=h),
        201,
    )
    assert proposal["status"] == "tested"
    assert proposal["writes_master_data"] is False
    counts = proposal["summary"]["counts"]
    assert (
        counts["unchanged"],
        counts["conflict"],
        counts["new"],
        counts["unit_unknown"],
        counts["crm_only"],
    ) == (1, 1, 1, 1, 1)
    assert not any("iban" in json.dumps(r) for r in proposal["rows"])
    conflict = next(r for r in proposal["rows"] if r["status"] == "conflict")
    assert conflict["display_name"] == "Bernd Anders"

    rerun = _ok(client.post(f"{BASE}/person-proposals/{proposal['id']}/test-run", headers=h))
    assert rerun["summary"]["counts"] == counts

    assert (
        client.post(f"{BASE}/person-proposals/{proposal['id']}/approve", headers=reader).status_code
        == 403
    )
    released = _ok(
        client.post(
            f"{BASE}/person-proposals/{proposal['id']}/approve",
            json={"note": "Abgleich geprüft"},
            headers=h,
        )
    )
    assert released["status"] == "approved"
    assert released["decision_note"] == "Abgleich geprüft"
    twice = client.post(f"{BASE}/person-proposals/{proposal['id']}/approve", headers=h)
    assert twice.status_code == 409
    assert twice.json()["code"] == "MHVP-OAK-0004"
    assert (
        client.post(f"{BASE}/person-proposals/{proposal['id']}/test-run", headers=h).status_code
        == 409
    )

    listed = _ok(client.get(f"{BASE}/person-proposals", params={"object_number": "291"}, headers=h))
    assert [p["id"] for p in listed["items"]] == [proposal["id"]]
    assert _ok(client.get("/api/v1/contacts", headers=h))["total"] == contacts_before

    hb = bearer(login(client, world, "dmsother"))
    assert client.get(f"{BASE}/person-proposals/{proposal['id']}", headers=hb).status_code in (
        403,
        404,
    )
    assert _ok(client.get(f"{BASE}/person-proposals", headers=hb))["total"] == 0
