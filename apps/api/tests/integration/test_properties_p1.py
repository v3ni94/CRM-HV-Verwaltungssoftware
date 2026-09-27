"""P1 AP2 (Ergänzung CRM 4.2 to 4.4): building with full energy certificate and ETag update,
unit version and informational amounts, statement periods, sub communities, Objektmappe,
provider and owner details with ledger account references, vacancy key values, meter changes.
Tenant separation and permissions for the new endpoints."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration

P = "/api/v1/properties"
A = "/api/v1/accounting"
BUCKET = f"mhvp-p1-{RUN}"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p1a-{RUN}", name=f"P1 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p1b-{RUN}", name=f"P1 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("p1padmin", a, "tenant_admin"),
            ("p1pcaretaker", a, "caretaker"),
            ("p1pother", b, "tenant_admin"),
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
    settings = _settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _prop(c: TestClient, h: dict[str, str], number: str, management_type: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"P1 Objekt {number}",
        "management_type": management_type,
        "street": "Musterweg",
        "house_number": number.lstrip("0"),
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    return dict(_ok(c.post(P, json=body, headers=h), 201))


def _building(c: TestClient, h: dict[str, str], prop: str, **extra: Any) -> dict[str, Any]:
    return dict(
        _ok(c.post(f"{P}/{prop}/buildings", json={"name": "Haus A", **extra}, headers=h), 201)
    )


def _unit(c: TestClient, h: dict[str, str], prop: str, building: str, number: str) -> Any:
    body = {"building_id": building, "number": number, "unit_type": "apartment"}
    return _ok(c.post(f"{P}/{prop}/units", json=body, headers=h), 201)


def _contact(c: TestClient, h: dict[str, str], name: str) -> Any:
    body = {"kind": "company", "company_name": f"{name} {RUN} GmbH"}
    return _ok(c.post("/api/v1/contacts", json=body, headers=h), 201)


def _party(c: TestClient, h: dict[str, str], contact_id: str) -> str:
    body = {"members": [{"contact_id": contact_id}]}
    return str(_ok(c.post("/api/v1/parties", json=body, headers=h), 201)["id"])


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def _hoa_ledger_account(c: TestClient, h: dict[str, str], prop: dict[str, Any]) -> str:
    """Any ledger account of the GdWE ledger of a WEG property (reference target only)."""
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )
    accounts = _ok(c.get(f"{A}/ledgers/{ledger['id']}/accounts", headers=h))
    return str(accounts[0]["id"])


ENERGY = {
    "energy_certificate_law": "geg",
    "energy_certificate_type": "bedarf",
    "energy_final_heat_kwh": "95.5",
    "energy_hot_water_included": True,
    "energy_final_electricity_kwh": "20",
    "heating_type_code": "zentral",
    "energy_sources": ["Gas", "Solar"],
    "energy_certificate_class": "D",
    "energy_certificate_construction_year": 1978,
    "energy_certificate_issued_on": "2024-03-01",
    "energy_certificate_valid_until": "2034-02-28",
}


def test_building_energy_certificate_etag_and_unit_version(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "p1padmin"))
    prop = _prop(client, h, "901", "rental")
    # the property no longer carries certificate fields (operator decision 26.09.2026)
    assert "energy_certificate_type" not in prop
    assert (
        client.post(
            P,
            json={
                "number": "902",
                "name": "x y",
                "management_type": "rental",
                "energy_certificate_type": "bedarf",
            },
            headers=h,
        ).status_code
        == 422
    )
    bad = ENERGY | {"energy_certificate_valid_until": "2024-02-01"}
    assert (
        client.post(f"{P}/{prop['id']}/buildings", json={"name": "H", **bad}, headers=h).status_code
        == 422
    )
    bad = ENERGY | {"energy_certificate_law": "enev_2009"}
    assert (
        client.post(f"{P}/{prop['id']}/buildings", json={"name": "H", **bad}, headers=h).status_code
        == 422
    )

    building = _building(client, h, prop["id"], address_addition="Hinterhaus", **ENERGY)
    assert building["version"] == 1
    assert building["energy_sources"] == ["Gas", "Solar"]
    assert building["address_addition"] == "Hinterhaus"
    got = client.get(f"/api/v1/buildings/{building['id']}", headers=h)
    assert got.headers["etag"] == '"1"'
    body = {k: v for k, v in building.items() if k not in ("id", "property_id", "version")}
    stale = client.put(
        f"/api/v1/buildings/{building['id']}",
        json=body | {"floors": 3},
        headers=h | {"If-Match": '"7"'},
    )
    assert stale.status_code == 412
    updated = _ok(
        client.put(
            f"/api/v1/buildings/{building['id']}",
            json=body | {"floors": 3},
            headers=h | {"If-Match": '"1"'},
        )
    )
    assert updated["version"] == 2
    assert updated["floors"] == 3
    assert updated["energy_certificate_class"] == "D"

    # unit: version, commission, deposit amount, vacancy VAT option
    unit = _unit(client, h, prop["id"], building["id"], "01")
    assert unit["version"] == 1
    ubody = {
        "building_id": building["id"],
        "number": "01",
        "unit_type": "apartment",
        "commission": "1500.00",
        "commission_note": "zwei Kaltmieten",
        "deposit_amount": "2400.00",
        "vacancy_vat_option": "commercial_no_vat",
    }
    assert (
        client.put(
            f"/api/v1/units/{unit['id']}", json=ubody, headers=h | {"If-Match": '"9"'}
        ).status_code
        == 412
    )
    unit = _ok(
        client.put(f"/api/v1/units/{unit['id']}", json=ubody, headers=h | {"If-Match": '"1"'})
    )
    assert unit["version"] == 2
    assert unit["deposit_amount"] == "2400.00"
    assert unit["vacancy_vat_option"] == "commercial_no_vat"
    assert client.get(f"/api/v1/units/{unit['id']}", headers=h).headers["etag"] == '"2"'

    # the exposé draft reads the certificate from the building
    exp = _ok(client.get(f"/api/v1/letting/units/{unit['id']}/expose", headers=h))
    assert exp["energy_certificate"]["type"] == "bedarf"
    assert exp["energy_certificate"]["value"] == "95.50"
    assert exp["energy_certificate"]["source"] == "Gas, Solar"
    assert not [m for m in exp["missing"] if m.startswith("energy_certificate.")]
    listing = _ok(
        client.post(
            "/api/v1/letting/listings", json={"unit_id": unit["id"], "kind": "rental"}, headers=h
        ),
        201,
    )
    assert listing["energy_status"] == "liegt_vor"
    assert listing["energy_includes_hot_water"] is True
    assert listing["energy_building_year"] == 1978

    # vacancy key values with history and as-of
    keys = {
        k["code"]: k["id"] for k in _ok(client.get(f"{P}/{prop['id']}/allocation-keys", headers=h))
    }
    key = next(iter(keys.values()))
    v = f"/api/v1/units/{unit['id']}/vacancy-allocation-values"
    first = _ok(
        client.post(
            v, json={"allocation_key_id": key, "value": "10", "valid_from": "2026-01-01"}, headers=h
        ),
        201,
    )
    second = _ok(
        client.post(
            v, json={"allocation_key_id": key, "value": "12", "valid_from": "2026-07-01"}, headers=h
        ),
        201,
    )
    assert second["key_code"] == first["key_code"]
    history = _ok(client.get(v, headers=h))
    assert [(x["value"], x["valid_to"]) for x in history] == [
        ("10.00000000", "2026-06-30"),
        ("12.00000000", None),
    ]
    assert [x["value"] for x in _ok(client.get(v, params={"as_of": "2026-03-01"}, headers=h))] == [
        "10.00000000"
    ]
    overlap = {
        "allocation_key_id": key,
        "value": "1",
        "valid_from": "2026-02-01",
        "valid_to": "2026-02-28",
    }
    assert client.post(v, json=overlap, headers=h).status_code == 409

    # meter change: old final and new initial reading, number replaced
    meter = _ok(
        client.post(
            f"{P}/{prop['id']}/meters",
            json={
                "unit_id": unit["id"],
                "meter_type_code": "cold_water",
                "number": "KW-1",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    m = f"/api/v1/meters/{meter['id']}/changes"
    early = {"changed_on": "2025-12-01", "old_final_value": "1", "new_initial_value": "0"}
    assert client.post(m, json=early, headers=h).status_code == 422
    change = _ok(
        client.post(
            m,
            json={
                "changed_on": "2026-05-01",
                "old_final_value": "1234.5",
                "new_initial_value": "0",
                "new_number": "KW-2",
            },
            headers=h,
        ),
        201,
    )
    assert change["old_number"] == "KW-1"
    assert change["new_number"] == "KW-2"
    meters = _ok(client.get(f"{P}/{prop['id']}/meters", headers=h))
    assert next(x for x in meters if x["id"] == meter["id"])["number"] == "KW-2"
    assert len(_ok(client.get(m, headers=h))) == 1


def test_property_level_entities(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1padmin"))
    weg = _prop(client, h, "903", "hoa")
    rental = _prop(client, h, "904", "rental")
    building = _building(client, h, weg["id"])
    unit = _unit(client, h, weg["id"], building["id"], "01")

    # statement periods per kind, no overlap within a kind
    bp = f"{P}/{weg['id']}/billing-periods"
    year = {
        "kind": "hoa",
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "board_online_audit": True,
    }
    period = _ok(client.post(bp, json=year, headers=h), 201)
    assert period["board_online_audit"] is True
    assert client.post(bp, json=year | {"valid_from": "2026-06-01"}, headers=h).status_code == 409
    _ok(client.post(bp, json=year | {"kind": "heating_costs"}, headers=h), 201)
    assert client.post(bp, json=year | {"valid_to": "2025-01-01"}, headers=h).status_code == 422
    assert len(_ok(client.get(bp, headers=h))) == 2
    assert client.delete(f"{bp}/{period['id']}", headers=h).status_code == 204
    assert (
        client.delete(f"{P}/{rental['id']}/billing-periods/{period['id']}", headers=h).status_code
        == 404
    )
    assert [x["kind"] for x in _ok(client.get(bp, headers=h))] == ["heating_costs"]

    # sub communities: WEG only, unique code, units attach and detach on delete
    sc = f"{P}/{weg['id']}/sub-communities"
    assert (
        client.post(
            f"{P}/{rental['id']}/sub-communities", json={"code": "H1", "name": "Haus 1"}, headers=h
        ).status_code
        == 422
    )
    sub = _ok(client.post(sc, json={"code": "H1", "name": "Haus 1"}, headers=h), 201)
    assert client.post(sc, json={"code": "H1", "name": "x"}, headers=h).status_code == 409
    sub = _ok(
        client.put(f"{sc}/{sub['id']}", json={"code": "H1", "name": "Haus 1 Vorderhaus"}, headers=h)
    )
    assert sub["name"] == "Haus 1 Vorderhaus"
    ubody = {
        "building_id": building["id"],
        "number": "01",
        "unit_type": "apartment",
        "sub_community_id": sub["id"],
    }
    unit = _ok(client.put(f"/api/v1/units/{unit['id']}", json=ubody, headers=h))
    assert unit["sub_community_id"] == sub["id"]
    foreign_unit = {
        "building_id": building["id"],
        "number": "02",
        "unit_type": "apartment",
        "sub_community_id": sub["id"],
    }
    other_building = _building(client, h, rental["id"])
    assert (
        client.post(
            f"{P}/{rental['id']}/units",
            json=foreign_unit | {"building_id": other_building["id"]},
            headers=h,
        ).status_code
        == 422
    )
    assert client.delete(f"{sc}/{sub['id']}", headers=h).status_code == 204
    assert _ok(client.get(f"/api/v1/units/{unit['id']}", headers=h))["sub_community_id"] is None

    # Objektmappe
    pd = f"{P}/{weg['id']}/portal-documents"
    doc = _doc(client, h, "hausordnung.pdf")
    assert (
        client.post(pd, json={"document_id": doc, "visible_for": []}, headers=h).status_code == 422
    )
    entry = _ok(
        client.post(
            pd,
            json={"document_id": doc, "visible_for": ["owner", "tenant"], "title": "Hausordnung"},
            headers=h,
        ),
        201,
    )
    assert entry["visible_for"] == ["owner", "tenant"]
    assert (
        client.post(pd, json={"document_id": doc, "visible_for": ["owner"]}, headers=h).status_code
        == 409
    )
    assert len(_ok(client.get(pd, headers=h))) == 1
    assert client.delete(f"{pd}/{entry['id']}", headers=h).status_code == 204
    assert _ok(client.get(f"/api/v1/documents/{doc}", headers=h))["id"] == doc

    # provider relation: customer number, exemption certificate, creditor account
    account = _hoa_ledger_account(client, h, weg)
    provider = _contact(client, h, "Dachdecker")
    sp = f"{P}/{weg['id']}/service-providers"
    base = {
        "contact_id": provider["id"],
        "contract_type_code": "caretaker",
        "valid_from": "2026-01-01",
        "customer_number": "K-4711",
    }
    assert (
        client.post(
            sp,
            json=base
            | {"exemption_cert_status": "none", "exemption_cert_valid_until": "2027-01-01"},
            headers=h,
        ).status_code
        == 422
    )
    rel = _ok(
        client.post(
            sp,
            json=base
            | {
                "exemption_cert_status": "valid",
                "exemption_cert_valid_until": "2027-01-01",
                "creditor_account_id": account,
            },
            headers=h,
        ),
        201,
    )
    assert rel["customer_number"] == "K-4711"
    assert rel["creditor_account_id"] == account
    # the account of the GdWE ledger cannot be referenced from another property
    assert (
        client.post(
            f"{P}/{rental['id']}/service-providers",
            json=base | {"creditor_account_id": account},
            headers=h,
        ).status_code
        == 422
    )

    # bank account with assigned ledger account
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    acc = _ok(
        client.post(
            f"{P}/{weg['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": "DE02120300000000202051",
                "holder": "WEG Musterweg 903",
                "valid_from": "2026-01-01",
                "ledger_account_id": account,
                "notes": "Girokonto",
            },
            headers=h,
        ),
        201,
    )
    assert acc["ledger_account_id"] == account
    assert acc["notes"] == "Girokonto"

    # owner of the rental property: tax advisor, power of attorney, clearing account
    owner_contact = _contact(client, h, "Bestand")
    advisor = _contact(client, h, "Steuerkanzlei")
    poa = _doc(client, h, "vollmacht.pdf")
    party = _party(client, h, owner_contact["id"])
    ow = f"{P}/{rental['id']}/owners"
    assert (
        client.post(
            ow,
            json={"party_id": party, "valid_from": "2026-01-01", "clearing_account_id": account},
            headers=h,
        ).status_code
        == 422
    )
    owner = _ok(
        client.post(
            ow,
            json={
                "party_id": party,
                "valid_from": "2026-01-01",
                "tax_advisor_contact_id": advisor["id"],
                "power_of_attorney_document_id": poa,
            },
            headers=h,
        ),
        201,
    )
    assert owner["tax_advisor_contact_id"] == advisor["id"]
    assert owner["power_of_attorney_document_id"] == poa
    current = _ok(client.get(ow, headers=h))
    assert current[0]["tax_advisor_contact_id"] == advisor["id"]
    details = _ok(
        client.put(
            f"{ow}/{owner['id']}/details",
            json={"tax_advisor_contact_id": None, "power_of_attorney_document_id": poa},
            headers=h,
        )
    )
    assert details["tax_advisor_contact_id"] is None
    assert details["legal_entity_id"] == owner["legal_entity_id"]


def test_tenant_separation_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1padmin"))
    other = bearer(login(client, world, "p1pother"))
    caretaker = bearer(login(client, world, "p1pcaretaker"))
    weg = _prop(client, h, "905", "hoa")
    building = _building(client, h, weg["id"], **ENERGY)
    unit = _unit(client, h, weg["id"], building["id"], "01")
    b = f"/api/v1/buildings/{building['id']}"
    body = {"name": "Haus A"}
    assert client.get(b, headers=other).status_code == 404
    assert client.put(b, json=body, headers=other).status_code == 404
    assert client.get(b, headers=caretaker).status_code == 200
    assert client.put(b, json=body, headers=caretaker).status_code == 403
    # list endpoints filter by RLS: the foreign tenant sees nothing, never an error leak
    assert _ok(client.get(f"{P}/{weg['id']}/billing-periods", headers=other)) == []
    year = {"kind": "hoa", "valid_from": "2026-01-01", "valid_to": "2026-12-31"}
    assert (
        client.post(f"{P}/{weg['id']}/billing-periods", json=year, headers=other).status_code == 404
    )
    assert (
        client.post(f"{P}/{weg['id']}/billing-periods", json=year, headers=caretaker).status_code
        == 403
    )
    assert (
        client.post(
            f"{P}/{weg['id']}/sub-communities", json={"code": "X", "name": "x"}, headers=other
        ).status_code
        == 404
    )
    v = f"/api/v1/units/{unit['id']}/vacancy-allocation-values"
    assert client.get(v, headers=other).status_code == 404
    assert client.get(v, headers=caretaker).status_code == 200
    meter = _ok(
        client.post(
            f"{P}/{weg['id']}/meters",
            json={"meter_type_code": "cold_water", "number": "KW-9", "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    change = {"changed_on": "2026-05-01", "old_final_value": "1", "new_initial_value": "0"}
    assert (
        client.post(f"/api/v1/meters/{meter['id']}/changes", json=change, headers=other).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/meters/{meter['id']}/changes", json=change, headers=caretaker
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/meters/{meter['id']}/changes", headers=other).status_code == 404
