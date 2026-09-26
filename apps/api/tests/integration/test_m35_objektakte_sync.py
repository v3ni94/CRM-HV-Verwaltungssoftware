"""M35 Stufe 5 acceptance: `/api/v1/objektakte/sync` differential import. Idempotent (a second
run over the same complete export changes nothing), differential (only rows at or after the
per tenant water mark are considered), deletion markers instead of physical deletes, tenant
separation of state and markers, and the per tenant switch (default off)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte/sync"

_OBJECT = """
INSERT INTO `objects_managedobject` (`id`,`object_number`,`name`,`street`,`house_number`,
`postal_code`,`city`,`management_type`,`updated_at`)
VALUES (11,'712','Haus Sync','Syncstraße','1','40721','Hilden','weg','2026-09-01 08:00:00');
"""
_UNIT_101 = """
INSERT INTO `objects_unit` (`id`,`object_id`,`unit_number`,`unit_label`,`unit_type`,`updated_at`)
VALUES (101,11,'1','EG links','apartment','2026-09-01 08:00:00');
"""
_UNIT_102 = """
INSERT INTO `objects_unit` (`id`,`object_id`,`unit_number`,`unit_label`,`unit_type`,`updated_at`)
VALUES (102,11,'2','EG rechts','apartment','2026-09-12 09:00:00');
"""
_OWNER = """
INSERT INTO `parties_owner` (`id`,`type`,`first_name`,`last_name`,`company_name`,`search_name`,
`updated_at`)
VALUES (201,'natural_person','Erika','Musterfrau',NULL,'Musterfrau, Erika','2026-09-01 08:00:00');
"""
_ASSIGNMENT = """
INSERT INTO `parties_ownerunitassignment` (`id`,`owner_id`,`unit_id`,`valid_from`,`valid_to`,
`share`,`updated_at`)
VALUES (401,201,101,'2020-01-01',NULL,'1.000000','2026-09-01 08:00:00'),
(402,201,101,'2015-01-01','2019-12-31','1.000000','2026-09-01 08:00:00');
"""
_ASSIGNMENT_401_ONLY = """
INSERT INTO `parties_ownerunitassignment` (`id`,`owner_id`,`unit_id`,`valid_from`,`valid_to`,
`share`,`updated_at`)
VALUES (401,201,101,'2020-01-01',NULL,'1.000000','2026-09-01 08:00:00');
"""


def _document(status: str, updated_at: str) -> str:
    return f"""
INSERT INTO `documents_document` (`id`,`object_id`,`sha256`,`size_bytes`,`mime_type`,
`original_name`,`current_name`,`drive_file_id`,`drive_node_id`,`status`,
`duplicate_of_document_id`,`category_code`,`subfolder_id`,`document_type_id`,`ocr_cache_key`,
`updated_at`)
VALUES (1001,11,'a1b2c3',20480,'application/pdf','sync.pdf','Sync.pdf','drv-sync-1001',NULL,
'{status}',NULL,NULL,NULL,NULL,'cache-sync-1001','{updated_at}');
"""


DUMP_V1 = _OBJECT + _UNIT_101 + _OWNER + _ASSIGNMENT + _document("ocr_done", "2026-09-10 12:00:00")
# Same object/unit/owner rows (older than the water mark), one new unit and a changed document.
DUMP_V2 = (
    _OBJECT
    + _UNIT_101
    + _UNIT_102
    + _OWNER
    + _ASSIGNMENT
    + _document("filed", "2026-09-12 09:00:00")
)
# Assignment row 402 was deleted in objektakte (the table itself still has rows: a mysqldump of
# an emptied table carries no INSERT at all and is skipped by the deletion check on purpose).
DUMP_V3 = (
    _OBJECT
    + _UNIT_101
    + _UNIT_102
    + _OWNER
    + _ASSIGNMENT_401_ONLY
    + _document("filed", "2026-09-12 09:00:00")
)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"os-{RUN}", name=f"OS {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"osb-{RUN}", name=f"OS B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("osadmin", a, "tenant_admin"),
            ("osreader", a, "read_only"),
            ("osclerk", a, "clerk_no_accounting"),
            ("osother", b, "tenant_admin"),
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


def _run(client: TestClient, headers: dict[str, str], dump: str) -> Any:
    return _ok(
        client.post(
            f"{BASE}/runs",
            files={"file": ("objektakte.sql", dump.encode("utf-8"), "application/sql")},
            headers=headers,
        )
    )


def test_differential_import_is_idempotent_and_incremental(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "osadmin", world.tenant_a))

    first = _run(client, admin, DUMP_V1)
    assert first["mode"] == "inline"
    assert first["watermark_before"] is None
    assert first["watermark_after"] == "2026-09-10T12:00:00+00:00"
    assert first["created"]["property"] == 1
    assert first["created"]["unit"] == 1
    assert first["created"]["contact"] == 1
    assert first["created"]["parties_ownerunitassignment"] == 2
    assert first["created"]["documents_document"] == 1
    assert first["deleted_marked"] == {}

    # Idempotent: the same complete export again changes nothing and moves no water mark.
    second = _run(client, admin, DUMP_V1)
    assert second["created"] == {}
    assert second["updated"] == {}
    assert second["deleted_marked"] == {}
    assert second["watermark_before"] == "2026-09-10T12:00:00+00:00"
    assert second["watermark_after"] == "2026-09-10T12:00:00+00:00"
    # Rows older than the water mark are not even considered.
    assert second["considered"]["objects_managedobject"] == 0
    assert second["considered"]["objects_unit"] == 0
    assert second["considered"]["documents_document"] == 1

    state = _ok(client.get(BASE, headers=admin))
    assert state["enabled"] is False
    assert state["last_status"] == "ok"
    assert state["last_source_updated_at"] == "2026-09-10T12:00:00Z"
    assert state["last_report"]["trigger"] == "manual_upload"

    # Differential: only the new unit and the changed document are newer than the water mark;
    # the unit still finds its (unchanged, filtered out) parent object via the CRM's own map.
    third = _run(client, admin, DUMP_V2)
    assert third["considered"]["objects_managedobject"] == 0
    assert third["considered"]["objects_unit"] == 1
    assert third["considered"]["documents_document"] == 1
    assert third["created"] == {"unit": 1}
    assert third["updated"] == {"documents_document": 1}
    assert third["watermark_after"] == "2026-09-12T09:00:00+00:00"

    fourth = _run(client, admin, DUMP_V2)
    assert fourth["created"] == {}
    assert fourth["updated"] == {}


def test_missing_source_rows_are_marked_never_deleted(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "osadmin", world.tenant_a))
    _run(client, admin, DUMP_V2)

    marked = _run(client, admin, DUMP_V3)
    assert marked["deleted_marked"] == {"parties_ownerunitassignment": 1}
    deletions = _ok(client.get(f"{BASE}/deletions", headers=admin))["items"]
    assert [(d["source_table"], d["source_id"]) for d in deletions] == [
        ("parties_ownerunitassignment", "402")
    ]
    assert deletions[0]["target_table"] == "objektakte_party_assignment"

    # A repeated run keeps the single marker; the reappearing row resolves it.
    again = _run(client, admin, DUMP_V3)
    assert again["deleted_marked"] == {}
    resolved = _run(client, admin, DUMP_V2)
    assert resolved["deletions_resolved"] == {"parties_ownerunitassignment": 1}
    assert resolved["created"] == {}
    assert _ok(client.get(f"{BASE}/deletions", headers=admin))["items"] == []
    assert (
        len(
            _ok(
                client.get(f"{BASE}/deletions", params={"include_resolved": "true"}, headers=admin)
            )["items"]
        )
        == 1
    )


def test_sync_state_and_markers_are_tenant_separated(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "osadmin", world.tenant_a))
    _run(client, admin, DUMP_V1)

    other = bearer(login(client, world, "osother", world.tenant_b))
    state_b = _ok(client.get(BASE, headers=other))
    assert state_b["last_status"] == "never"
    assert state_b["last_source_updated_at"] is None
    assert state_b["last_report"] is None
    assert _ok(client.get(f"{BASE}/deletions", headers=other))["items"] == []

    # Tenant B's own first run starts from an empty water mark and creates its own rows.
    run_b = _run(client, other, DUMP_V1)
    assert run_b["watermark_before"] is None
    assert run_b["created"]["property"] == 1


def test_switch_is_off_by_default_and_needs_a_dump_path(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "osadmin", world.tenant_a))
    assert _ok(client.get(BASE, headers=admin))["enabled"] is False

    response = client.put(BASE, json={"enabled": True}, headers=admin)
    assert response.status_code == 422, response.text
    response = client.put(BASE, json={"dump_path": "relative/export.sql"}, headers=admin)
    assert response.status_code == 422, response.text
    response = client.put(BASE, json={"dump_path": "/data/export/objektakte.txt"}, headers=admin)
    assert response.status_code == 422, response.text
    # Sicherheitsreview 26.09.2026: only paths inside Settings.objektakte_dump_dir.
    for outside in ("/etc/objektakte.sql", "/data/objektakte-export/../x/objektakte.sql"):
        response = client.put(BASE, json={"dump_path": outside}, headers=admin)
        assert response.status_code == 422, response.text
        assert "Exportverzeichnis" in response.text

    state = _ok(
        client.put(
            BASE,
            json={"dump_path": "/data/objektakte-export/objektakte.sql", "enabled": True},
            headers=admin,
        )
    )
    assert state["enabled"] is True
    assert state["dump_path"] == "/data/objektakte-export/objektakte.sql"
    _ok(client.put(BASE, json={"enabled": False}, headers=admin))

    reader = bearer(login(client, world, "osreader", world.tenant_a))
    assert client.put(BASE, json={"enabled": True}, headers=reader).status_code == 403
    assert (
        client.post(
            f"{BASE}/runs",
            files={"file": ("objektakte.sql", DUMP_V1.encode("utf-8"), "application/sql")},
            headers=reader,
        ).status_code
        == 403
    )


def test_manual_run_respects_the_switch(client: TestClient, world: World) -> None:
    """Sicherheitsreview 26.09.2026, Befund 7: without a file the queued run needs `enabled`;
    an upload while the import is off is reserved for administrators."""
    admin = bearer(login(client, world, "osadmin", world.tenant_a))
    clerk = bearer(login(client, world, "osclerk", world.tenant_a))
    _ok(
        client.put(
            BASE,
            json={"dump_path": "/data/objektakte-export/objektakte.sql", "enabled": False},
            headers=admin,
        )
    )
    queued = client.post(f"{BASE}/runs", headers=admin)
    assert queued.status_code == 409, queued.text
    assert "ausgeschaltet" in queued.json()["detail"]
    upload = client.post(
        f"{BASE}/runs",
        files={"file": ("objektakte.sql", DUMP_V1.encode("utf-8"), "application/sql")},
        headers=clerk,
    )
    assert upload.status_code == 403, upload.text
    assert "Administratoren" in upload.json()["detail"]
    assert _run(client, admin, DUMP_V1)["mode"] == "inline"

    _ok(client.put(BASE, json={"enabled": True}, headers=admin))
    assert _run(client, clerk, DUMP_V1)["mode"] == "inline"
    _ok(client.put(BASE, json={"enabled": False}, headers=admin))
