"""P1 AP4 (spec 4.11, annex B): catalogues and custom field definitions.

Covers: annex B system entries seeded per tenant (flagged, idempotent), tenant extension,
relabel and deactivate of system entries, refusal to delete a system entry, delete of a
tenant entry, the settings permission (`tenant_settings:update`) for every write, tenant
separation, custom field attributes of 4.11 including patch and delete, and the value
validation of the B.28 field types with minimum, maximum and choice options."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.properties.catalogs import ANNEX_B_CATALOGS
from mhvp.properties.defaults import ensure_tenant_defaults
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m4_properties import _prop

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"cat-{RUN}", name=f"Cat {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"cat2-{RUN}", name=f"Cat2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("katadmin", a, "tenant_admin"),
            ("katcaretaker", a, "caretaker"),
            ("katother", b, "tenant_admin"),
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
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


@pytest.fixture(scope="module")
def world(settings: Any) -> World:
    return asyncio.run(_world(settings))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def test_annex_b_catalogues_seeded_as_system_entries(
    client: TestClient, world: World, settings: Any
) -> None:
    """Expected: every annex B catalogue exists for the tenant with all entries flagged as
    system entries; running the seed again adds nothing (idempotent)."""
    h = bearer(login(client, world, "katadmin"))
    summaries = {c["catalog"]: c for c in _ok(client.get("/api/v1/catalogs", headers=h))}
    for name, entries in ANNEX_B_CATALOGS.items():
        assert name in summaries, name
        assert summaries[name]["system"] >= len(entries), name
    kinds = _ok(client.get("/api/v1/catalogs/deposit_kind", headers=h))
    assert [k["label"] for k in kinds] == [
        "Kautionsversicherung",
        "Sparbuch",
        "Barkaution",
        "Bürgschaft",
        "Festgeld",
        "Patronatserklärung",
    ]
    assert all(k["is_system"] for k in kinds)
    # M4 default catalogues are system entries as well.
    assert all(m["is_system"] for m in _ok(client.get("/api/v1/catalogs/meter_type", headers=h)))
    field_types = {
        e["code"] for e in _ok(client.get("/api/v1/catalogs/custom_field_type", headers=h))
    }
    assert {"integer", "amount", "choice", "url", "contact_ref"} <= field_types

    async def _reseed() -> None:
        from mhvp.core.db.engine import create_app_engine, create_session_factory
        from mhvp.core.db.tenancy import tenant_transaction

        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                await ensure_tenant_defaults(session, world.tenant_a)
        finally:
            await engine.dispose()

    asyncio.run(_reseed())
    again = {c["catalog"]: c for c in _ok(client.get("/api/v1/catalogs", headers=h))}
    assert again == summaries


def test_tenant_extends_and_deactivates_but_cannot_delete_system_entries(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "katadmin"))
    own = _ok(
        client.post(
            "/api/v1/catalogs/deposit_kind",
            json={"code": f"muendlich_{RUN}", "label": "Mündliche Zusage", "sort_order": 99},
            headers=h,
        ),
        201,
    )
    assert own["is_system"] is False
    assert own["active"] is True
    system = next(
        k
        for k in _ok(client.get("/api/v1/catalogs/deposit_kind", headers=h))
        if k["code"] == "sparbuch"
    )
    patched = _ok(
        client.patch(
            f"/api/v1/catalogs/deposit_kind/{system['id']}",
            json={"label": "Sparbuch (verpfändet)", "active": False},
            headers=h,
        )
    )
    assert patched["label"] == "Sparbuch (verpfändet)"
    assert patched["active"] is False
    assert patched["is_system"] is True
    active_codes = {k["code"] for k in _ok(client.get("/api/v1/catalogs/deposit_kind", headers=h))}
    assert "sparbuch" not in active_codes
    assert own["code"] in active_codes
    all_codes = {
        k["code"]
        for k in _ok(client.get("/api/v1/catalogs/deposit_kind?include_inactive=true", headers=h))
    }
    assert "sparbuch" in all_codes
    # Code changes are rejected by the schema (immutable), deletion of a system entry by rule.
    assert (
        client.patch(
            f"/api/v1/catalogs/deposit_kind/{system['id']}", json={"code": "x"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.delete(f"/api/v1/catalogs/deposit_kind/{system['id']}", headers=h).status_code == 409
    )
    _ok(
        client.patch(
            f"/api/v1/catalogs/deposit_kind/{system['id']}", json={"active": True}, headers=h
        )
    )
    # Own entries can be removed; a wrong catalogue in the path is not found.
    assert client.delete(f"/api/v1/catalogs/unit_type/{own['id']}", headers=h).status_code == 404
    assert client.delete(f"/api/v1/catalogs/deposit_kind/{own['id']}", headers=h).status_code == 204
    assert client.delete(f"/api/v1/catalogs/deposit_kind/{own['id']}", headers=h).status_code == 404
    # Duplicate codes are a conflict.
    assert (
        client.post(
            "/api/v1/catalogs/deposit_kind", json={"code": "sparbuch", "label": "x"}, headers=h
        ).status_code
        == 409
    )


def test_catalog_permissions_and_tenant_separation(client: TestClient, world: World) -> None:
    """Expected: reading needs properties:read (caretaker may read), every write needs
    tenant_settings:update; a tenant never sees or changes entries of another tenant."""
    admin = bearer(login(client, world, "katadmin"))
    caretaker = bearer(login(client, world, "katcaretaker"))
    other = bearer(login(client, world, "katother"))
    assert client.get("/api/v1/catalogs/trade", headers=caretaker).status_code == 200
    assert (
        client.post(
            "/api/v1/catalogs/trade", json={"code": "glaser", "label": "Glaser"}, headers=caretaker
        ).status_code
        == 403
    )
    own = _ok(
        client.post(
            "/api/v1/catalogs/trade", json={"code": "glaser", "label": "Glaser"}, headers=admin
        ),
        201,
    )
    assert (
        client.patch(
            f"/api/v1/catalogs/trade/{own['id']}", json={"label": "x"}, headers=caretaker
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/catalogs/trade/{own['id']}", headers=caretaker).status_code == 403
    )
    assert (
        client.patch(
            f"/api/v1/catalogs/trade/{own['id']}", json={"label": "x"}, headers=other
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/catalogs/trade/{own['id']}", headers=other).status_code == 404
    assert "glaser" not in {
        t["code"] for t in _ok(client.get("/api/v1/catalogs/trade", headers=other))
    }
    assert client.get("/api/v1/catalogs/Trade%20x", headers=admin).status_code == 422
    assert client.get("/api/v1/custom-fields", headers=caretaker).status_code == 200
    assert (
        client.post(
            "/api/v1/custom-fields",
            json={"entity_type": "unit", "key": "k", "label": "K", "field_type": "text"},
            headers=caretaker,
        ).status_code
        == 403
    )


def test_custom_field_attributes_patch_delete_and_validation(
    client: TestClient, world: World
) -> None:
    """Expected: a definition carries the 4.11 attributes; entity, key and type are
    immutable; values are checked against type, bounds and choice options."""
    h = bearer(login(client, world, "katadmin"))
    body = {
        "entity_type": "property",
        "key": f"baujahr_{RUN}",
        "label": "Baujahr",
        "field_type": "integer",
        "group": "Gebäudedaten",
        "valid_for_management_types": ["hoa", "rental"],
        "uniqueness": "none",
        "visible_in_main": True,
        "min_value": "1800",
        "max_value": "2100",
        "default_value": 1990,
        "description": "Jahr der Fertigstellung",
        "sort_order": 5,
    }
    field = _ok(client.post("/api/v1/custom-fields", json=body, headers=h), 201)
    assert field["group"] == "Gebäudedaten"
    assert field["visible_in_main"] is True
    assert field["valid_for_management_types"] == ["hoa", "rental"]
    assert Decimal(field["min_value"]) == Decimal("1800")
    assert field["default_value"] == 1990
    assert (
        client.post(
            "/api/v1/custom-fields", json=body | {"min_value": "3000"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/custom-fields", json=body | {"valid_for_management_types": ["x"]}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/custom-fields",
            json={
                "entity_type": "unit",
                "key": f"lage_{RUN}",
                "label": "Lage",
                "field_type": "choice",
            },
            headers=h,
        ).status_code
        == 422
    )
    choice = _ok(
        client.post(
            "/api/v1/custom-fields",
            json={
                "entity_type": "property",
                "key": f"lage_{RUN}",
                "label": "Lage",
                "field_type": "choice",
                "options": ["Stadt", "Land"],
            },
            headers=h,
        ),
        201,
    )
    patched = _ok(
        client.patch(
            f"/api/v1/custom-fields/{field['id']}",
            json={"label": "Baujahr (Fertigstellung)", "max_value": "2050", "required": False},
            headers=h,
        )
    )
    assert patched["label"] == "Baujahr (Fertigstellung)"
    assert Decimal(patched["max_value"]) == Decimal("2050")
    assert (
        client.patch(
            f"/api/v1/custom-fields/{field['id']}", json={"field_type": "text"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/custom-fields/{field['id']}", json={"min_value": "2060"}, headers=h
        ).status_code
        == 422
    )
    by_entity = _ok(client.get("/api/v1/custom-fields?entity_type=property", headers=h))
    assert {f["key"] for f in by_entity} >= {field["key"], choice["key"]}
    # Values: type, bounds and options are checked on the property.
    key, lage = field["key"], choice["key"]
    number = "391"
    ok = client.post(
        "/api/v1/properties",
        json=_prop(number) | {"custom_fields": {key: 1965, lage: "Stadt"}},
        headers=h,
    )
    assert ok.status_code == 201, ok.text
    for bad in ({key: 1700}, {key: 2099}, {key: "1965"}, {key: 19.5}, {lage: "Meer"}):
        response = client.post(
            "/api/v1/properties", json=_prop("392") | {"custom_fields": bad}, headers=h
        )
        assert response.status_code == 422, (bad, response.text)
    assert client.delete(f"/api/v1/custom-fields/{choice['id']}", headers=h).status_code == 204
    assert client.delete(f"/api/v1/custom-fields/{choice['id']}", headers=h).status_code == 404
    assert (
        client.post(
            "/api/v1/properties", json=_prop("393") | {"custom_fields": {lage: "Stadt"}}, headers=h
        ).status_code
        == 422
    )


def test_custom_field_rules_enforced_on_save(client: TestClient, world: World) -> None:
    """Expected: validity per management type (a value for a field of another management
    type is refused, its required flag does not apply), default value on create, required,
    uniqueness within the tenant per entity type (the entity itself excepted), field errors
    under ``errors`` with ``custom_fields.<key>``; another tenant is not affected."""
    h = bearer(login(client, world, "katadmin"))
    other = bearer(login(client, world, "katother"))
    tag = f"tag_{RUN}"
    hoa_only = f"weg_{RUN}"
    stufe = f"stufe_{RUN}"
    for body in (
        {
            "entity_type": "property",
            "key": tag,
            "label": "Kennung",
            "field_type": "string",
            "uniqueness": "all_contracts",
            "required": True,
            "default_value": "STANDARD",
        },
        {
            "entity_type": "property",
            "key": hoa_only,
            "label": "WEG-Nummer",
            "field_type": "string",
            "required": True,
            "valid_for_management_types": ["hoa"],
        },
        {
            "entity_type": "unit",
            "key": stufe,
            "label": "Stufe",
            "field_type": "integer",
            "min_value": "1",
            "max_value": "5",
        },
    ):
        _ok(client.post("/api/v1/custom-fields", json=body, headers=h), 201)

    # Default on create and required field of another management type not required.
    created = _ok(client.post("/api/v1/properties", json=_prop("394", "rental"), headers=h), 201)
    assert created["custom_fields"][tag] == "STANDARD"
    assert hoa_only not in created["custom_fields"]
    # A value for a field that is not valid for the management type is refused.
    refused = client.post(
        "/api/v1/properties",
        json=_prop("395", "rental") | {"custom_fields": {tag: "A", hoa_only: "x"}},
        headers=h,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["errors"][0]["field"] == f"custom_fields.{hoa_only}"
    assert refused.json()["errors"][0]["code"] == "not_applicable"
    # Required within its management type.
    missing = client.post(
        "/api/v1/properties", json=_prop("395", "hoa") | {"custom_fields": {tag: "B"}}, headers=h
    )
    assert missing.status_code == 422
    assert missing.json()["errors"][0] == {
        "location": ["body", "custom_fields", hoa_only],
        "field": f"custom_fields.{hoa_only}",
        "code": "required",
        "message": "ist Pflicht.",
    }
    # Uniqueness within the tenant per entity type.
    duplicate = client.post(
        "/api/v1/properties",
        json=_prop("395", "rental") | {"custom_fields": {tag: "STANDARD"}},
        headers=h,
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["errors"][0]["code"] == "unique"
    # Saving the same value on the entity itself stays possible (PATCH, If-Match).
    same = client.patch(
        f"/api/v1/properties/{created['id']}",
        json={"custom_fields": {tag: "STANDARD"}},
        headers=h | {"If-Match": f'"{created["version"]}"'},
    )
    assert same.status_code == 200, same.text
    # Another tenant has no such definitions: the key is unknown there, its values free.
    foreign = client.post(
        "/api/v1/properties",
        json=_prop("394") | {"custom_fields": {tag: "STANDARD"}},
        headers=other,
    )
    assert foreign.status_code == 422
    assert foreign.json()["errors"][0]["code"] == "unknown"
    assert _ok(client.post("/api/v1/properties", json=_prop("394"), headers=other), 201)
    # Bounds on the unit with a field error.
    building = _ok(
        client.post(
            f"/api/v1/properties/{created['id']}/buildings", json={"name": "Haus"}, headers=h
        ),
        201,
    )
    unit_body = {"building_id": building["id"], "number": "1", "unit_type": "apartment"}
    too_high = client.post(
        f"/api/v1/properties/{created['id']}/units",
        json=unit_body | {"custom_fields": {stufe: 6}},
        headers=h,
    )
    assert too_high.status_code == 422
    assert too_high.json()["errors"][0]["code"] == "max"
    unit = _ok(
        client.post(
            f"/api/v1/properties/{created['id']}/units",
            json=unit_body | {"custom_fields": {stufe: 3}},
            headers=h,
        ),
        201,
    )
    assert unit["custom_fields"][stufe] == 3
