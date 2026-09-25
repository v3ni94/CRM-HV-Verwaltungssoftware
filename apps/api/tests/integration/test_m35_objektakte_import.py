"""M35 Stufe 1/2 acceptance: `/api/v1/objektakte/imports` preview/apply with a synthetic dump,
idempotent re-apply (rule 0.1.12), tenant separation (RLS), document/OCR-cache takeover and a
download of a migrated Drive document through the existing download path (fake Drive store)."""

import asyncio
import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte/imports"
DUMP = r"""
INSERT INTO `objects_managedobject` (`id`,`object_number`,`name`,`street`,`house_number`,
`postal_code`,`city`,`management_type`)
VALUES (11,'711','Haus Musterstraße','Musterstraße','12','40721','Hilden','weg');

INSERT INTO `objects_unit` (`id`,`object_id`,`unit_number`,`unit_label`,`unit_type`)
VALUES (101,11,'1','EG links','apartment');

INSERT INTO `parties_owner` (`id`,`type`,`first_name`,`last_name`,`company_name`,`search_name`)
VALUES (201,'natural_person','Erika','Musterfrau',NULL,'Musterfrau, Erika');

INSERT INTO `parties_ownerunitassignment` (`id`,`owner_id`,`unit_id`,`valid_from`,`valid_to`,
`share`)
VALUES (401,201,101,'2020-01-01',NULL,'1.000000');
"""


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"oa-{RUN}", name=f"OA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"oab-{RUN}", name=f"OA B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("oaadmin", a, "tenant_admin"),
            ("oareader", a, "read_only"),
            ("oaother", b, "tenant_admin"),
        ):
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _upload(client: TestClient, headers: dict[str, str], mode: str) -> Any:
    return client.post(
        BASE,
        params={"mode": mode},
        files={"file": ("dump.sql", DUMP.encode("utf-8"), "application/sql")},
        headers=headers,
    )


def test_preview_reports_counts_and_new_property(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    out = _ok(_upload(client, admin, "preview"))
    assert out["mode"] == "preview"
    assert out["counts"]["objects_managedobject"] == 1
    assert out["new_properties"] == 1
    assert out["matched_properties"] == 0
    assert out["duplicates"] == {}


def test_apply_is_idempotent_by_source_id(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    first = _ok(_upload(client, admin, "apply"))
    assert first["mode"] == "apply"
    assert first["created"]["property"] == 1
    assert first["created"]["unit"] == 1
    assert first["created"]["contact"] == 1
    assert first["created"]["parties_ownerunitassignment"] == 1

    second = _ok(_upload(client, admin, "apply"))
    assert second["created"] == {}
    assert second["skipped_duplicates"]["objects_managedobject"] == 1
    assert second["skipped_duplicates"]["objects_unit"] == 1
    assert second["skipped_duplicates"]["parties_owner"] == 1
    assert second["skipped_duplicates"]["parties_ownerunitassignment"] == 1

    run_id = second["import_run_id"]
    fetched = _ok(client.get(f"{BASE}/{run_id}", headers=admin))
    assert fetched["import_run_id"] == run_id


def test_read_only_member_cannot_apply(client: TestClient, world: World) -> None:
    reader = bearer(login(client, world, "oareader", world.tenant_a))
    response = _upload(client, reader, "preview")
    assert response.status_code == 403


def test_other_tenant_cannot_read_import_run(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    result = _ok(_upload(client, admin, "apply"))
    run_id = result["import_run_id"]

    other = bearer(login(client, world, "oaother", world.tenant_b))
    response = client.get(f"{BASE}/{run_id}", headers=other)
    assert response.status_code == 404


# --- Stufe 2: documents, categories, drive nodes, review cases, OCR cache -------------------

DOCUMENT_DUMP = (
    DUMP
    + r"""
INSERT INTO `documents_documentcategory` (`code`,`folder_name`,`display_name`,`sort_order`)
VALUES ('02','02_Stammakte','Stammakte',20);

INSERT INTO `documents_documentsubfolder` (`id`,`category_code`,`code`,`folder_name`,
`display_name`,`sort_order`)
VALUES (51,'02','01','Vertraege','Verträge',10);

INSERT INTO `documents_documenttype` (`id`,`category_code`,`subfolder_id`,`code`,`name`,
`requires_period`,`requires_owner`,`requires_tenant`)
VALUES (71,'02',51,'vertrag_hv','Verwaltervertrag',0,1,0);

INSERT INTO `drive_drivenode` (`id`,`object_id`,`parent_node_id`,`node_kind`,`list_type`,`year`,
`drive_name`,`drive_file_id`,`drive_parent_id`,`status`)
VALUES (901,11,NULL,'main_folder',NULL,NULL,'02_Stammakte','drv-901','drv-root','active');

INSERT INTO `documents_document` (`id`,`object_id`,`sha256`,`size_bytes`,`mime_type`,
`original_name`,`current_name`,`drive_file_id`,`drive_node_id`,`status`,
`duplicate_of_document_id`,`category_code`,`subfolder_id`,`document_type_id`,`ocr_cache_key`)
VALUES (1001,11,'a1b2c3',20480,'application/pdf','vertrag.pdf','Verwaltervertrag.pdf',
'drv-file-1001',901,'ocr_done',NULL,'02',51,71,'cache-1001');

INSERT INTO `review_reviewcase` (`id`,`document_id`,`case_type`,`candidates`,`proposed_action`,
`priority`,`status`,`snoozed_until`)
VALUES (2001,1001,'category_ambiguous',NULL,NULL,80,'open',NULL);

INSERT INTO `review_reviewdecision` (`id`,`review_case_id`,`document_id`,`before_state`,
`after_state`)
VALUES (3001,2001,1001,NULL,'{"category":"02"}');
"""
)


def _upload_documents(client: TestClient, headers: dict[str, str], mode: str) -> Any:
    return client.post(
        BASE,
        params={"mode": mode},
        files={"file": ("dump.sql", DOCUMENT_DUMP.encode("utf-8"), "application/sql")},
        headers=headers,
    )


def test_document_preview_reports_document_and_review_counts(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    out = _ok(_upload_documents(client, admin, "preview"))
    assert out["counts"]["documents_document"] == 1
    assert out["counts"]["review_reviewcase"] == 1
    assert out["open_review_cases"] == 1
    assert out["documents_without_property"] == 0
    assert out["unmatched_drive_nodes"] == 0


def test_document_apply_is_idempotent_then_updates_on_changed_row(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    first = _ok(_upload_documents(client, admin, "apply"))
    assert first["created"]["documents_document"] == 1
    assert first["created"]["documents_documentcategory"] == 1
    assert first["created"]["documents_documenttype"] == 1
    assert first["created"]["drive_drivenode"] == 1
    assert first["created"]["review_reviewcase"] == 1
    assert first["created"]["review_reviewdecision"] == 1

    second = _ok(_upload_documents(client, admin, "apply"))
    assert second["created"] == {}
    assert second["skipped_duplicates"]["documents_document"] == 1
    assert second["updated"] == {}

    changed_dump = DOCUMENT_DUMP.replace("'ocr_done'", "'filed'")
    changed = client.post(
        BASE,
        params={"mode": "apply"},
        files={"file": ("dump.sql", changed_dump.encode("utf-8"), "application/sql")},
        headers=admin,
    )
    out = _ok(changed)
    assert out["updated"]["documents_document"] == 1
    assert out["created"] == {}


def test_ocr_cache_zip_fills_text_and_marks_extracted(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    apply_result = _ok(_upload_documents(client, admin, "apply"))
    run_id = apply_result["import_run_id"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("cache-1001.txt", "Verwaltervertrag Volltext aus dem OCR-Cache.")
        zf.writestr("cache-unknown.txt", "gehört zu keinem übernommenen Dokument.")
    buffer.seek(0)

    response = client.post(
        f"{BASE}/{run_id}/ocr-cache",
        files={"file": ("ocr-cache.zip", buffer.read(), "application/zip")},
        headers=admin,
    )
    out = _ok(response)
    assert out["matched"] == 1
    assert out["unmatched_count"] == 1
    assert "cache-unknown" in out["unmatched_keys"]

    documents = _ok(
        client.get("/api/v1/documents", params={"page": 1, "page_size": 20}, headers=admin)
    )
    migrated = next(d for d in documents["items"] if d["filename"] == "Verwaltervertrag.pdf")
    fetched = _ok(client.get(f"/api/v1/documents/{migrated['id']}", headers=admin))
    assert fetched["text_status"] == "extracted"


def test_ocr_cache_zip_skips_entries_over_the_size_limit(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sicherheitsreview 2026-09-25, Befund 3: an oversized entry (a synthetic zip bomb style
    upload) is rejected by `ZipInfo.file_size` before `archive.read()`, counted as
    `skipped_too_large`, never matched or decompressed."""
    from mhvp.objektakte import routers as objektakte_routers

    monkeypatch.setattr(objektakte_routers, "MAX_OCR_ENTRY_BYTES", 5)

    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    apply_result = _ok(_upload_documents(client, admin, "apply"))
    run_id = apply_result["import_run_id"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("cache-1001.txt", "Verwaltervertrag Volltext, länger als das Test-Limit.")
    buffer.seek(0)

    response = client.post(
        f"{BASE}/{run_id}/ocr-cache",
        files={"file": ("ocr-cache.zip", buffer.read(), "application/zip")},
        headers=admin,
    )
    out = _ok(response)
    assert out["matched"] == 0
    assert out["skipped_too_large"] == 1
    assert out["unmatched_count"] == 0


class _FakeDrive:
    """Minimal Google Drive endpoint faking the download of a migrated document's original
    (M35 Stufe 2 acceptance: a download through the existing document download path, no local
    copy, `storage_ref` is the plain objektakte Drive file id, docs/plans/M35-objektakte-
    uebernahme.md section 4 item 1)."""

    def __init__(self, content: bytes) -> None:
        self.content = content

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://oauth2.googleapis.com/token"):
            return httpx.Response(200, json={"access_token": "drive-token"})
        if url.startswith("https://www.googleapis.com/drive/v3/files/drv-file-1001"):
            assert request.headers["authorization"] == "Bearer drive-token"
            return httpx.Response(200, content=self.content)
        return httpx.Response(404)


def test_download_migrated_document_through_fake_drive_store(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = bearer(login(client, world, "oaadmin", world.tenant_a))
    _ok(_upload_documents(client, admin, "apply"))
    documents = _ok(
        client.get("/api/v1/documents", params={"page": 1, "page_size": 20}, headers=admin)
    )
    migrated = next(d for d in documents["items"] if d["filename"] == "Verwaltervertrag.pdf")

    _ok(
        client.put(
            "/api/v1/dms-connections/google_drive",
            json={
                "enabled": True,
                "secret": json.dumps({"client_secret": "s", "refresh_token": "r"}),
                "options": {"root_folder_id": "root", "client_id": "c"},
            },
            headers=admin,
        ),
        200,
    )

    fake = _FakeDrive(b"%PDF-1.4 Verwaltervertrag Original")
    real_async_client = httpx.AsyncClient

    def fake_async_client(*, timeout: float | None = None) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(fake.handler), timeout=timeout)

    monkeypatch.setattr("mhvp.documents.services.httpx.AsyncClient", fake_async_client)

    response = client.get(f"/api/v1/documents/{migrated['id']}/content", headers=admin)
    assert response.status_code == 200, response.text
    assert response.content == b"%PDF-1.4 Verwaltervertrag Original"
