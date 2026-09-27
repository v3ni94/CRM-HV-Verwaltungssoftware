"""P1 AP8 (inline editing): partial updates of property, building, unit, contact and contract
remarks. Only the sent fields change, ``If-Match`` against ``version`` answers 412 on a stale
version, the audit row carries the diff of the changed fields only, the permission equals the
``PUT`` route and a record of another tenant is invisible."""

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

P = "/api/v1/properties"
AUDIT = "/api/v1/tenant/audit-log"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pt8a-{RUN}", name=f"Patch A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pt8b-{RUN}", name=f"Patch B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("pt8admin", a, "tenant_admin"),
            ("pt8caretaker", a, "caretaker"),
            ("pt8other", b, "tenant_admin"),
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
    return response.json()


def _audit(client: TestClient, h: dict[str, str], entity_type: str, entity_id: str) -> Any:
    return _ok(
        client.get(AUDIT, params={"entity_type": entity_type, "entity_id": entity_id}, headers=h)
    )


def _prop(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"Patchhaus {number}",
        "management_type": "rental",
        "street": "Patchweg",
        "house_number": number.lstrip("0"),
        "postal_code": "40789",
        "city": "Monheim am Rhein",
        "notes": "Bestand",
    }
    return dict(_ok(c.post(P, json=body, headers=h), 201))


def _building(c: TestClient, h: dict[str, str], prop: str) -> dict[str, Any]:
    body = {"name": "Haus A", "floors": 2}
    return dict(_ok(c.post(f"{P}/{prop}/buildings", json=body, headers=h), 201))


def _unit(c: TestClient, h: dict[str, str], prop: str, building: str, number: str) -> Any:
    body = {"building_id": building, "number": number, "unit_type": "apartment", "rooms": "3.0"}
    return _ok(c.post(f"{P}/{prop}/units", json=body, headers=h), 201)


def test_property_patch_partial_version_audit(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pt8admin"))
    prop = _prop(client, h, "811")
    assert prop["version"] == 1
    # Partial update: only the sent field changes, the rest stays.
    res = client.patch(f"{P}/{prop['id']}", json={"notes": "Neu"}, headers=h | {"If-Match": '"1"'})
    out = _ok(res)
    assert res.headers["etag"] == '"2"'
    assert out["version"] == 2
    assert out["notes"] == "Neu"
    assert out["name"] == "Patchhaus 811"
    assert out["street"] == "Patchweg"
    # Stale version: 412 with the platform problem code, nothing changed.
    stale = client.patch(
        f"{P}/{prop['id']}", json={"notes": "Alt"}, headers=h | {"If-Match": '"1"'}
    )
    assert stale.status_code == 412, stale.text
    assert stale.json()["code"] == "MHVP-PLAT-0003"
    assert _ok(client.get(f"{P}/{prop['id']}", headers=h))["notes"] == "Neu"
    # Validation of the merged record uses the PUT rules (management type frozen, pattern).
    assert (
        client.patch(f"{P}/{prop['id']}", json={"management_type": "hoa"}, headers=h).status_code
        == 422
    )
    assert client.patch(f"{P}/{prop['id']}", json={"number": "8A"}, headers=h).status_code == 422
    assert client.patch(f"{P}/{prop['id']}", json={"unknown": 1}, headers=h).status_code == 422
    # Audit: the diff carries only the changed field.
    rows = _audit(client, h, "property", prop["id"])
    updates = [r for r in rows if r["changes"] and "notes" in r["changes"]]
    assert updates, rows
    assert updates[0]["changes"]["notes"] == {"old": "Bestand", "new": "Neu"}
    assert "name" not in updates[0]["changes"]


def test_building_and_unit_patch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pt8admin"))
    prop = _prop(client, h, "812")
    building = _building(client, h, prop["id"])
    res = client.patch(
        f"/api/v1/buildings/{building['id']}",
        json={"construction_year": 1972},
        headers=h | {"If-Match": '"1"'},
    )
    out = _ok(res)
    assert res.headers["etag"] == '"2"'
    assert out["construction_year"] == 1972
    assert out["floors"] == 2
    assert out["name"] == "Haus A"
    assert (
        client.patch(
            f"/api/v1/buildings/{building['id']}",
            json={"floors": 4},
            headers=h | {"If-Match": '"1"'},
        ).status_code
        == 412
    )
    assert (
        client.patch(
            f"/api/v1/buildings/{building['id']}", json={"floors": -1}, headers=h
        ).status_code
        == 422
    )
    rows = _audit(client, h, "building", building["id"])
    assert any(r["changes"].get("construction_year") == {"old": None, "new": 1972} for r in rows)

    unit = _unit(client, h, prop["id"], building["id"], "01")
    assert unit["version"] == 1
    res = client.patch(
        f"/api/v1/units/{unit['id']}",
        json={"label": "EG links", "rooms": "3.5"},
        headers=h | {"If-Match": '"1"'},
    )
    out = _ok(res)
    assert res.headers["etag"] == '"2"'
    assert out["label"] == "EG links"
    assert out["rooms"] == "3.5"
    assert out["number"] == "01"
    assert out["building_id"] == building["id"]
    assert (
        client.patch(
            f"/api/v1/units/{unit['id']}", json={"label": "x"}, headers=h | {"If-Match": '"1"'}
        ).status_code
        == 412
    )
    # A building of another property is refused as on PUT.
    other = _building(client, h, _prop(client, h, "813")["id"])
    assert (
        client.patch(
            f"/api/v1/units/{unit['id']}", json={"building_id": other["id"]}, headers=h
        ).status_code
        == 422
    )
    rows = _audit(client, h, "unit", unit["id"])
    assert any(set(r["changes"]) == {"label", "rooms"} for r in rows), rows


def test_patch_permission_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pt8admin"))
    prop = _prop(client, h, "814")
    building = _building(client, h, prop["id"])
    unit = _unit(client, h, prop["id"], building["id"], "01")
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Petra", "last_name": f"Patch{RUN}"},
            headers=h,
        ),
        201,
    )
    caretaker = bearer(login(client, world, "pt8caretaker"))
    other = bearer(login(client, world, "pt8other"))
    calls = [
        (f"{P}/{prop['id']}", {"notes": "x"}),
        (f"/api/v1/buildings/{building['id']}", {"floors": 1}),
        (f"/api/v1/units/{unit['id']}", {"label": "x"}),
        (f"/api/v1/contacts/{contact['id']}", {"notes": "x"}),
    ]
    for path, body in calls:
        assert client.patch(path, json=body, headers=caretaker).status_code == 403, path
        assert client.patch(path, json=body, headers=other).status_code == 404, path
    assert _ok(client.get(f"{P}/{prop['id']}", headers=h))["version"] == 1
    assert _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))["version"] == 1


def test_contact_patch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pt8admin"))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Karl",
                "last_name": f"Inline{RUN}",
                "emails": [{"email": f"karl.{RUN}@example.org", "is_primary": True}],
                "tags": ["patch"],
            },
            headers=h,
        ),
        201,
    )
    cid = contact["id"]
    res = client.patch(
        f"/api/v1/contacts/{cid}",
        json={"notes": "Erreichbar vormittags", "title": "Dr."},
        headers=h | {"If-Match": '"1"'},
    )
    out = _ok(res)
    assert res.headers["etag"] == '"2"'
    assert out["version"] == 2
    assert out["notes"] == "Erreichbar vormittags"
    assert out["title"] == "Dr."
    assert out["display_name"] == f"Inline{RUN}, Dr. Karl"
    # Children untouched by a master data patch.
    assert [e["email"] for e in out["emails"]] == [f"karl.{RUN}@example.org"]
    assert out["tags"] == ["patch"]
    assert (
        client.patch(
            f"/api/v1/contacts/{cid}", json={"notes": "x"}, headers=h | {"If-Match": '"1"'}
        ).status_code
        == 412
    )
    # Same validators as PUT: a person needs a name, the language pattern applies.
    bad = client.patch(
        f"/api/v1/contacts/{cid}", json={"first_name": None, "last_name": None}, headers=h
    )
    assert bad.status_code == 422, bad.text
    assert (
        client.patch(f"/api/v1/contacts/{cid}", json={"language": "DEU"}, headers=h).status_code
        == 422
    )
    assert (
        client.patch(f"/api/v1/contacts/{cid}", json={"kind": "company"}, headers=h).status_code
        == 422
    )
    # Block sets the block date, lifting it clears the date.
    blocked = _ok(client.patch(f"/api/v1/contacts/{cid}", json={"blocked": True}, headers=h))
    assert blocked["blocked"] is True
    assert blocked["blocked_at"] is not None
    lifted = _ok(client.patch(f"/api/v1/contacts/{cid}", json={"blocked": False}, headers=h))
    assert lifted["blocked"] is False
    assert lifted["blocked_at"] is None
    # Search still finds the contact (search text rebuilt from the merged record).
    found = _ok(client.get("/api/v1/contacts", params={"q": f"Inline{RUN}"}, headers=h))
    assert cid in {c["id"] for c in found["items"]}
    rows = _audit(client, h, "contact", cid)
    first = [r for r in rows if r["changes"] and "title" in r["changes"]]
    assert first, rows
    assert first[0]["changes"]["notes"] == {"old": None, "new": "Erreichbar vormittags"}
    assert "emails" not in first[0]["changes"]


def test_contract_notes_patch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pt8admin"))
    prop = _prop(client, h, "815")
    building = _building(client, h, prop["id"])
    unit = _unit(client, h, prop["id"], building["id"], "01")
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Mieter {RUN} GmbH"},
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
    owner_contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Vermieter {RUN} GmbH"},
            headers=h,
        ),
        201,
    )
    owner = _ok(
        client.post(
            "/api/v1/parties",
            json={"members": [{"contact_id": owner_contact["id"]}]},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{P}/{prop['id']}/owners",
            json={"party_id": owner["id"], "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit["id"],
                "party_id": party["id"],
                "start_date": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    cid = contract["id"]
    path = f"/api/v1/contracts/{cid}/notes"
    # Dunning block needs a reason (same rule as the contract schema).
    bad = client.patch(path, json={"dunning_block": True}, headers=h)
    assert bad.status_code == 422, bad.text
    assert bad.json()["errors"][0]["field"] == "dunning_block_reason"
    out = _ok(
        client.patch(
            path, json={"dunning_block": True, "dunning_block_reason": "Klärung offen"}, headers=h
        )
    )
    assert out["dunning_block"] is True
    assert out["dunning_block_reason"] == "Klärung offen"
    assert out["version"] == contract["version"]  # in place, no contract version
    out = _ok(client.patch(path, json={"notes": "Schlüssel im Büro"}, headers=h))
    assert out["notes"] == "Schlüssel im Büro"
    assert out["dunning_block"] is True
    assert out["start_date"] == "2026-01-01"
    assert client.patch(path, json={"end_date": "2027-01-01"}, headers=h).status_code == 422
    assert (
        client.patch(
            path, json={"notes": "x"}, headers=bearer(login(client, world, "pt8caretaker"))
        ).status_code
        == 403
    )
    assert (
        client.patch(
            path, json={"notes": "x"}, headers=bearer(login(client, world, "pt8other"))
        ).status_code
        == 404
    )
    rows = _audit(client, h, "contract", cid)
    assert any(r["changes"].get("notes") == {"old": None, "new": "Schlüssel im Büro"} for r in rows)
    versions = _ok(client.get(f"/api/v1/contracts/{cid}/versions", headers=h))
    assert len(versions) == 1
