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


def test_remaining_property_endpoints(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m4admin"))
    prop = client.post("/api/v1/properties", json=_prop("351", "rental"), headers=h).json()
    pid = prop["id"]
    got = client.get(f"/api/v1/properties/{pid}", headers=h)
    updated = client.put(
        f"/api/v1/properties/{pid}",
        json=_prop("351", "rental") | {"notes": "Dach 2027"},
        headers=h | {"If-Match": got.headers["etag"]},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert (
        client.put(
            f"/api/v1/properties/{pid}",
            json=_prop("351", "rental"),
            headers=h | {"If-Match": '"1"'},
        ).status_code
        == 412
    )
    building = client.post(
        f"/api/v1/properties/{pid}/buildings", json={"name": "Hinterhaus"}, headers=h
    ).json()
    assert [
        b["name"] for b in client.get(f"/api/v1/properties/{pid}/buildings", headers=h).json()
    ] == ["Hinterhaus"]
    unit = client.post(
        f"/api/v1/properties/{pid}/units",
        json={"building_id": building["id"], "number": "G1", "unit_type": "garage"},
        headers=h,
    ).json()
    changed = client.put(
        f"/api/v1/units/{unit['id']}",
        json={
            "building_id": building["id"],
            "number": "G1",
            "unit_type": "parking",
            "label": "Stellplatz 1",
        },
        headers=h,
    )
    assert changed.json()["unit_type"] == "parking"
    vat = client.post(
        f"/api/v1/units/{unit['id']}/vat-options",
        json={"option": "commercial_full_vat", "occupant": "vacancy", "valid_from": "2026-01-01"},
        headers=h,
    )
    assert vat.json()["vat_option"] == "commercial_full_vat"
    assert (
        client.post(
            f"/api/v1/units/{unit['id']}/vat-options",
            json={"option": "none", "occupant": "vacancy", "valid_from": "2026-06-01"},
            headers=h,
        ).status_code
        == 409
    )
    key = client.post(
        f"/api/v1/properties/{pid}/allocation-keys",
        json={
            "code": "AUFZ_A",
            "name": "Aufzug Haus A",
            "unit_of_measure": "MEA",
            "kind": "static",
        },
        headers=h,
    )
    assert key.status_code == 201
    assert (
        client.post(
            f"/api/v1/properties/{pid}/allocation-keys",
            json={"code": "AUFZ_A", "name": "Doppelt", "unit_of_measure": "MEA", "kind": "static"},
            headers=h,
        ).status_code
        == 409
    )
    person = client.post(
        "/api/v1/contacts",
        json={
            "kind": "person",
            "last_name": f"Hausmeister{RUN}",
            "bank_accounts": [{"iban": "DE02120300000000202051", "valid_from": "2026-01-01"}],
        },
        headers=h,
    ).json()
    contact = client.post(
        f"/api/v1/properties/{pid}/contacts",
        json={
            "contact_id": person["id"],
            "category_code": "caretaker",
            "valid_from": "2026-01-01",
            "visible_in_portal_for": ["tenant"],
        },
        headers=h,
    )
    assert contact.status_code == 201
    assert len(client.get(f"/api/v1/properties/{pid}/contacts", headers=h).json()) == 1
    provider = client.post(
        f"/api/v1/properties/{pid}/service-providers",
        json={
            "contact_id": person["id"],
            "contract_type_code": "caretaker",
            "valid_from": "2026-01-01",
            "contact_bank_account_id": person["bank_accounts"][0]["id"],
        },
        headers=h,
    )
    assert provider.status_code == 201
    other = client.post(
        "/api/v1/contacts", json={"kind": "person", "last_name": f"Fremd{RUN}"}, headers=h
    ).json()
    wrong_account = client.post(
        f"/api/v1/properties/{pid}/service-providers",
        json={
            "contact_id": other["id"],
            "contract_type_code": "caretaker",
            "valid_from": "2026-01-01",
            "contact_bank_account_id": person["bank_accounts"][0]["id"],
        },
        headers=h,
    )
    assert wrong_account.status_code == 422
    assert len(client.get(f"/api/v1/properties/{pid}/service-providers", headers=h).json()) == 1
    item = client.post(
        f"/api/v1/properties/{pid}/maintenance",
        json={
            "kind": "inspection",
            "title": "Prüfung Rauchwarnmelder",
            "due_date": "2027-03-01",
            "remind_before": "1m",
            "interval_months": 12,
        },
        headers=h,
    )
    assert item.status_code == 201
    assert (
        client.get(f"/api/v1/properties/{pid}/maintenance", headers=h).json()[0]["status"] == "open"
    )
    assert client.get(f"/api/v1/properties/{pid}/legal-entities", headers=h).json() == []
    assert client.get(f"/api/v1/properties/{pid}/bank-accounts", headers=h).json() == []
    assert len(client.get(f"/api/v1/properties/{pid}/meters", headers=h).json()) == 0
    assert len(client.get("/api/v1/allocation-key-templates", headers=h).json()) == 21
    assert (
        client.post(
            "/api/v1/catalogs/property_type",
            json={"code": "mfh", "label": "Mehrfamilienhaus"},
            headers=h,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/properties", json=_prop("352") | {"property_type_code": "mfh"}, headers=h
        ).status_code
        == 201
    )
    assert any(
        f["key"].startswith("baujahr_")
        for f in client.get("/api/v1/custom-fields", headers=h).json()
    )
    assert client.get(f"/api/v1/properties/{pid}/units", headers=h).json()[0]["number"] == "G1"


def test_property_list_filters_by_management_type_and_sev(client: TestClient, world: World) -> None:
    """Expected: rental filter lists only rental properties; sev_only lists HOA-with-SEV
    properties only once a tenancy contract exists on one of their units."""
    from tests.integration.test_m5_contracts import _party, _unit

    h = bearer(login(client, world, "m4admin"))
    rental = client.post("/api/v1/properties", json=_prop("353", "rental"), headers=h)
    assert rental.status_code == 201, rental.text
    rental = rental.json()
    sev = client.post("/api/v1/properties", json=_prop("354", "hoa_with_sev"), headers=h)
    assert sev.status_code == 201, sev.text
    sev = sev.json()
    listed = client.get(
        "/api/v1/properties", params={"management_type": "rental"}, headers=h
    ).json()
    ids = {p["id"] for p in listed["items"]}
    assert rental["id"] in ids
    assert sev["id"] not in ids
    before = client.get("/api/v1/properties", params={"sev_only": "true"}, headers=h).json()
    assert sev["id"] not in {p["id"] for p in before["items"]}
    unit = _unit(client, h, sev["id"], "01")
    owner, _ = _party(client, h, "SevEigentuemer")
    ownership = client.post(
        "/api/v1/contracts",
        json={
            "kind": "ownership",
            "unit_id": unit,
            "party_id": owner,
            "start_date": "2020-01-01",
            "title_transfer_date": "2020-01-01",
            "acquisition_kind": "first_acquisition",
            "sev_enabled": True,
        },
        headers=h,
    )
    assert ownership.status_code == 201, ownership.text
    party, _ = _party(client, h, "SevMieter")
    created = client.post(
        "/api/v1/contracts",
        json={"kind": "tenancy", "unit_id": unit, "party_id": party, "start_date": "2026-01-01"},
        headers=h,
    )
    assert created.status_code == 201, created.text
    after = client.get("/api/v1/properties", params={"sev_only": "true"}, headers=h).json()
    ids = {p["id"] for p in after["items"]}
    assert sev["id"] in ids
    assert rental["id"] not in ids
