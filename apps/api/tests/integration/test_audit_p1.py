"""P1 AP6: change log per entity (Ergänzung 7.2).

One change per entity of the P1 packages (Contact, Property, Building, Unit, Contract) shows
up in ``GET /tenant/audit-log`` filtered by ``entity_type`` and ``entity_id``; the CSV export
carries the same rows. Building (``PUT /buildings/{id}``) and contract versions write their
audit diff as well.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
AUDIT = "/api/v1/tenant/audit-log"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aud-{RUN}", name=f"Audit {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aud2-{RUN}", name=f"Audit2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("audadmin", a, "tenant_admin"),
            ("audcaretaker", a, "caretaker"),
            ("audother", b, "tenant_admin"),
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _audit(client: TestClient, h: dict[str, str], entity_type: str, entity_id: str) -> Any:
    return _ok(
        client.get(AUDIT, params={"entity_type": entity_type, "entity_id": entity_id}, headers=h)
    )


def _assert_change(
    rows: list[dict[str, Any]], entity_type: str, entity_id: str, field: str
) -> None:
    assert rows, f"no audit row for {entity_type} {entity_id}"
    assert all(r["entity_type"] == entity_type and r["entity_id"] == entity_id for r in rows)
    assert any(field in r["changes"] for r in rows), rows


PROPERTY = {"number": "611", "name": f"Audithaus {RUN}", "management_type": "rental"}


def test_contact_change_is_logged(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "audadmin"))
    body = {"kind": "person", "first_name": "Anna", "last_name": f"Audit{RUN}"}
    created = client.post("/api/v1/contacts", json=body, headers=h)
    contact = _ok(created, 201)
    _ok(
        client.put(
            f"/api/v1/contacts/{contact['id']}",
            json=body | {"first_name": "Anna Maria"},
            headers=h | {"If-Match": created.headers["etag"]},
        )
    )
    _assert_change(
        _audit(client, h, "contact", contact["id"]), "contact", contact["id"], "first_name"
    )


def test_property_change_is_logged(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "audadmin"))
    prop = _ok(client.post("/api/v1/properties", json=PROPERTY, headers=h), 201)
    got = client.get(f"/api/v1/properties/{prop['id']}", headers=h)
    _ok(
        client.put(
            f"/api/v1/properties/{prop['id']}",
            json=PROPERTY | {"notes": "Dach 2027"},
            headers=h | {"If-Match": got.headers["etag"]},
        )
    )
    _assert_change(_audit(client, h, "property", prop["id"]), "property", prop["id"], "notes")


def test_unit_change_is_logged(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "audadmin"))
    prop = _ok(client.post("/api/v1/properties", json=PROPERTY | {"number": "612"}, headers=h), 201)
    unit_id = _unit(client, h, prop["id"], "01")
    unit = _ok(client.get(f"/api/v1/units/{unit_id}", headers=h))
    body = {
        "building_id": unit["building_id"],
        "number": "01",
        "label": "WE 01 Dachgeschoss",
        "unit_type": "apartment",
    }
    _ok(client.put(f"/api/v1/units/{unit_id}", json=body, headers=h))
    _assert_change(_audit(client, h, "unit", unit_id), "unit", unit_id, "label")


def test_building_change_is_logged(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "audadmin"))
    prop = _ok(client.post("/api/v1/properties", json=PROPERTY | {"number": "613"}, headers=h), 201)
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )
    got = client.get(f"/api/v1/buildings/{building['id']}", headers=h)
    headers = h | ({"If-Match": got.headers["etag"]} if "etag" in got.headers else {})
    _ok(
        client.put(
            f"/api/v1/buildings/{building['id']}",
            json={"name": "Vorderhaus"},
            headers=headers,
        )
    )
    _assert_change(
        _audit(client, h, "building", building["id"]), "building", building["id"], "name"
    )


def test_contract_change_is_logged(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "audadmin"))
    prop = _ok(client.post("/api/v1/properties", json=PROPERTY | {"number": "614"}, headers=h), 201)
    unit_id = _unit(client, h, prop["id"], "01")
    party, _ = _party(client, h, "Mieter")
    owner, _ = _party(client, h, "Eigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit_id,
                "party_id": party,
                "start_date": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    version = _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/versions",
            json={
                "effective_date": "2026-07-01",
                "dunning_block": True,
                "dunning_block_reason": "Klage",
            },
            headers=h,
        ),
        201,
    )
    rows = _audit(client, h, "contract", contract["id"]) + _audit(
        client, h, "contract", version["id"]
    )
    assert rows
    assert any("dunning_block" in r["changes"] for r in rows), rows


def test_audit_filter_export_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "audadmin"))
    body = {"kind": "person", "first_name": "Bernd", "last_name": f"Export{RUN}"}
    created = client.post("/api/v1/contacts", json=body, headers=h)
    contact = _ok(created, 201)
    _ok(
        client.put(
            f"/api/v1/contacts/{contact['id']}",
            json=body | {"first_name": "Bernd Otto"},
            headers=h | {"If-Match": created.headers["etag"]},
        )
    )
    # Type filter alone: only contact rows, the new one among them.
    rows = _ok(client.get(AUDIT, params={"entity_type": "contact"}, headers=h))
    assert rows
    assert all(r["entity_type"] == "contact" for r in rows)
    assert contact["id"] in {r["entity_id"] for r in rows}
    assert _ok(client.get(AUDIT, params={"entity_type": "unknown_type"}, headers=h)) == []
    # CSV export: one row per changed field, semicolon separated, UTF-8 BOM.
    export = client.get(
        f"{AUDIT}/export", params={"entity_type": "contact", "entity_id": contact["id"]}, headers=h
    )
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("text/csv")
    assert "aenderungsprotokoll-contact.csv" in export.headers["content-disposition"]
    text = export.content.decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0] == "occurred_at;entity_type;entity_id;field;old;new;actor_user_id"
    fields = {line.split(";")[3] for line in lines[1:]}
    assert "first_name" in fields
    first_name = next(line for line in lines[1:] if line.split(";")[3] == "first_name")
    assert first_name.split(";")[4:6] == ["Bernd", "Bernd Otto"]
    # Permission and tenant separation.
    caretaker = bearer(login(client, world, "audcaretaker"))
    assert client.get(AUDIT, headers=caretaker).status_code == 403
    assert client.get(f"{AUDIT}/export", headers=caretaker).status_code == 403
    other = bearer(login(client, world, "audother"))
    assert _audit(client, other, "contact", contact["id"]) == []
