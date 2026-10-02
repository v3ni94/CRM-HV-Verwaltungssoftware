"""GAG-12 (AH08): `/api/v1/objektakte/import-runs` (list, clear OCR cache). Own test world with
prefix `h08`: tenant admin, read only user and a second tenant (RLS, 403, 404, 422)."""

import asyncio
import io
import zipfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
IMPORTS = "/api/v1/objektakte/imports"
RUNS = "/api/v1/objektakte/import-runs"

BASE_DUMP = r"""
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


DOCUMENT_DUMP = (
    BASE_DUMP
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


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"h08-{RUN}", name=f"H08 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"h08b-{RUN}", name=f"H08 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("h08admin", a, "tenant_admin"),
            ("h08reader", a, "read_only"),
            ("h08other", b, "tenant_admin"),
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


def _apply(client: TestClient, headers: dict[str, str]) -> str:
    out = _ok(
        client.post(
            IMPORTS,
            params={"mode": "apply"},
            files={"file": ("dump.sql", DOCUMENT_DUMP.encode("utf-8"), "application/sql")},
            headers=headers,
        )
    )
    return str(out["import_run_id"])


def _cache_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("cache-1001.txt", "Volltext aus dem OCR-Cache.")
    return buffer.getvalue()


def _search_hits(client: TestClient, headers: dict[str, str]) -> int:
    out = _ok(client.get("/api/v1/documents", params={"page": 1, "page_size": 50}, headers=headers))
    hits = 0
    for item in out["items"]:
        detail = _ok(client.get(f"/api/v1/documents/{item['id']}", headers=headers))
        hits += 1 if detail.get("text_status") == "extracted" else 0
    return hits


def test_list_runs_paged_with_counts_and_tenant_separation(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "h08admin", world.tenant_a))
    run_id = _apply(client, admin)
    response = client.get(RUNS, params={"page": 1, "page_size": 10}, headers=admin)
    items = _ok(response)
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["X-Page-Size"] == "10"
    assert items[0]["id"] == run_id
    assert items[0]["status"] == "applied"
    assert items[0]["created_total"] > 0
    assert items[0]["cache_documents"] == 0
    other = bearer(login(client, world, "h08other", world.tenant_b))
    assert _ok(client.get(RUNS, headers=other)) == []
    reader = bearer(login(client, world, "h08reader", world.tenant_a))
    assert len(_ok(client.get(RUNS, headers=reader))) == 1
    assert _ok(client.get(RUNS, params={"filter[status]": "undone"}, headers=admin)) == []


def test_list_runs_rejects_unknown_parameters(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "h08admin", world.tenant_a))
    assert client.get(RUNS, params={"bogus": "1"}, headers=admin).status_code == 422
    assert client.get(RUNS, params={"filter[nope]": "1"}, headers=admin).status_code == 422
    assert client.get(RUNS, params={"page": 0}, headers=admin).status_code == 422
    assert client.get(RUNS).status_code == 401


def test_clear_ocr_cache_resets_text_and_is_guarded(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "h08admin", world.tenant_a))
    run_id = list_first = _ok(client.get(RUNS, headers=admin))[0]["id"]
    assert run_id == list_first
    filled = _ok(
        client.post(
            f"{IMPORTS}/{run_id}/ocr-cache",
            files={"file": ("c.zip", _cache_zip(), "application/zip")},
            headers=admin,
        )
    )
    assert filled["matched"] == 1
    assert _search_hits(client, admin) == 1
    assert _ok(client.get(RUNS, headers=admin))[0]["cache_documents"] == 1

    reader = bearer(login(client, world, "h08reader", world.tenant_a))
    assert client.delete(f"{RUNS}/{run_id}/ocr-cache", headers=reader).status_code == 403
    other = bearer(login(client, world, "h08other", world.tenant_b))
    assert client.delete(f"{RUNS}/{run_id}/ocr-cache", headers=other).status_code == 404
    assert _search_hits(client, admin) == 1

    out = _ok(client.delete(f"{RUNS}/{run_id}/ocr-cache", headers=admin))
    assert out["cleared"] == 1
    assert _search_hits(client, admin) == 0
    assert _ok(client.get(RUNS, headers=admin))[0]["cache_documents"] == 0
    again = _ok(client.delete(f"{RUNS}/{run_id}/ocr-cache", headers=admin))
    assert again["cleared"] == 0


def test_clear_ocr_cache_unknown_run_is_404(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "h08admin", world.tenant_a))
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.delete(f"{RUNS}/{missing}/ocr-cache", headers=admin).status_code == 404
