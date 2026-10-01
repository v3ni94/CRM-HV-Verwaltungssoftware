"""Wave 3 documents (Q03): presigned transfer (S12-06), temporary objects (M6-08), ZIP bulk
upload as import_run (M6-03), redacted copies (M25-01), holds and permanent records per legal
entity (S711-06), tenant intake address (M6-04) and the Drive Changes API (M6-05)."""

import asyncio
import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.documents import drive_changes, intake_address
from mhvp.documents.blobs import BlobStore
from mhvp.documents.dms import GoogleDriveStore
from mhvp.documents.tasks import cleanup_tmp_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import BUCKET, _ok, _pdf, _settings, _upload

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q3-{RUN}", name=f"Q03 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q3b-{RUN}", name=f"Q03b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("q3admin", a, "tenant_admin"),
            ("q3second", a, "tenant_admin"),
            ("q3caretaker", a, "caretaker"),
            ("q3other", b, "tenant_admin"),
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


def _h(client: TestClient, world: World, name: str) -> dict[str, str]:
    return bearer(login(client, world, name))


def _property(c: TestClient, h: dict[str, str], number: str, kind: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"Objekt {number}",
        "management_type": kind,
        "street": "Rheinpromenade",
        "house_number": "13",
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    return _ok(c.post("/api/v1/properties", json=body, headers=h))  # type: ignore[no-any-return]


# S12-06 and M6-08 --------------------------------------------------------------------------


def test_presigned_upload_complete_and_download_url(client: TestClient, world: World) -> None:
    h = _h(client, world, "q3admin")
    refused = client.post(
        "/api/v1/documents/uploads",
        json={"filename": "x.exe", "mime_type": "application/x-msdownload", "size": 10},
        headers=h,
    )
    assert refused.status_code == 422
    too_big = client.post(
        "/api/v1/documents/uploads",
        json={"filename": "a.pdf", "mime_type": "application/pdf", "size": 10_000_000},
        headers=h,
    )
    assert too_big.status_code == 422
    assert (
        client.post("/api/v1/documents/uploads", json={"filename": "a.pdf"}, headers=h).status_code
        == 422
    )
    data = _pdf(f"Direkt {RUN}")
    intent = _ok(
        client.post(
            "/api/v1/documents/uploads",
            json={"filename": "direkt.pdf", "mime_type": "application/pdf", "size": len(data)},
            headers=h,
        )
    )
    assert intent["method"] == "PUT"
    assert "X-Amz-Signature" in intent["url"]
    assert intent["headers"] == {"Content-Type": "application/pdf"}
    complete = f"/api/v1/documents/uploads/{intent['upload_id']}/complete"
    body = {"filename": "direkt.pdf", "mime_type": "application/pdf", "title": "Direkt"}
    missing = client.post(complete, json=body, headers=h)
    assert missing.status_code == 404  # nothing staged yet
    # The browser PUTs to the signed URL; in the test the object is staged directly.
    s3c = boto3.client("s3", region_name="us-east-1")
    key = BlobStore.tmp_key(world.tenant_a, uuid.UUID(intent["upload_id"]))
    s3c.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType="application/pdf")
    other = _h(client, world, "q3other")
    assert client.post(complete, json=body, headers=other).status_code == 404  # other tenant key
    doc = _ok(client.post(complete, json=body, headers=h))
    assert doc["title"] == "Direkt"
    assert doc["size"] == len(data)
    assert "Contents" not in s3c.list_objects_v2(Bucket=BUCKET, Prefix="tmp/")
    url = _ok(client.get(f"/api/v1/documents/{doc['id']}/download-url", headers=h), 200)
    assert "X-Amz-Signature" in url["url"]
    assert url["expires_in"] == 300
    assert "direkt.pdf" in url["url"]
    assert (
        client.get(f"/api/v1/documents/{doc['id']}/download-url", headers=other).status_code == 404
    )
    caretaker = _h(client, world, "q3caretaker")
    assert (
        client.get(f"/api/v1/documents/{doc['id']}/download-url", headers=caretaker).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/documents/uploads",
            json={"filename": "a.pdf", "mime_type": "application/pdf", "size": 5},
            headers=caretaker,
        ).status_code
        == 403
    )


def test_tmp_cleanup_removes_only_old_temporary_objects(
    client: TestClient, database: Database, redis_url: str
) -> None:
    s3c = boto3.client("s3", region_name="us-east-1")
    s3c.put_object(Bucket=BUCKET, Key="tmp/t/uploads/old", Body=b"x")
    s3c.put_object(Bucket=BUCKET, Key="tenants/t/documents/keep", Body=b"x")
    settings = _settings(database, redis_url)
    fresh = cleanup_tmp_once(settings)
    assert fresh["removed"] == 0  # younger than one day
    result = cleanup_tmp_once(settings, now=datetime.now(UTC) + timedelta(days=2))
    assert result == {"lifecycle": 1, "removed": 1}
    keys = [o["Key"] for o in s3c.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert keys == ["tenants/t/documents/keep"]
    rules = s3c.get_bucket_lifecycle_configuration(Bucket=BUCKET)["Rules"]
    assert rules[0]["Filter"]["Prefix"] == "tmp/"
    assert rules[0]["Expiration"]["Days"] == 1


# M6-03 ------------------------------------------------------------------------------------


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_zip_import_creates_import_run_and_skips_refused_files(
    client: TestClient, world: World
) -> None:
    h = _h(client, world, "q3admin")
    prop = _property(client, h, "931", "rental")
    archive = _zip(
        {
            "ordner/rechnung.pdf": _pdf(f"ZIP Rechnung {RUN}"),
            "notiz.txt": b"Notiz aus dem Archiv",
            "falsch.pdf": b"kein pdf",
            "programm.exe": b"MZ",
            "__MACOSX/._rechnung.pdf": b"x",
        }
    )
    links = json.dumps([{"entity_type": "property", "entity_id": prop["id"]}])
    result = _ok(
        client.post(
            "/api/v1/documents/zip-import",
            files={"file": ("belege.zip", archive, "application/zip")},
            data={"links": links},
            headers=h,
        )
    )
    assert len(result["created"]) == 2
    assert result["import_run_id"]
    assert sorted(x["name"] for x in result["skipped"]) == ["falsch.pdf", "programm.exe"]
    first = _ok(client.get(f"/api/v1/documents/{result['created'][0]}", headers=h), 200)
    assert first["source"] == "import"
    assert first["links"][0]["entity_id"] == prop["id"]
    broken = client.post(
        "/api/v1/documents/zip-import",
        files={"file": ("x.zip", b"no zip", "application/zip")},
        headers=h,
    )
    assert broken.status_code == 422
    caretaker = _h(client, world, "q3caretaker")
    assert (
        client.post(
            "/api/v1/documents/zip-import",
            files={"file": ("belege.zip", archive, "application/zip")},
            headers=caretaker,
        ).status_code
        == 403
    )
    other = _h(client, world, "q3other")
    assert client.get(f"/api/v1/documents/{result['created'][0]}", headers=other).status_code == 404


# M25-01 -----------------------------------------------------------------------------------


def test_redacted_copy_with_protocol_and_four_eyes_release(
    client: TestClient, world: World
) -> None:
    h = _h(client, world, "q3admin")
    second = _h(client, world, "q3second")
    original = _ok(_upload(client, h, "beleg.txt", b"Beleg Name Mustermann IBAN", "text/plain"))
    url = f"/api/v1/documents/{original['id']}/redactions"
    form = {
        "reason": "Daten Dritter",
        "scope": "Name und IBAN",
        "steps": json.dumps(["Name geschwärzt", "IBAN geschwärzt"]),
    }
    same = client.post(
        url,
        files={"file": ("beleg.txt", b"Beleg Name Mustermann IBAN", "text/plain")},
        data=form,
        headers=h,
    )
    assert same.status_code == 422  # identical to the original
    no_steps = client.post(
        url,
        files={"file": ("b.txt", b"Beleg XXX", "text/plain")},
        data={**form, "steps": "[]"},
        headers=h,
    )
    assert no_steps.status_code == 422
    red = _ok(
        client.post(
            url,
            files={"file": ("beleg.txt", b"Beleg Name XXXX IBAN XXXX", "text/plain")},
            data=form,
            headers=h,
        )
    )
    assert red["steps"] == ["Name geschwärzt", "IBAN geschwärzt"]
    assert red["released_at"] is None
    copy = _ok(client.get(f"/api/v1/documents/{red['copy_document_id']}", headers=h), 200)
    assert copy["visibility"] == ["internal"]
    assert any(
        x["entity_type"] == "document" and x["entity_id"] == original["id"]
        for x in copy["links"]
        if x["role"] == "generated"
    )
    unchanged = _ok(client.get(f"/api/v1/documents/{original['id']}", headers=h), 200)
    assert unchanged["sha256"] == original["sha256"]
    release = f"{url}/{red['id']}/release"
    own = client.post(release, json={"visibility": ["owner"]}, headers=h)
    assert own.status_code == 403  # four eyes
    assert (
        client.post(release, json={"visibility": ["internal"]}, headers=second).status_code == 422
    )
    done = _ok(client.post(release, json={"visibility": ["owner"]}, headers=second), 200)
    assert done["released_visibility"] == ["owner"]
    assert _ok(client.get(f"/api/v1/documents/{red['copy_document_id']}", headers=h), 200)[
        "visibility"
    ] == ["owner"]
    assert client.post(release, json={"visibility": ["owner"]}, headers=second).status_code == 409
    listed = _ok(client.get(url, headers=h), 200)
    assert [x["id"] for x in listed] == [red["id"]]
    other = _h(client, world, "q3other")
    assert client.get(url, headers=other).status_code == 404
    # The original with a redacted copy cannot be deleted before the copy.
    blocked = client.delete(f"/api/v1/documents/{original['id']}", headers=h)
    assert blocked.status_code == 409


# S711-06 ----------------------------------------------------------------------------------


def test_hold_kind_propagates_and_permanent_record_per_legal_entity(
    client: TestClient, world: World
) -> None:
    h = _h(client, world, "q3admin")
    categories = _ok(client.get("/api/v1/document-categories", headers=h), 200)
    division = next(c for c in categories if c["code"] == "declaration_of_division")
    weg = _property(client, h, "932", "hoa")
    rental = _property(client, h, "933", "rental")
    for prop, expected in ((weg, True), (rental, False)):
        doc = _ok(
            _upload(
                client,
                h,
                "te.txt",
                f"Teilungserklärung {prop['number']}".encode(),
                "text/plain",
                category_id=division["id"],
                links=json.dumps([{"entity_type": "property", "entity_id": prop["id"]}]),
            )
        )
        assert doc["permanent_record"] is expected
    # Clearing the permanent record flag needs documents:approve (admins have it).
    patched = _ok(
        client.patch(f"/api/v1/documents/{doc['id']}", json={"permanent_record": True}, headers=h),
        200,
    )
    assert patched["permanent_record"] is True
    assert (
        client.patch(
            f"/api/v1/documents/{doc['id']}", json={"permanent_record": None}, headers=h
        ).status_code
        == 422
    )
    # Hold with a kind; it also keeps a document derived from the held one.
    original = _ok(_upload(client, h, "streit.txt", b"Beweis", "text/plain"))
    held = _ok(
        client.post(
            f"/api/v1/documents/{original['id']}/hold",
            json={"reason": "Rechtsstreit Beispiel", "kind": "litigation"},
            headers=h,
        ),
        200,
    )
    assert held["retention_hold_kind"] == "litigation"
    bad = client.post(
        f"/api/v1/documents/{original['id']}/hold",
        json={"reason": "Sperre xyz", "kind": "x"},
        headers=h,
    )
    assert bad.status_code == 422
    derived = _ok(
        _upload(
            client,
            h,
            "kopie.txt",
            b"Beweis Kopie",
            "text/plain",
            links=json.dumps(
                [{"entity_type": "document", "entity_id": original["id"], "role": "generated"}]
            ),
        )
    )
    refused = client.delete(f"/api/v1/documents/{derived['id']}", headers=h)
    assert refused.status_code == 409
    assert "verbundenen Dokument" in refused.json()["detail"]
    cleared = _ok(
        client.request(
            "DELETE",
            f"/api/v1/documents/{original['id']}/hold",
            json={"reason": "Verfahren beendet"},
            headers=h,
        ),
        200,
    )
    assert cleared["retention_hold_kind"] is None


def test_profile_per_legal_entity_kind(client: TestClient, world: World) -> None:
    h = _h(client, world, "q3admin")
    base = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"q3_{RUN}",
                "legal_basis": "Testprofil Basis",
                "retention_years": 6,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )
    hoa = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"q3_{RUN}",
                "legal_entity_kind": "hoa",
                "legal_basis": "Testprofil GdWE",
                "retention_years": 10,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )
    category = _ok(
        client.post(
            "/api/v1/document-categories",
            json={"code": f"q3c_{RUN}".lower()[:63], "name": "Q3"},
            headers=h,
        )
    )
    _ok(
        client.patch(
            f"/api/v1/document-categories/{category['id']}",
            json={"retention_profile_id": base["id"]},
            headers=h,
        ),
        200,
    )
    weg = _property(client, h, "934", "hoa")
    rental = _property(client, h, "935", "rental")
    docs = {}
    for prop in (weg, rental):
        docs[prop["number"]] = _ok(
            _upload(
                client,
                h,
                "p.txt",
                f"Profil {prop['number']}".encode(),
                "text/plain",
                category_id=category["id"],
                links=json.dumps([{"entity_type": "property", "entity_id": prop["id"]}]),
            )
        )
    assert docs["934"]["retention_profile_id"] == hoa["id"]
    assert docs["935"]["retention_profile_id"] == base["id"]


# M6-04 ------------------------------------------------------------------------------------


def test_intake_address_config_and_classification(client: TestClient, world: World) -> None:
    h = _h(client, world, "q3admin")
    empty = _ok(client.get("/api/v1/document-intake-address", headers=h), 200)
    assert empty["configured"] is False
    body = {
        "mailbox_address": "Belege@Example.de",
        "allowed_senders": ["@muellerhv.de", "chef@x.de"],
    }
    first = _ok(client.put("/api/v1/document-intake-address", json=body, headers=h), 200)
    assert first["address"].startswith("belege+")
    assert first["address"].endswith("@example.de")
    again = _ok(client.put("/api/v1/document-intake-address", json=body, headers=h), 200)
    assert again["address"] == first["address"]  # token kept
    rotated = _ok(
        client.put("/api/v1/document-intake-address?rotate=true", json=body, headers=h), 200
    )
    assert rotated["address"] != first["address"]
    assert (
        client.put(
            "/api/v1/document-intake-address", json={"mailbox_address": "kein-mail"}, headers=h
        ).status_code
        == 422
    )
    caretaker = _h(client, world, "q3caretaker")
    assert (
        client.put("/api/v1/document-intake-address", json=body, headers=caretaker).status_code
        == 403
    )
    other = _h(client, world, "q3other")
    assert (
        _ok(client.get("/api/v1/document-intake-address", headers=other), 200)["configured"]
        is False
    )
    config = intake_address.IntakeAddress("belege@example.de", "abc", ["@muellerhv.de"])
    assert intake_address.classify(config, ["Belege <belege+abc@example.de>"]) == "own"
    assert intake_address.classify(config, ["belege+zzz@example.de"]) == "foreign"
    assert intake_address.classify(config, ["info@example.de"]) is None
    assert intake_address.sender_allowed(config, "Timo <timo@muellerhv.de>")
    assert not intake_address.sender_allowed(config, "fremd@example.org")


# M6-05 ------------------------------------------------------------------------------------


def test_drive_changes_cursor_and_removed_mirror(client: TestClient, world: World) -> None:
    h = _h(client, world, "q3admin")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.endswith("/startPageToken"):
            return httpx.Response(200, json={"startPageToken": "10"})
        assert request.url.params["pageToken"] == "10"
        return httpx.Response(
            200,
            json={
                "newStartPageToken": "11",
                "changes": [
                    {"fileId": "drive-file-1", "removed": False, "file": {"trashed": True}},
                    {"fileId": "unknown", "removed": True},
                ],
            },
        )

    async def run() -> tuple[Any, Any]:
        from mhvp.core.db.engine import create_app_engine, create_session_factory
        from mhvp.core.db.tenancy import tenant_transaction
        from mhvp.documents.models import DmsConnection, DocumentMirror, MirrorStatus, StorageKind

        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        doc = _ok(_upload(client, h, "drive.txt", b"Drive Datei", "text/plain"))
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                connection = DmsConnection(
                    tenant_id=world.tenant_a,
                    kind=StorageKind.GOOGLE_DRIVE,
                    enabled=False,
                    secret=json.dumps({"refresh_token": "r"}),
                    options={},
                )
                session.add(connection)
                session.add(
                    DocumentMirror(
                        tenant_id=world.tenant_a,
                        document_id=uuid.UUID(doc["id"]),
                        kind=StorageKind.GOOGLE_DRIVE,
                        status=MirrorStatus.DONE,
                        external_ref="drive-file-1",
                    )
                )
                await session.flush()
                store = GoogleDriveStore("root", "c", "s", "r", http)
                first = await drive_changes.sync_tenant(session, world.tenant_a, store, connection)
                second = await drive_changes.sync_tenant(session, world.tenant_a, store, connection)
                assert connection.options[drive_changes.CURSOR_KEY] == "11"
                mirror = await session.scalar(
                    select(DocumentMirror).where(DocumentMirror.external_ref == "drive-file-1")
                )
                assert mirror is not None
                assert mirror.last_error == drive_changes.REMOVED_NOTE
                assert mirror.status is MirrorStatus.DONE  # nothing deleted, nothing re-uploaded
                await session.delete(mirror)
                await session.delete(connection)
            return first, second
        finally:
            await http.aclose()
            await engine.dispose()

    first, second = asyncio.run(run())
    assert first.started is True
    assert first.changes == 0
    assert (second.changes, second.matched, second.removed) == (2, 1, 1)
    # Endpoint without an enabled Drive connection answers 422, without permission 403.
    assert client.post("/api/v1/dms-changes/google-drive/sync", headers=h).status_code == 422
    caretaker = _h(client, world, "q3caretaker")
    assert (
        client.post("/api/v1/dms-changes/google-drive/sync", headers=caretaker).status_code == 403
    )
