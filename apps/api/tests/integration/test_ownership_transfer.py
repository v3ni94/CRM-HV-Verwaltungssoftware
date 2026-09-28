"""Eigentümerwechsel in der Oberfläche (operator 28.09.2026, D16, D17): preview, transfer
with carry over of the standing amounts (payments, payment schedule, allocation values valid
on the title transfer date), acquirer as contact, notes, evidence document; validation,
permission (403), tenant separation (404). Expected values are fixed by hand: the seller's
amounts end the day before, the acquirer's copies start on the title transfer date with the
same amounts. No statement split (rule W07, release point P01 stay open). Rows are invented."""

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
DATE = "2026-04-01"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ot-{RUN}", name=f"Wechsel {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ot2-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "otadmin": [(a, "tenant_admin")],
            "otreader": [(a, "read_only")],
            "otother": [(b, "tenant_admin")],
        }
        for name, memberships in specs.items():
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            for tenant_id, role in memberships:
                await services.add_member(
                    factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _weg(client: TestClient, h: dict[str, str], number: str) -> tuple[dict[str, Any], str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"WEG {number}",
                "management_type": "hoa_with_sev",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h)
    )
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building["id"],
                "number": "07",
                "label": "WE 07",
                "unit_type": "apartment",
            },
            headers=h,
        )
    )
    return cast(dict[str, Any], prop), str(unit["id"])


def _contact(client: TestClient, h: dict[str, str], last_name: str) -> str:
    body = {"kind": "person", "first_name": "Erwerb", "last_name": f"{last_name}{RUN}"}
    return str(_ok(client.post("/api/v1/contacts", json=body, headers=h))["id"])


def _party(client: TestClient, h: dict[str, str], last_name: str) -> str:
    contact = _contact(client, h, last_name)
    party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": contact}]}, headers=h)
    )
    return str(party["id"])


def _ownership(client: TestClient, h: dict[str, str], unit: str, party: str) -> dict[str, Any]:
    body = {
        "kind": "ownership",
        "unit_id": unit,
        "party_id": party,
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
        "sev_enabled": True,
    }
    return cast(dict[str, Any], _ok(client.post("/api/v1/contracts", json=body, headers=h)))


def _payment(code: str, amount: str, valid_from: str) -> dict[str, Any]:
    return {
        "payment_type_code": code,
        "net": amount,
        "vat_percent": "0",
        "gross": amount,
        "valid_from": valid_from,
    }


def _document(client: TestClient, h: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("grundbuch.pdf", b"%PDF-1.4 fake extract", "application/pdf")},
        data={"title": "Grundbuchauszug WE 07"},
        headers=h,
    )
    return str(_ok(response)["id"])


def _setup(client: TestClient, h: dict[str, str], number: str) -> tuple[dict[str, Any], str]:
    """WEG with SEV, one unit, seller ownership with Hausgeld 300,00 (history: 250,00 until
    2024), reserve contribution 50,00, monthly schedule and allocation value persons = 2."""
    prop, unit = _weg(client, h, number)
    seller = _party(client, h, "Verkauf")
    contract = _ownership(client, h, unit, seller)
    cid = contract["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{cid}/payments",
            json=_payment("hoa_fee", "250.00", "2020-01-01"),
            headers=h,
        )
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{cid}/payments",
            json=_payment("hoa_fee", "300.00", "2025-01-01"),
            headers=h,
        )
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{cid}/payments",
            json=_payment("reserve", "50.00", "2025-01-01"),
            headers=h,
        )
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{cid}/schedules",
            json={
                "interval": "monthly",
                "due_day_rule": "day",
                "due_day": 3,
                "valid_from": "2020-01-01",
            },
            headers=h,
        )
    )
    key = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/allocation-keys",
            json={
                "code": "PERSONS",
                "name": "Personen",
                "unit_of_measure": "Pers.",
                "kind": "static",
            },
            headers=h,
        )
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{cid}/allocation-values",
            json={"allocation_key_id": key["id"], "value": "2", "valid_from": "2020-01-01"},
            headers=h,
        )
    )
    return contract, prop["id"]


def test_preview_and_transfer_carry_over_standing_amounts(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "otadmin"))
    seller, _ = _setup(client, h, "701")
    sid = seller["id"]
    preview_url = f"/api/v1/contracts/{sid}/ownership-transfer/preview"

    preview = _ok(client.get(preview_url, params={"title_transfer_date": DATE}, headers=h), 200)
    assert preview["old_end_date"] == "2026-03-31"
    assert preview["new_start_date"] == DATE
    assert preview["statement_split"] == "not_implemented"
    assert [(p["payment_type_code"], p["gross"]) for p in preview["payments"]] == [
        ("hoa_fee", "300.00"),
        ("reserve", "50.00"),
    ]
    assert [s["interval"] for s in preview["schedules"]] == ["monthly"]
    assert [(v["allocation_key_code"], v["value"]) for v in preview["allocation_values"]] == [
        ("PERSONS", "2.00000000")
    ]
    # Preview only: nothing changed.
    assert _ok(client.get(f"/api/v1/contracts/{sid}", headers=h), 200)["end_date"] is None
    # A date before the start of the ownership is rejected with the module code.
    early = client.get(preview_url, params={"title_transfer_date": "2019-12-31"}, headers=h)
    assert early.status_code == 422
    assert early.json()["code"] == "MHVP-CONTR-0001"

    acquirer = _contact(client, h, "Kauf")
    document = _document(client, h)
    body = {
        "new_contact_id": acquirer,
        "title_transfer_date": DATE,
        "benefit_burden_date": "2026-03-15",
        "acquisition_kind": "purchase",
        "sev_enabled": True,
        "notes": "Kaufvertrag UR 12/2026",
        "document_id": document,
    }
    new = _ok(client.post(f"/api/v1/contracts/{sid}/ownership-transfer", json=body, headers=h))
    assert new["start_date"] == DATE
    assert new["title_transfer_date"] == DATE
    assert new["benefit_burden_date"] == "2026-03-15"
    assert new["notes"] == "Kaufvertrag UR 12/2026"
    assert new["sev_enabled"] is True
    assert new["party_id"] != seller["party_id"]
    assert new["debtor_account"]["id"] != seller["debtor_account"]["id"]
    # The acquirer's party carries the contact as its only member.
    party = _ok(client.get(f"/api/v1/parties/{new['party_id']}", headers=h), 200)
    assert [m["contact_id"] for m in party["members"]] == [acquirer]

    # Carried over from the title transfer date on, with the same amounts, open ended.
    assert sorted(
        (p["payment_type_code"], p["gross"], p["valid_from"], p["valid_to"])
        for p in new["payments"]
    ) == [
        ("hoa_fee", "300.00", DATE, None),
        ("reserve", "50.00", DATE, None),
    ]
    assert [
        (s["interval"], s["due_day"], s["valid_from"], s["valid_to"]) for s in new["schedules"]
    ] == [("monthly", 3, DATE, None)]
    values = _ok(client.get(f"/api/v1/contracts/{new['id']}/allocation-values", headers=h), 200)
    assert [
        (v["allocation_key_code"], v["value"], v["valid_from"], v["valid_to"]) for v in values
    ] == [("PERSONS", "2.00000000", DATE, None)]
    # The seller's ownership and its rows end the day before; the history stays.
    old = _ok(client.get(f"/api/v1/contracts/{sid}", headers=h), 200)
    assert old["end_date"] == "2026-03-31"
    assert sorted((p["payment_type_code"], p["gross"], p["valid_to"]) for p in old["payments"]) == [
        ("hoa_fee", "250.00", "2024-12-31"),
        ("hoa_fee", "300.00", "2026-03-31"),
        ("reserve", "50.00", "2026-03-31"),
    ]
    assert [s["valid_to"] for s in old["schedules"]] == ["2026-03-31"]
    old_values = _ok(client.get(f"/api/v1/contracts/{sid}/allocation-values", headers=h), 200)
    assert [v["valid_to"] for v in old_values] == ["2026-03-31"]
    # Evidence document linked to the new contract.
    doc = _ok(client.get(f"/api/v1/documents/{document}", headers=h), 200)
    assert ("contract", new["id"], "evidence") in {
        (link["entity_type"], link["entity_id"], link["role"]) for link in doc["links"]
    }
    # A second transfer of the ended ownership is rejected.
    again = client.post(f"/api/v1/contracts/{sid}/ownership-transfer", json=body, headers=h)
    assert again.status_code == 422
    assert again.json()["code"] == "MHVP-CONTR-0001"


def test_transfer_without_carry_over_and_same_owner(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "otadmin"))
    seller, _ = _setup(client, h, "702")
    sid = seller["id"]
    same = client.post(
        f"/api/v1/contracts/{sid}/ownership-transfer",
        json={
            "new_party_id": seller["party_id"],
            "title_transfer_date": DATE,
            "acquisition_kind": "purchase",
        },
        headers=h,
    )
    assert same.status_code == 422
    assert same.json()["code"] == "MHVP-CONTR-0001"
    buyer = _party(client, h, "Ohne")
    new = _ok(
        client.post(
            f"/api/v1/contracts/{sid}/ownership-transfer",
            json={
                "new_party_id": buyer,
                "title_transfer_date": DATE,
                "acquisition_kind": "inheritance",
                "carry_over_amounts": False,
            },
            headers=h,
        )
    )
    assert new["payments"] == []
    assert new["schedules"] == []
    assert _ok(client.get(f"/api/v1/contracts/{new['id']}/allocation-values", headers=h), 200) == []
    old = _ok(client.get(f"/api/v1/contracts/{sid}", headers=h), 200)
    assert old["end_date"] == "2026-03-31"


def test_validation_permission_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "otadmin"))
    seller, _ = _setup(client, h, "703")
    sid = seller["id"]
    buyer = _party(client, h, "Recht")
    good = {"new_party_id": buyer, "title_transfer_date": DATE, "acquisition_kind": "purchase"}
    url = f"/api/v1/contracts/{sid}/ownership-transfer"
    # Exactly one of new_party_id and new_contact_id.
    assert client.post(url, json={**good, "new_contact_id": buyer}, headers=h).status_code == 422
    assert (
        client.post(
            url, json={"title_transfer_date": DATE, "acquisition_kind": "purchase"}, headers=h
        ).status_code
        == 422
    )
    # Unknown contact or document: 404, nothing changed.
    missing = "0192abcd-0000-7000-8000-000000000001"
    assert (
        client.post(
            url, json={**good, "new_party_id": None, "new_contact_id": missing}, headers=h
        ).status_code
        == 404
    )
    assert client.post(url, json={**good, "document_id": missing}, headers=h).status_code == 404
    assert _ok(client.get(f"/api/v1/contracts/{sid}", headers=h), 200)["end_date"] is None

    reader = bearer(login(client, world, "otreader"))
    assert client.post(url, json=good, headers=reader).status_code == 403
    assert (
        client.get(
            f"{url}/preview", params={"title_transfer_date": DATE}, headers=reader
        ).status_code
        == 200
    )
    other = bearer(login(client, world, "otother"))
    assert client.post(url, json=good, headers=other).status_code == 404
    assert (
        client.get(
            f"{url}/preview", params={"title_transfer_date": DATE}, headers=other
        ).status_code
        == 404
    )
    assert _ok(client.get(f"/api/v1/contracts/{sid}", headers=h), 200)["end_date"] is None
