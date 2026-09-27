"""Contracts P1 (Ergänzung CRM 4.5, AP3, migration 0150): contract related allocation values
with period (open predecessor closed the day before, key of another property rejected), SEPA
mandate with payment types and special levy exclusion (unknown code rejected), move in and
move out dates, termination with meter readings (writes ``meter_reading`` and the link row,
foreign meter rejected), ``GET /contracts?status=ended``, ``GET /deposits`` and
``GET /properties/{id}/vacancies?as_of=``, tenant separation and permissions.

Expected values are fixed here: persons 2 from 01.01.2026, 3 from 01.07.2026 closes the first
value on 30.06.2026; the deposit of 1.500,00 with 1.000,00 received has 500,00 outstanding;
the unit is vacant from 01.10.2026 after the end on 30.09.2026."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _property, _unit

pytestmark = pytest.mark.integration
IBAN = "DE02120300000000202051"
DOC = "0190a000-0000-7000-8000-000000000001"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p1c-{RUN}", name=f"P1 Vertr {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p1d-{RUN}", name=f"P1 Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("p1cadmin", a, "tenant_admin"),
            ("p1capprover", a, "tenant_admin"),
            ("p1ccaretaker", a, "caretaker"),
            ("p1cother", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_contracts_p1(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1cadmin"))
    prop = _property(client, h, "701", "rental")
    unit = _unit(client, h, prop["id"], "01")
    unit2 = _unit(client, h, prop["id"], "02")
    owner, _ = _party(client, h, "Vermieter", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
    )["legal_entity_id"]
    tenant, contact = _party(client, h, "Mieter", iban=IBAN)
    approve_bank_accounts(client, bearer(login(client, world, "p1capprover")), contact["id"])

    # Move in and move out dates (4.5 Kopf); move out before move in is rejected.
    bad = client.post(
        "/api/v1/contracts",
        json={
            "kind": "tenancy",
            "unit_id": unit,
            "party_id": tenant,
            "start_date": "2026-01-01",
            "move_in_on": "2026-01-05",
            "move_out_on": "2026-01-02",
        },
        headers=h,
    )
    assert bad.status_code == 422, bad.text
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2026-01-01",
                "move_in_on": "2026-01-05",
            },
            headers=h,
        )
    )
    cid = contract["id"]
    assert contract["move_in_on"] == "2026-01-05"
    assert contract["move_out_on"] is None

    # Allocation values (4.5 Eigenschaften): key of the property, period within the term.
    keys = _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h), 200)
    persons = next((k for k in keys if k["code"] == "PERS"), None) or _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/allocation-keys",
            json={"code": "PERS", "name": "Personen", "unit_of_measure": "Pers", "kind": "static"},
            headers=h,
        )
    )
    other_prop = _property(client, h, "702", "rental")
    foreign_key = _ok(
        client.post(
            f"/api/v1/properties/{other_prop['id']}/allocation-keys",
            json={"code": "P1X", "name": "Fremd", "unit_of_measure": "Pers", "kind": "static"},
            headers=h,
        )
    )
    url = f"/api/v1/contracts/{cid}/allocation-values"
    assert (
        client.post(
            url,
            json={"allocation_key_id": foreign_key["id"], "value": "2", "valid_from": "2026-01-01"},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            json={"allocation_key_id": persons["id"], "value": "2", "valid_from": "2025-12-01"},
            headers=h,
        ).status_code
        == 422
    )
    first = _ok(
        client.post(
            url,
            json={"allocation_key_id": persons["id"], "value": "2", "valid_from": "2026-01-01"},
            headers=h,
        )
    )
    assert first["allocation_key_code"] == "PERS"
    assert first["valid_to"] is None
    _ok(
        client.post(
            url,
            json={"allocation_key_id": persons["id"], "value": "3", "valid_from": "2026-07-01"},
            headers=h,
        )
    )
    values = _ok(client.get(url, headers=h), 200)
    assert [(v["value"], v["valid_from"], v["valid_to"]) for v in values] == [
        ("2.00000000", "2026-01-01", "2026-06-30"),
        ("3.00000000", "2026-07-01", None),
    ]
    # Overlap with an existing closed period is a conflict, not a silent overwrite.
    overlap = client.post(
        url,
        json={
            "allocation_key_id": persons["id"],
            "value": "4",
            "valid_from": "2026-03-01",
            "valid_to": "2026-04-30",
        },
        headers=h,
    )
    assert overlap.status_code == 409, overlap.text

    # SEPA mandate with payment types and special levy exclusion (4.5 Zahlungsverkehr).
    mandate = {
        "party_id": tenant,
        "legal_entity_id": entity,
        "contact_bank_account_id": contact["bank_accounts"][0]["id"],
        "reference": f"P1{RUN}"[:35],
        "creditor_id": "DE98ZZZ09999999999",
        "signed_at": "2026-01-01",
        "document_id": DOC,
        "payment_type_codes": ["rent", "operating_cost_advance"],
        "exclude_special_levy": True,
    }
    assert (
        client.post(
            "/api/v1/sepa-mandates",
            json={**mandate, "payment_type_codes": ["no_such_type"]},
            headers=h,
        ).status_code
        == 422
    )
    created = _ok(client.post("/api/v1/sepa-mandates", json=mandate, headers=h))
    assert created["payment_type_codes"] == ["rent", "operating_cost_advance"]
    assert created["exclude_special_levy"] is True
    listed = _ok(client.get("/api/v1/sepa-mandates", params={"party_id": tenant}, headers=h), 200)
    assert listed[0]["exclude_special_levy"] is True

    # Deposit list across contracts (4.5 Kaution): 1.500,00 due, 1.000,00 received.
    deposit = _ok(
        client.post(
            f"/api/v1/contracts/{cid}/deposits",
            json={"kind": "cash", "amount_due": "1500.00", "valid_from": "2026-01-01"},
            headers=h,
        )
    )
    _ok(
        client.post(
            f"/api/v1/deposits/{deposit['id']}/movements",
            json={"date": "2026-01-05", "amount": "1000.00", "kind": "payment"},
            headers=h,
        )
    )
    rows = _ok(client.get("/api/v1/deposits", params={"property_id": prop["id"]}, headers=h), 200)
    assert len(rows) == 1
    assert rows[0]["contract_number"] == contract["number"]
    assert rows[0]["unit_number"] == "01"
    assert (rows[0]["amount_due"], rows[0]["received"], rows[0]["outstanding"]) == (
        "1500.00",
        "1000.00",
        "500.00",
    )
    assert (
        _ok(
            client.get(
                "/api/v1/deposits",
                params={"property_id": prop["id"], "outstanding_only": "true"},
                headers=h,
            ),
            200,
        )[0]["id"]
        == deposit["id"]
    )

    # Termination with meter readings (4.5 Aktionen): unit meter and a foreign unit meter.
    meter = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/meters",
            json={
                "unit_id": unit,
                "meter_type_code": "cold_water",
                "number": f"KW-{RUN}",
                "valid_from": "2024-01-01",
            },
            headers=h,
        )
    )
    foreign_meter = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/meters",
            json={
                "unit_id": unit2,
                "meter_type_code": "cold_water",
                "number": f"KW2-{RUN}",
                "valid_from": "2024-01-01",
            },
            headers=h,
        )
    )
    term_url = f"/api/v1/contracts/{cid}/termination"
    rejected = client.post(
        term_url,
        json={
            "end_date": "2026-09-30",
            "meter_readings": [{"meter_id": foreign_meter["id"], "value": "10"}],
        },
        headers=h,
    )
    assert rejected.status_code == 422, rejected.text
    # The rejected call left no end date and no reading behind (transaction rolled back).
    assert _ok(client.get(f"/api/v1/contracts/{cid}", headers=h), 200)["end_date"] is None
    assert _ok(client.get(f"/api/v1/meters/{meter['id']}/readings", headers=h), 200) == []
    duplicate = client.post(
        term_url,
        json={
            "end_date": "2026-09-30",
            "meter_readings": [
                {"meter_id": meter["id"], "value": "10"},
                {"meter_id": meter["id"], "value": "11"},
            ],
        },
        headers=h,
    )
    assert duplicate.status_code == 422
    ended = _ok(
        client.post(
            term_url,
            json={
                "end_date": "2026-09-30",
                "termination_date": "2026-06-28",
                "move_out_on": "2026-09-28",
                "meter_readings": [{"meter_id": meter["id"], "value": "1234.5"}],
            },
            headers=h,
        ),
        200,
    )
    assert ended["end_date"] == "2026-09-30"
    assert ended["move_out_on"] == "2026-09-28"
    readings = _ok(client.get(f"/api/v1/meters/{meter['id']}/readings", headers=h), 200)
    assert [(r["read_at"], r["value"]) for r in readings] == [("2026-09-30", "1234.50000000")]
    links = _ok(client.get(f"/api/v1/contracts/{cid}/termination-readings", headers=h), 200)
    assert len(links) == 1
    assert links[0]["meter_reading_id"] == readings[0]["id"]
    assert links[0]["read_at"] == "2026-09-30"

    # Ended contracts list and vacancy as of a date.
    ended_ids = [
        c["id"]
        for c in _ok(
            client.get(
                "/api/v1/contracts",
                params={"property_id": prop["id"], "status": "ended", "as_of": "2026-10-01"},
                headers=h,
            ),
            200,
        )
    ]
    assert ended_ids == [cid]
    active_ids = [
        c["id"]
        for c in _ok(
            client.get(
                "/api/v1/contracts",
                params={"property_id": prop["id"], "status": "active", "as_of": "2026-05-01"},
                headers=h,
            ),
            200,
        )
    ]
    assert active_ids == [cid]
    before = _ok(
        client.get(
            f"/api/v1/properties/{prop['id']}/vacancies", params={"as_of": "2026-05-01"}, headers=h
        ),
        200,
    )
    assert [v["unit_number"] for v in before] == ["02"]
    assert before[0]["vacant_since"] is None
    after = _ok(
        client.get(
            f"/api/v1/properties/{prop['id']}/vacancies", params={"as_of": "2026-10-01"}, headers=h
        ),
        200,
    )
    by_unit = {v["unit_number"]: v for v in after}
    assert set(by_unit) == {"01", "02"}
    assert by_unit["01"]["vacant_since"] == "2026-10-01"
    assert by_unit["01"]["previous_contract_id"] == cid

    # Permissions: a caretaker reads, but neither records values nor terminates.
    care = bearer(login(client, world, "p1ccaretaker"))
    assert client.get(url, headers=care).status_code in (200, 403)
    assert (
        client.post(
            url,
            json={"allocation_key_id": persons["id"], "value": "1", "valid_from": "2026-08-01"},
            headers=care,
        ).status_code
        == 403
    )
    assert client.get("/api/v1/deposits", headers=care).status_code in (200, 403)

    # Tenant separation: the other tenant sees nothing of it.
    other = bearer(login(client, world, "p1cother", tenant_id=world.tenant_b))
    assert client.get(url, headers=other).status_code == 404
    assert (
        client.get(f"/api/v1/contracts/{cid}/termination-readings", headers=other).status_code
        == 404
    )
    assert _ok(client.get("/api/v1/deposits", headers=other), 200) == []
    assert (
        client.get(f"/api/v1/properties/{prop['id']}/vacancies", headers=other).status_code == 404
    )
    assert (
        client.get("/api/v1/sepa-mandates", params={"party_id": tenant}, headers=other).json() == []
    )
