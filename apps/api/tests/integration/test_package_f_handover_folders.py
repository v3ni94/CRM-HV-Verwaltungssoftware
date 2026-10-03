"""Package F: handover protocol linked to a contract, meter readings taken over from the
protocol into the unit's meter readings, standard categories 04/05 and the folder structure of
the property file, upload with category, contract and contact links.

Expected values by hand: a protocol created with ``contract_id`` answers with the contract
number and party name; the takeover of three protocol meter rows (E-1 matched by number to the
unit meter "E 1", XX without meter, a row with meter_id but no value) creates exactly one
``meter_reading`` with value 12345.678 dated on the handover date and the note
"Übergabeprotokoll UP-…"; a second takeover creates nothing (already_transferred 1); a
protocol without matchable meters gets 409 MHVP-HDOV-0002; confirm=false gets 422
MHVP-HDOV-0001; a read-only member gets 403; a member of another tenant 404. A new tenant has
twelve standard categories including tenant_file (04_Mieterakte) and owner_file
(05_Eigentümerakte); ensure-defaults adds nothing twice; the folder structure lists the six
folders of 11.2 in order with 04 and 05 flagged per unit and person and without invented
subfolders."""

import asyncio
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _property, _unit
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/handover/protocols"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pkf-{RUN}", name=f"PKF {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pkfb-{RUN}", name=f"PKF B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("pkfadmin", a, "tenant_admin"),
            ("pkfreader", a, "read_only"),
            ("pkfother", b, "tenant_admin"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _meter(client: TestClient, h: dict[str, str], prop: str, number: str, unit: str | None) -> Any:
    return _ok(
        client.post(
            f"/api/v1/properties/{prop}/meters",
            json={
                "unit_id": unit,
                "meter_type_code": "electricity",
                "number": number,
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )


def test_contract_link_and_meter_transfer(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pkfadmin"))
    prop = _property(client, h, "840", "rental")
    unit = _unit(client, h, prop["id"], "05")
    owner, _ = _party(client, h, "Vermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenant_party, _ = _party(client, h, "Mieterin")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant_party,
                "start_date": "2025-01-01",
            },
            headers=h,
        ),
        201,
    )
    unit_meter = _meter(client, h, prop["id"], "E 1", unit)
    common_meter = _meter(client, h, prop["id"], "ALLG-7", None)

    # (1) Protocol linked to the contract at creation; the full record carries the summary.
    p = _ok(
        client.post(
            H, json={"kind": "rental", "unit_id": unit, "contract_id": contract["id"]}, headers=h
        ),
        201,
    )
    assert p["contract_id"] == contract["id"]
    assert p["contract"]["number"] == contract["number"]
    assert p["contract"]["party_name"] == f"Test{RUN}, Mieterin"
    assert p["contract"]["kind"] == "tenancy"
    pid = p["id"]
    # Unknown contract on patch and create: 404, the link stays.
    missing = "01920000-0000-7000-8000-00000000dead"
    assert client.patch(f"{H}/{pid}", json={"contract_id": missing}, headers=h).status_code == 404
    assert (
        client.post(H, json={"kind": "rental", "contract_id": missing}, headers=h).status_code
        == 404
    )
    assert _ok(client.get(f"{H}/{pid}", headers=h))["contract"]["id"] == contract["id"]
    # The link can be removed and set again through the patch.
    _ok(client.patch(f"{H}/{pid}", json={"contract_id": None}, headers=h))
    assert _ok(client.get(f"{H}/{pid}", headers=h))["contract"] is None
    _ok(client.patch(f"{H}/{pid}", json={"contract_id": contract["id"]}, headers=h))

    # (2) Meter rows: matched by number (normalised), unmatched, matched by id without value.
    matched = _ok(
        client.post(
            f"{H}/{pid}/meters",
            json={
                "meter_type": "electricity",
                "number": "E-1",
                "value": "12345.678",
                "unit": "kWh",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/{pid}/meters",
            json={"meter_type": "gas", "number": "XX", "value": "10"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/{pid}/meters",
            json={"meter_type": "electricity", "meter_id": common_meter["id"]},
            headers=h,
        ),
        201,
    )
    transfer = f"{H}/{pid}/meters/transfer"
    not_confirmed = client.post(transfer, json={"confirm": False}, headers=h)
    assert not_confirmed.status_code == 422, not_confirmed.text
    assert not_confirmed.json()["code"] == "MHVP-HDOV-0001"
    assert _ok(client.get(f"/api/v1/meters/{unit_meter['id']}/readings", headers=h)) == []

    reader = bearer(login(client, world, "pkfreader"))
    assert client.post(transfer, json={"confirm": True}, headers=reader).status_code == 403
    other = bearer(login(client, world, "pkfother"))
    assert client.post(transfer, json={"confirm": True}, headers=other).status_code == 404

    result = _ok(client.post(transfer, json={"confirm": True}, headers=h))
    assert [x["item_id"] for x in result["created"]] == [matched["id"]]
    assert result["created"][0]["meter_id"] == unit_meter["id"]
    assert result["created"][0]["value"] == "12345.678"
    assert result["created"][0]["read_at"] == local_today().isoformat()
    assert sorted(x["reason"] for x in result["skipped"]) == ["no_meter", "no_value"]
    assert result["already_transferred"] == []
    readings = _ok(client.get(f"/api/v1/meters/{unit_meter['id']}/readings", headers=h))
    assert len(readings) == 1
    assert Decimal(readings[0]["value"]) == Decimal("12345.678")
    assert readings[0]["source"] == "manual"
    assert readings[0]["read_at"] == local_today().isoformat()
    assert readings[0]["notes"] == f"Übergabeprotokoll {p['number']}"
    full = _ok(client.get(f"{H}/{pid}", headers=h))
    row = next(m for m in full["meters"] if m["id"] == matched["id"])
    assert row["meter_reading_id"] == readings[0]["id"]
    assert row["meter_id"] == unit_meter["id"]

    # Idempotent: the second call creates nothing and reports the row as taken over.
    again = _ok(client.post(transfer, json={"confirm": True}, headers=h))
    assert again["created"] == []
    assert [x["item_id"] for x in again["already_transferred"]] == [matched["id"]]
    assert len(_ok(client.get(f"/api/v1/meters/{unit_meter['id']}/readings", headers=h))) == 1

    # Takeover works on a completed protocol too (the usual case after signing). The locked
    # row keeps its content: only the link meter_reading_id is written, meter_id stays.
    late = _ok(
        client.post(
            f"{H}/{pid}/meters",
            json={"meter_type": "electricity", "number": "E 1", "value": "12350"},
            headers=h,
        ),
        201,
    )
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    _ok(client.post(f"{H}/{pid}/complete", json={"force": True}, headers=h))
    after = _ok(client.post(transfer, json={"confirm": True}, headers=h))
    assert [x["item_id"] for x in after["created"]] == [late["id"]]
    assert after["created"][0]["meter_id"] == unit_meter["id"]
    assert len(after["already_transferred"]) == 1
    full = _ok(client.get(f"{H}/{pid}", headers=h))
    assert full["locked"] is True
    late_row = next(m for m in full["meters"] if m["id"] == late["id"])
    assert late_row["meter_reading_id"] == after["created"][0]["meter_reading_id"]
    assert late_row["meter_id"] is None
    assert Decimal(late_row["value"]) == Decimal("12350")
    readings = _ok(client.get(f"/api/v1/meters/{unit_meter['id']}/readings", headers=h))
    assert len(readings) == 2
    assert _ok(client.post(transfer, json={"confirm": True}, headers=h))["created"] == []

    # Nothing matchable: protocol without unit, 409 with the registered code.
    empty = _ok(client.post(H, json={"kind": "general"}, headers=h), 201)
    _ok(
        client.post(f"{H}/{empty['id']}/meters", json={"number": "E-1", "value": "1"}, headers=h),
        201,
    )
    nothing = client.post(f"{H}/{empty['id']}/meters/transfer", json={"confirm": True}, headers=h)
    assert nothing.status_code == 409, nothing.text
    assert nothing.json()["code"] == "MHVP-HDOV-0002"
    # Cancelled protocols are never taken over.
    _ok(client.post(f"{H}/{empty['id']}/status", json={"action": "cancel"}, headers=h))
    assert (
        client.post(
            f"{H}/{empty['id']}/meters/transfer", json={"confirm": True}, headers=h
        ).status_code
        == 422
    )


def test_folder_structure_categories_and_upload_links(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pkfadmin"))
    categories = _ok(client.get("/api/v1/document-categories", headers=h))
    by_code = {c["code"]: c for c in categories}
    assert by_code["tenant_file"]["drive_folder"] == "04_Mieterakte"
    assert by_code["tenant_file"]["name"] == "Mieterakte"
    assert by_code["owner_file"]["drive_folder"] == "05_Eigentümerakte"
    assert by_code["owner_file"]["name"] == "Eigentümerakte"
    assert len(categories) == 12

    # ensure-defaults is idempotent and needs tenant_settings:update. Since GAJ-301 it also
    # creates the payment_file category (sort order 900) that locks payment files behind G2.
    ensured = _ok(client.post("/api/v1/document-categories/ensure-defaults", headers=h))
    assert len(ensured) == 13
    assert {c["code"] for c in ensured} == set(by_code) | {"payment_file"}
    assert len(_ok(client.post("/api/v1/document-categories/ensure-defaults", headers=h))) == 13
    reader = bearer(login(client, world, "pkfreader"))
    assert (
        client.post("/api/v1/document-categories/ensure-defaults", headers=reader).status_code
        == 403
    )

    folders = _ok(client.get("/api/v1/document-folders", headers=h))
    assert [f["folder"] for f in folders] == [
        "01_Legitimationsunterlagen",
        "02_Stammakte",
        "03_Buchhaltung",
        "04_Mieterakte",
        "05_Eigentümerakte",
        "06_Sonstiges",
    ]
    tenant_file = folders[3]
    assert tenant_file["per_unit_and_person"] is True
    assert [c["code"] for c in tenant_file["categories"]] == ["tenant_file"]
    assert tenant_file["subfolders"] == []
    assert tenant_file["subfolders_source"] is None
    assert folders[0]["per_unit_and_person"] is False
    assert folders[0]["description"].startswith("Ausweiskopien")
    assert {c["code"] for c in folders[1]["categories"]} == {
        "contract",
        "minutes",
        "insurance",
        "declaration_of_division",
    }
    assert client.get("/api/v1/document-folders", headers=reader).status_code == 200

    # Upload with category, contract and contact links (the fields of the new upload dialog).
    prop = _property(client, h, "841", "rental")
    unit = _unit(client, h, prop["id"], "01")
    owner, _ = _party(client, h, "Eigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    party, contact = _party(client, h, "Mieter")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2025-01-01",
            },
            headers=h,
        ),
        201,
    )
    links = [
        {"entity_type": "unit", "entity_id": unit, "role": "original"},
        {"entity_type": "contract", "entity_id": contract["id"], "role": "original"},
        {"entity_type": "contact", "entity_id": contact["id"], "role": "original"},
    ]
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("mietvertrag.pdf", b"%PDF-1.4\n%mock\n", "application/pdf")},
            data={
                "title": "WE 01, Mietvertrag",
                "category_id": by_code["tenant_file"]["id"],
                "links": json.dumps(links),
            },
            headers=h,
        ),
        201,
    )
    assert doc["category_id"] == by_code["tenant_file"]["id"]
    assert {(x["entity_type"], x["entity_id"]) for x in doc["links"]} == {
        ("unit", unit),
        ("contract", contract["id"]),
        ("contact", contact["id"]),
    }
    # Tenant separation: the other tenant sees its own categories only, never this document.
    other = bearer(login(client, world, "pkfother"))
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=other).status_code == 404
    assert len(_ok(client.get("/api/v1/document-folders", headers=other))) == 6
