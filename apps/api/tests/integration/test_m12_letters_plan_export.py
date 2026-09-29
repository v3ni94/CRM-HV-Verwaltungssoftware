"""M12 gaps (29.09.2026): letters on the letterhead with dispatch record, Wirtschaftsplan
into the payment plans with preview and second person, Objektakte export for the successor.

Expected values by hand:
* Nachforderungsschreiben: two missing classes of the HOA property, one PDF document linked
  to property, contact and ticket; dispatch ``post`` with registered mail number, status sent.
* Rent increase letter: current 600,00 EUR, target 660,00 EUR (10 %), the PDF names both;
  the case status stays ``draft`` (the process step send is behind G3).
* Plan 2027: hoa_fee 6.000,00 EUR by MEA 600/400 -> 3.600,00 / 2.400,00 a year, monthly
  300,00 / 200,00; reserve 1.200,00 -> 720,00 / 480,00, monthly 60,00 / 40,00. Unit 01 has
  an old standing hoa_fee of 250,00 (create), unit 02 none (create): four rows created.
* Export: ZIP with the one document of the property, einheiten.csv with two units,
  eigentuemer.csv with two owners, the handover log and the personal data note.
"""

import asyncio
import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from pypdf import PdfReader
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m6_documents import COMPANY

pytestmark = pytest.mark.integration
BUCKET = "mhvp-m12-letters"
OBJ = "/api/v1/objektakte"
LET = "/api/v1/letting"
HOA = "/api/v1/hoa"
ACC = "/api/v1/accounting"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m12l-{RUN}", name=f"M12 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"m12lb-{RUN}", name=f"M12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("m12admin", a, "tenant_admin"),
            ("m12second", a, "tenant_admin"),
            ("m12reader", a, "read_only"),
            ("m12other", b, "tenant_admin"),
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
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _contact(c: TestClient, h: dict[str, str], last: str, **extra: Any) -> dict[str, Any]:
    body = {
        "kind": "person",
        "first_name": "Erika",
        "last_name": f"{last}{RUN}",
        "addresses": [
            {
                "street": "Rheinpromenade",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            }
        ],
        **extra,
    }
    return _ok(c.post("/api/v1/contacts", json=body, headers=h), 201)  # type: ignore[no-any-return]


def _letterhead(c: TestClient, h: dict[str, str]) -> None:
    _ok(c.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))


def _pdf_text(c: TestClient, h: dict[str, str], document_id: str) -> str:
    content = c.get(f"/api/v1/documents/{document_id}/content", headers=h)
    assert content.status_code == 200, content.text
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content.content)).pages)


def _hoa_property(
    c: TestClient, h: dict[str, str], number: str
) -> tuple[dict[str, Any], str, dict[str, str]]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"WEG {number}",
                "management_type": "hoa",
                "street": "Musterweg",
                "house_number": "5",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(c.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    return prop, hoa, keys


def _owner(
    c: TestClient,
    h: dict[str, str],
    prop: str,
    no: str,
    mea: str,
    key: str,
    pays: dict[str, str],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    unit = _unit(c, h, prop, no)
    _ok(
        c.post(
            f"/api/v1/units/{unit}/allocation-values",
            json={"allocation_key_id": key, "value": mea, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    party, contact = _party(c, h, f"Eigentuemer{no}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    for code, amount in pays.items():
        _ok(
            c.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": code,
                    "net": amount,
                    "gross": amount,
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )
    return unit, contract, contact


# Gap 1: Nachforderungsschreiben on the letterhead --------------------------------------------


def test_nachforderungsschreiben_pdf_with_dispatch_and_ticket(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "m12admin"))
    reader = bearer(login(client, world, "m12reader"))
    other = bearer(login(client, world, "m12other", tenant_id=world.tenant_b))
    _letterhead(client, h)
    prop, _, _ = _hoa_property(client, h, "811")
    for code, name in (("te", "Teilungserklärung"), ("vv", "Verwaltervertrag")):
        cat = _ok(
            client.post(
                "/api/v1/document-categories",
                json={"code": f"{code}{RUN[:4]}", "name": name},
                headers=h,
            ),
            201,
        )
        _ok(
            client.post(
                f"{OBJ}/required-documents",
                json={"management_type": "hoa", "document_category_id": cat["id"]},
                headers=h,
            ),
            201,
        )
    previous = _contact(client, h, "Vorverwaltung", salutation="Frau")
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Übernahme 811", "property_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    path = f"{OBJ}/properties/{prop['id']}/completeness/nachforderungsschreiben/pdf"
    body = {
        "contact_id": previous["id"],
        "letter_date": "2026-09-29",
        "ticket_id": ticket["id"],
        "dispatch": {
            "channel": "post",
            "sent_on": "2026-09-29",
            "evidence_kind": "registered_mail",
            "evidence_ref": "RR 1234 5678 9DE",
        },
    }
    assert client.post(path, json=body, headers=reader).status_code == 403
    assert client.post(path, json=body, headers=other).status_code == 404
    out = _ok(client.post(path, json=body, headers=h), 201)
    assert [m["name"] for m in out["missing"]] == ["Teilungserklärung", "Verwaltervertrag"]
    assert out["dispatch"]["channel"] == "post"
    assert out["dispatch"]["status"] == "sent"
    assert out["dispatch"]["evidence_ref"] == "RR 1234 5678 9DE"
    assert out["dispatch"]["created_by"] == str(world.users["m12admin"])
    assert out["dispatch"]["sent_at"].startswith("2026-09-29")
    text = _pdf_text(client, h, out["document_id"])
    assert "Fehlende Unterlagen zur Objektakte 811" in text
    assert "1. Teilungserklärung" in text
    assert "Sehr geehrte Frau" in text
    assert COMPANY["name"] in text
    assert "29.09.2026" in text
    document = _ok(client.get(f"/api/v1/documents/{out['document_id']}", headers=h))
    links = {(x["entity_type"], x["entity_id"]) for x in document["links"]}
    assert ("property", prop["id"]) in links
    assert ("contact", previous["id"]) in links
    assert ("ticket", ticket["id"]) in links
    comments = _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))["comments"]
    assert any(out["document_id"] in c.get("document_ids", []) for c in comments)
    # The other tenant never sees the document.
    assert client.get(f"/api/v1/documents/{out['document_id']}", headers=other).status_code == 404
    # No missing class means no letter.
    complete, _, _ = _hoa_property(client, h, "812")
    required = _ok(client.get(f"{OBJ}/required-documents", headers=h))
    for m in out["missing"]:
        row_id = next(
            r["id"] for r in required if r["document_category_id"] == m["document_category_id"]
        )
        assert client.delete(f"{OBJ}/required-documents/{row_id}", headers=h).status_code == 204
    assert (
        client.post(
            f"{OBJ}/properties/{complete['id']}/completeness/nachforderungsschreiben/pdf",
            json={"contact_id": previous["id"]},
            headers=h,
        ).status_code
        == 409
    )


# Gap 1: rent increase letter on the letterhead --------------------------------------------


def test_rent_increase_letter_pdf_records_dispatch_without_sending(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "m12admin"))
    reader = bearer(login(client, world, "m12reader"))
    _letterhead(client, h)
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "813",
                "name": "Miethaus 813",
                "management_type": "rental",
                "street": "Musterweg",
                "house_number": "7",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter813", kind="company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit = _unit(client, h, prop["id"], "01")
    tenant_contact = _contact(client, h, "Mieterin", salutation="Frau")
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": tenant_contact["id"]}]}, headers=h
        ),
        201,
    )["id"]
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/payments",
            json={
                "payment_type_code": "rent",
                "net": "600.00",
                "vat_percent": "0",
                "gross": "600.00",
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    case = _ok(
        client.post(
            f"{LET}/rent-increases",
            json={
                "contract_id": contract["id"],
                "basis": "mietspiegel",
                "target_rent": "660.00",
                "effective_date": "2027-01-01",
                "reference_rent": "600.00",
                "cap_limit_percent": "15",
                "comparison_rent_per_sqm": "11.00",
                "source_note": "Testwerte, keine Rechtsquelle",
                "justification": "mietspiegel",
                "rent_index_name": "Mietspiegel Test 2026",
            },
            headers=h,
        ),
        201,
    )
    path = f"{LET}/rent-increases/{case['id']}/letter/pdf"
    assert client.post(path, json={}, headers=reader).status_code == 403
    # Portal delivery would be a real transmission: refused while G3 is closed.
    gated = client.post(path, json={"dispatch": {"channel": "portal"}}, headers=h)
    assert gated.status_code == 403
    assert gated.json()["code"] == "MHVP-GATE-0001"
    out = _ok(
        client.post(
            path,
            json={
                "letter_date": "2026-09-29",
                "dispatch": {"channel": "post", "sent_on": "2026-09-30", "evidence_ref": "Einwurf"},
            },
            headers=h,
        ),
        201,
    )
    assert out["draft"] is True
    assert out["status"] == "draft"
    assert out["contact_id"] == tenant_contact["id"]
    assert out["dispatch"]["status"] == "sent"
    assert out["dispatch"]["evidence_ref"] == "Einwurf"
    text = _pdf_text(client, h, out["document_id"])
    assert "600,00 EUR" in text
    assert "660,00 EUR" in text
    assert "Mietspiegel Test 2026" in text
    assert "ENTWURF" in text
    assert COMPANY["name"] in text
    # The case did not move: the process step send stays behind G3.
    assert _ok(client.get(f"{LET}/rent-increases/{case['id']}", headers=h))["status"] == "draft"
    document = _ok(client.get(f"/api/v1/documents/{out['document_id']}", headers=h))
    links = {(x["entity_type"], x["entity_id"]) for x in document["links"]}
    assert ("rent_increase_case", case["id"]) in links
    assert ("contract", contract["id"]) in links
    assert ("contact", tenant_contact["id"]) in links
    # E-mail channel prepares a draft for the mailbox only (mail approval), never sends.
    other_contact = _contact(client, h, "Fremd", emails=[{"email": f"fremd-{RUN}@example.org"}])
    wrong = client.post(
        path, json={"contact_id": other_contact["id"], "dispatch": {"channel": "email"}}, headers=h
    )
    assert wrong.status_code == 422
    plain = _ok(client.get(f"{LET}/rent-increases/{case['id']}/letter", headers=h))
    assert "ENTWURF" in plain["text"]
    assert "660,00 EUR" in plain["text"]


# Gap 2: Wirtschaftsplan into the payment plans (W02) -----------------------------------------


def test_plan_apply_preview_confirmation_second_person_idempotent(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "m12admin"))
    h2 = bearer(login(client, world, "m12second"))
    reader = bearer(login(client, world, "m12reader"))
    prop, hoa, keys = _hoa_property(client, h, "814")
    _, c1, _ = _owner(client, h, prop["id"], "01", "600", keys["MEA"], {"hoa_fee": "250.00"})
    _, c2, _ = _owner(client, h, prop["id"], "02", "400", keys["MEA"], {})
    template = _ok(client.post(f"{ACC}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{ACC}/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    plan = _ok(
        client.post(
            f"{HOA}/plans",
            json={"ledger_id": ledger, "year": 2027, "valid_from": "2027-01-01"},
            headers=h,
        ),
        201,
    )
    for component, amount in (("hoa_fee", "6000.00"), ("reserve", "1200.00")):
        _ok(
            client.post(
                f"{HOA}/plans/{plan['id']}/items",
                json={
                    "label": component,
                    "component": component,
                    "amount": amount,
                    "allocation_key_id": keys["MEA"],
                },
                headers=h,
            ),
            201,
        )
    calc = _ok(client.post(f"{HOA}/plans/{plan['id']}/calculate", headers=h))
    preview_path = f"{HOA}/plans/{plan['id']}/apply/preview"
    apply_path = f"{HOA}/plans/{plan['id']}/apply"
    # Before the resolution: preview visible, apply refused (W02, W06).
    early = _ok(client.get(preview_path, headers=h))
    assert early["can_apply"] is False
    assert client.post(apply_path, json={"confirm": True}, headers=h).status_code == 409
    _ok(
        client.post(
            f"{HOA}/plans/{plan['id']}/transition",
            json={"target": "internally_approved"},
            headers=h2,
        )
    )
    resolution = _ok(
        client.post(
            f"{HOA}/resolutions",
            json={
                "legal_entity_id": hoa,
                "decided_on": "2026-11-15",
                "subject": "Wirtschaftsplan 2027",
                "wording": "Der Wirtschaftsplan 2027 wird beschlossen.",
                "status": "positive",
                "subject_type": "economic_plan",
                "subject_id": plan["id"],
                "snapshot_hash": calc["snapshot_hash"],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{HOA}/plans/{plan['id']}/transition",
            json={"target": "resolved", "resolution_id": resolution["id"]},
            headers=h,
        )
    )
    preview = _ok(client.get(preview_path, headers=h))
    assert preview["can_apply"] is True
    assert preview["snapshot_hash"] == calc["snapshot_hash"]
    assert preview["counts"] == {"create": 4, "unchanged": 0, "zero": 0, "no_contract": 0}
    assert preview["posted_months"] == 0
    rows = {(r["unit_number"], r["component"]): r for r in preview["rows"]}
    assert rows[("01", "hoa_fee")]["current"] == "250.00"
    assert rows[("01", "hoa_fee")]["new"] == "300.00"
    assert rows[("02", "hoa_fee")]["current"] is None
    assert rows[("02", "hoa_fee")]["new"] == "200.00"
    assert rows[("01", "reserve")]["new"] == "60.00"
    assert rows[("02", "reserve")]["new"] == "40.00"
    assert rows[("01", "hoa_fee")]["contract_id"] == c1["id"]
    assert rows[("02", "reserve")]["contract_id"] == c2["id"]
    assert "G1" in preview["gates"]["posting"]
    # Authorization, confirmation, stale hash, second person.
    assert client.get(preview_path, headers=reader).status_code == 200  # reading is allowed
    assert (
        client.post(
            apply_path,
            json={"confirm": True, "snapshot_hash": calc["snapshot_hash"]},
            headers=reader,
        ).status_code
        == 403
    )
    assert client.post(apply_path, json={"confirm": False}, headers=h2).status_code == 422
    assert (
        client.post(
            apply_path, json={"confirm": True, "snapshot_hash": "x" * 10}, headers=h2
        ).status_code
        == 409
    )
    same = client.post(
        apply_path, json={"confirm": True, "snapshot_hash": calc["snapshot_hash"]}, headers=h
    )
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    done = _ok(
        client.post(
            apply_path, json={"confirm": True, "snapshot_hash": calc["snapshot_hash"]}, headers=h2
        )
    )
    assert done["payments_created"] == 4
    assert done["applied_at"] is not None
    # Idempotent: a second call creates nothing.
    again = _ok(
        client.post(
            apply_path, json={"confirm": True, "snapshot_hash": calc["snapshot_hash"]}, headers=h2
        )
    )
    assert again["payments_created"] == 0
    assert again["already_applied"] is True
    payments = _ok(client.get(f"/api/v1/contracts/{c1['id']}/payments", headers=h))
    by_type = {}
    for p in payments:
        by_type.setdefault(p["payment_type_code"], []).append(p)
    old, new = sorted(by_type["hoa_fee"], key=lambda p: p["valid_from"])
    assert (old["gross"], old["valid_to"]) == ("250.00", "2026-12-31")
    assert (new["gross"], new["valid_from"], new["valid_to"]) == ("300.00", "2027-01-01", None)
    assert new["reason"] == "adjustment_from_statement"
    assert by_type["reserve"][0]["gross"] == "60.00"
    after = _ok(client.get(preview_path, headers=h))
    assert after["counts"]["unchanged"] == 4
    assert after["can_apply"] is False


# Gap 3: Objektakte export for the successor manager ------------------------------------------


def test_objektakte_export_job_document_download_and_permissions(
    client: TestClient,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    database: Database,
    redis_url: str,
) -> None:
    from mhvp.objektakte import tasks as objektakte_tasks

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        objektakte_tasks.export_property,
        "delay",
        lambda tenant_id, export_id: calls.append((tenant_id, export_id)),
    )
    h = bearer(login(client, world, "m12admin"))
    reader = bearer(login(client, world, "m12reader"))
    other = bearer(login(client, world, "m12other", tenant_id=world.tenant_b))
    prop, _, keys = _hoa_property(client, h, "815")
    _owner(client, h, prop["id"], "01", "500", keys["MEA"], {"hoa_fee": "100.00"})
    _owner(client, h, prop["id"], "02", "500", keys["MEA"], {})
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/meters",
            json={"meter_type_code": "cold_water", "number": "KW-815", "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    uploaded = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("teilungserklaerung.txt", b"Teilungserklaerung Text", "text/plain")},
            data={
                "title": "Teilungserklärung 815",
                "links": json.dumps(
                    [{"entity_type": "property", "entity_id": prop["id"], "role": "original"}]
                ),
            },
            headers=h,
        ),
        201,
    )
    base = f"/api/v1/properties/{prop['id']}/objektakte-export"
    body = {"confirm": True, "personal_data_acknowledged": True, "note": "Übergabe an Nachfolger"}
    # Termination first.
    assert client.post(base, json=body, headers=h).status_code == 409
    successor = _contact(client, h, "Nachfolger")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/terminate",
            json={
                "terminated_by": "hoa",
                "notice_date": "2026-06-30",
                "effective_date": "2026-12-31",
                "successor_manager_contact_id": successor["id"],
            },
            headers=h,
        )
    )
    assert client.post(base, json={"confirm": True}, headers=h).status_code == 422
    assert client.post(base, json=body, headers=reader).status_code == 403
    assert client.post(base, json=body, headers=other).status_code == 404
    started = _ok(client.post(base, json=body, headers=h), 202)
    assert started["status"] == "queued"
    assert calls == [(str(world.tenant_a), started["id"])]
    assert client.post(base, json=body, headers=h).status_code == 409  # one at a time
    settings = _settings(database, redis_url)
    result = asyncio.run(
        objektakte_tasks.export_property_once(settings, world.tenant_a, uuid.UUID(started["id"]))
    )
    assert result == {"status": "done"}
    run = _ok(client.get(f"{base}/{started['id']}", headers=h))
    assert run["status"] == "done", run
    assert run["counts"]["documents"] == 1
    assert run["counts"]["units"] == 2
    assert run["counts"]["owners"] == 2
    assert run["counts"]["meters"] == 1
    assert run["document_id"]
    # Download: permissions, audit event, content.
    assert client.get(f"{base}/{started['id']}/download", headers=reader).status_code == 403
    assert client.get(f"{base}/{started['id']}/download", headers=other).status_code == 404
    download = client.get(f"{base}/{started['id']}/download", headers=h)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/zip")
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    names = archive.namelist()
    assert any(
        n.startswith("01_Dokumente/") and n.endswith("teilungserklaerung.txt") for n in names
    )
    assert {
        "02_Stammdaten/einheiten.csv",
        "02_Stammdaten/eigentuemer.csv",
        "02_Stammdaten/mieter.csv",
        "02_Stammdaten/vertraege.csv",
        "02_Stammdaten/zaehler.csv",
        "03_Offene_Posten/offene_posten.csv",
        "04_Uebergabe/uebergabeprotokoll.txt",
        "04_Uebergabe/datenschutzhinweis.txt",
    } <= set(names)
    units = archive.read("02_Stammdaten/einheiten.csv").decode("utf-8-sig")
    assert units.count("\r\n") == 3  # header and two units
    owners = archive.read("02_Stammdaten/eigentuemer.csv").decode("utf-8-sig")
    assert "Eigentuemer01" in owners
    assert "IBAN" not in owners
    log = archive.read("04_Uebergabe/uebergabeprotokoll.txt").decode("utf-8")
    assert "Nachfolgender Verwalter: " in log
    assert "31.12.2026" in log
    assert "Datenschutzhinweis" in log
    assert uploaded["id"]  # the uploaded document was part of the export
    after = _ok(client.get(f"{base}/{started['id']}", headers=h))
    assert after["download_count"] == 1
    engine = create_engine(database.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(world.tenant_a)},
        )
        types = {
            row[0]
            for row in conn.execute(
                text("SELECT type FROM domain_event WHERE entity_id = :id"), {"id": started["id"]}
            )
        }
    engine.dispose()
    assert {"objektakte_export.requested", "objektakte_export.downloaded"} <= types
    listing = _ok(client.get(base, headers=h))
    assert listing["items"][0]["id"] == started["id"]
    assert "Datenschutzhinweis" in listing["personal_data_note"]
