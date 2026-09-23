"""M4 acceptance: property with buildings and units, key values with periods, as-of query,
property status, legal entity rules for bank accounts (6.9.1, D56)."""

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


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p-{RUN}", name=f"Objekte {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m4admin", "tenant_admin"), ("m4caretaker", "caretaker")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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


def _prop(number: str, management_type: str = "hoa") -> dict[str, Any]:
    return {
        "number": number,
        "name": f"Rheinpromenade {number}",
        "management_type": management_type,
        "street": "Rheinpromenade",
        "house_number": number.lstrip("0"),
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }


def test_property_with_buildings_units_keys_and_as_of(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m4admin"))
    created = client.post("/api/v1/properties", json=_prop("342", "hoa_with_sev"), headers=h)
    assert created.status_code == 201, created.text
    prop = created.json()
    assert prop["status"] == "onboarding"
    hoa = [e for e in prop["legal_entities"] if e["kind"] == "hoa"]
    assert len(hoa) == 1
    assert (
        hoa[0]["name"]
        == "Gemeinschaft der Wohnungseigentümer Rheinpromenade 342, 40789 Monheim am Rhein"
    )
    assert client.post("/api/v1/properties", json=_prop("342"), headers=h).status_code == 409
    assert client.post("/api/v1/properties", json=_prop("34A"), headers=h).status_code == 422

    keys = client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h).json()
    codes = [k["code"] for k in keys]
    assert codes[:5] == ["WFL", "HZF", "WWF", "UR", "MEA"]
    mea = next(k for k in keys if k["code"] == "MEA")

    building = client.post(
        f"/api/v1/properties/{prop['id']}/buildings",
        json={"name": "Haus A", "elevator": True},
        headers=h,
    ).json()
    unit = client.post(
        f"/api/v1/properties/{prop['id']}/units",
        json={
            "building_id": building["id"],
            "number": "01",
            "label": "WE 01",
            "location": "EG links",
            "unit_type": "apartment",
            "living_area_sqm": "71.35",
        },
        headers=h,
    )
    assert unit.status_code == 201
    unit_id = unit.json()["id"]
    assert (
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building["id"], "number": "01", "unit_type": "garage"},
            headers=h,
        ).status_code
        == 409
    )

    first = client.post(
        f"/api/v1/units/{unit_id}/allocation-values",
        json={"allocation_key_id": mea["id"], "value": "125.5", "valid_from": "2020-01-01"},
        headers=h,
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/units/{unit_id}/allocation-values",
        json={"allocation_key_id": mea["id"], "value": "130", "valid_from": "2026-01-01"},
        headers=h,
    )
    assert second.status_code == 201
    history = client.get(f"/api/v1/units/{unit_id}/allocation-values", headers=h).json()
    assert [(v["value"], v["valid_from"], v["valid_to"]) for v in history] == [
        ("125.50000000", "2020-01-01", "2025-12-31"),
        ("130.00000000", "2026-01-01", None),
    ]
    at_2025 = client.get(
        f"/api/v1/units/{unit_id}", params={"as_of": "2025-06-30"}, headers=h
    ).json()
    assert [v["value"] for v in at_2025["allocation_values"]] == ["125.50000000"]
    at_2026 = client.get(
        f"/api/v1/properties/{prop['id']}/units", params={"as_of": "2026-06-30"}, headers=h
    ).json()
    assert at_2026[0]["allocation_values"][0]["value"] == "130.00000000"
    overlap = client.post(
        f"/api/v1/units/{unit_id}/allocation-values",
        json={
            "allocation_key_id": mea["id"],
            "value": "1",
            "valid_from": "2021-01-01",
            "valid_to": "2021-12-31",
        },
        headers=h,
    )
    assert overlap.status_code == 409

    active = client.post(
        f"/api/v1/properties/{prop['id']}/status", json={"status": "active"}, headers=h
    )
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    back = client.post(
        f"/api/v1/properties/{prop['id']}/status", json={"status": "onboarding"}, headers=h
    )
    assert back.status_code == 422
    end_without_date = client.post(
        f"/api/v1/properties/{prop['id']}/status", json={"status": "terminated"}, headers=h
    )
    assert end_without_date.status_code == 422


def test_activation_needs_a_unit(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m4admin"))
    prop = client.post("/api/v1/properties", json=_prop("343"), headers=h).json()
    assert (
        client.post(
            f"/api/v1/properties/{prop['id']}/status", json={"status": "active"}, headers=h
        ).status_code
        == 422
    )


def test_bank_accounts_follow_legal_entities(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m4admin"))
    weg = client.post("/api/v1/properties", json=_prop("344", "hoa"), headers=h).json()
    hoa_id = weg["legal_entities"][0]["id"]
    ok = client.post(
        f"/api/v1/properties/{weg['id']}/bank-accounts",
        json={
            "legal_entity_id": hoa_id,
            "kind": "hoa",
            "iban": "DE02120300000000202051",
            "holder": "WEG Rheinpromenade 344",
            "valid_from": "2026-01-01",
        },
        headers=h,
    )
    assert ok.status_code == 201
    assert ok.json()["iban_masked"] == "DE02 **** **** 2051"
    deposit_on_hoa = client.post(
        f"/api/v1/properties/{weg['id']}/bank-accounts",
        json={
            "legal_entity_id": hoa_id,
            "kind": "deposit",
            "iban": "DE02120300000000202051",
            "holder": "x",
            "valid_from": "2026-01-01",
        },
        headers=h,
    )
    assert deposit_on_hoa.status_code == 422

    rental = client.post("/api/v1/properties", json=_prop("345", "rental"), headers=h).json()
    assert rental["legal_entities"] == []
    owner = client.post(
        "/api/v1/contacts",
        json={"kind": "company", "company_name": f"Bestand {RUN} GmbH"},
        headers=h,
    ).json()
    party = client.post(
        "/api/v1/parties", json={"members": [{"contact_id": owner["id"]}]}, headers=h
    ).json()
    added = client.post(
        f"/api/v1/properties/{rental['id']}/owners",
        json={"party_id": party["id"], "valid_from": "2026-01-01"},
        headers=h,
    )
    assert added.status_code == 201
    owner_entity = added.json()["legal_entity_id"]
    deposit = client.post(
        f"/api/v1/properties/{rental['id']}/bank-accounts",
        json={
            "legal_entity_id": owner_entity,
            "kind": "deposit",
            "iban": "DE02120300000000202051",
            "holder": "Kautionskonto",
            "valid_from": "2026-01-01",
        },
        headers=h,
    )
    assert deposit.status_code == 201
    assert deposit.json()["segregated"] is True
    hoa_on_rental = client.post(
        f"/api/v1/properties/{rental['id']}/bank-accounts",
        json={
            "legal_entity_id": owner_entity,
            "kind": "reserve",
            "iban": "DE02120300000000202051",
            "holder": "x",
            "valid_from": "2026-01-01",
        },
        headers=h,
    )
    assert hoa_on_rental.status_code == 422
    foreign = client.post(
        f"/api/v1/properties/{rental['id']}/bank-accounts",
        json={
            "legal_entity_id": hoa_id,
            "kind": "other",
            "iban": "DE02120300000000202051",
            "holder": "x",
            "valid_from": "2026-01-01",
        },
        headers=h,
    )
    assert foreign.status_code == 422
    owners_on_weg = client.post(
        f"/api/v1/properties/{weg['id']}/owners",
        json={"party_id": party["id"], "valid_from": "2026-01-01"},
        headers=h,
    )
    assert owners_on_weg.status_code == 422
    changed_type = client.put(
        f"/api/v1/properties/{rental['id']}", json=_prop("345", "hoa"), headers=h
    )
    assert changed_type.status_code == 422


def test_meters_catalogs_custom_fields_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m4admin"))
    prop = client.post("/api/v1/properties", json=_prop("346"), headers=h).json()
    meter_types = client.get("/api/v1/catalogs/meter_type", headers=h).json()
    assert "Heizkostenverteiler" in [m["label"] for m in meter_types]
    bad = client.post(
        f"/api/v1/properties/{prop['id']}/meters",
        json={"meter_type_code": "unknown", "number": "1", "valid_from": "2026-01-01"},
        headers=h,
    )
    assert bad.status_code == 422
    meter = client.post(
        f"/api/v1/properties/{prop['id']}/meters",
        json={"meter_type_code": "cold_water", "number": "KW-1", "valid_from": "2026-01-01"},
        headers=h,
    ).json()
    assert (
        client.post(
            f"/api/v1/meters/{meter['id']}/readings",
            json={"read_at": "2026-01-01", "value": "100"},
            headers=h,
        ).json()["implausible"]
        is False
    )
    assert (
        client.post(
            f"/api/v1/meters/{meter['id']}/readings",
            json={"read_at": "2026-02-01", "value": "90"},
            headers=h,
        ).json()["implausible"]
        is True
    )

    field = client.post(
        "/api/v1/custom-fields",
        json={
            "entity_type": "property",
            "key": f"baujahr_{RUN}",
            "label": "Baujahr lt. Akte",
            "field_type": "number",
        },
        headers=h,
    )
    assert field.status_code == 201
    good = client.post(
        "/api/v1/properties",
        json=_prop("347") | {"custom_fields": {f"baujahr_{RUN}": 1972}},
        headers=h,
    )
    assert good.status_code == 201
    wrong = client.post(
        "/api/v1/properties",
        json=_prop("348") | {"custom_fields": {f"baujahr_{RUN}": "alt"}},
        headers=h,
    )
    assert wrong.status_code == 422
    unknown = client.post(
        "/api/v1/properties", json=_prop("349") | {"custom_fields": {"nope": 1}}, headers=h
    )
    assert unknown.status_code == 422

    caretaker = bearer(login(client, world, "m4caretaker"))
    assert client.get("/api/v1/properties", headers=caretaker).status_code == 200
    assert (
        client.post("/api/v1/properties", json=_prop("350"), headers=caretaker).status_code == 403
    )
    listed = client.get("/api/v1/properties", params={"q": "Rheinpromenade"}, headers=h).json()
    assert listed["total"] >= 5
