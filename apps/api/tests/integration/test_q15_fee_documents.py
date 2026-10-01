"""Q15 (Welle 3): M13-05 PDF document and credit note XRechnung, M13-06 batch issue, M18-06
VAT overview by object, M10-07 year end carry over.

Expected values, computed by hand:
- Fee run: two objects with 2 apartments x 40,00 = 80,00 net, 19 % = 15,20, gross 95,20 each
  (quarter 01.01. to 31.03.2026); numbers PQ-2026-000001 and PQ-2026-000002, a repeat issues
  nothing.
- VAT: revenue line 100,00 net + 19,00 VAT on a unit of object A, 50,00 + 9,50 without unit:
  output VAT 19,00 (object A) and 9,50 (ohne Objekt), total 28,50.
- Carry over 2025: bank 5.000,00 and 001201 20.000,00 give a closing entry and an opening entry
  of 25.000,00 against 009000; the cumulative bank balance stays 5.000,00.
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m6_documents import COMPANY

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
BUCKET = "mhvp-q15"
LEITWEG = "04011000-12345-67"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=2_000_000,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q15a-{RUN}", name=f"Q15 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q15b-{RUN}", name=f"Q15 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("q15admin", a, "tenant_admin"),
            ("q15acc", a, "accountant_no_banking"),
            ("q15care", a, "caretaker"),
            ("q15other", b, "tenant_admin"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Q15 Haus {number}",
                "management_type": "hoa",
                "street": "Rheinpromenade",
                "house_number": number,
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )


def test_fee_run_pdf_and_credit_note_documents(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q15admin"))
    care = bearer(login(client, world, "q15care"))
    other = bearer(login(client, world, "q15other"))
    fees = []
    for number in ("801", "802"):
        prop = _property(client, h, number)
        for no in ("01", "02"):
            _unit(client, h, prop["id"], no)
        fees.append(
            _ok(
                client.post(
                    f"{A}/admin-fees",
                    json={
                        "property_id": prop["id"],
                        "start_date": "2026-01-01",
                        "vat_percent": "19",
                        "amounts_per_unit_type": {"apartment": "40.00"},
                    },
                    headers=h,
                ),
                201,
            )
        )
        _ok(
            client.patch(
                f"{A}/admin-fees/{fees[-1]['id']}", json={"interval": "quarterly"}, headers=h
            )
        )
    body = {"period_date": "2026-02-15", "invoice_date": "2026-04-02"}
    # Before the tax data exist nothing is issued; the preview still works.
    preview = _ok(client.post(f"{A}/admin-fees-run", json=body, headers=h))
    assert preview["confirmed"] is False
    assert [r["status"] for r in preview["rows"]] == ["preview", "preview"]
    assert {r["gross"] for r in preview["rows"]} == {"95.20"}
    assert (
        client.post(f"{A}/admin-fees-run", json={**body, "confirm": True}, headers=h).status_code
        == 409
    )

    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={
                "invoice_prefix": "PQ",
                "vat_status": "regelbesteuert",
                "vat_id": "DE123456789",
                "leitweg_id": LEITWEG,
                "payee_iban": "DE02120300000000202051",
            },
            headers=h,
        )
    )
    _ok(
        client.patch(
            "/api/v1/tenant/settings",
            json={"company": {**COMPANY, "email": "info@example.org", "phone": "+49 2173 000000"}},
            headers=h,
        )
    )
    assert (
        client.post(f"{A}/admin-fees-run", json={**body, "confirm": True}, headers=care).status_code
        == 403
    )
    assert client.post(f"{A}/admin-fees-run", json={**body, "x": 1}, headers=h).status_code == 422
    run = _ok(client.post(f"{A}/admin-fees-run", json={**body, "confirm": True}, headers=h))
    assert run["issued"] == 2
    numbers = sorted(r["number"] for r in run["rows"])
    assert numbers == ["PQ-2026-000001", "PQ-2026-000002"]
    assert {r["gross"] for r in run["rows"]} == {"95.20"}
    again = _ok(client.post(f"{A}/admin-fees-run", json={**body, "confirm": True}, headers=h))
    assert again["issued"] == 0
    assert {r["status"] for r in again["rows"]} == {"already_issued"}
    assert _ok(client.post(f"{A}/admin-fees-run", json=body, headers=other))["rows"] == []

    # M13-05: PDF on the letterhead, idempotent; credit note PDF and XRechnung.
    invoice = run["rows"][0]["invoice_id"]
    doc_url = f"{A}/admin-fee-invoices/{invoice}/document"
    first = _ok(client.post(doc_url, headers=h), 201)
    assert first["created"] is True
    assert _ok(client.post(doc_url, headers=h), 201)["document_id"] == first["document_id"]
    detail = _ok(client.get(f"{A}/admin-fee-invoices/{invoice}", headers=h))
    assert detail["pdf_document_id"] == first["document_id"]
    assert client.post(doc_url, headers=care).status_code == 403
    assert client.post(doc_url, headers=other).status_code == 404
    credit = _ok(
        client.post(
            f"{A}/admin-fee-invoices/{invoice}/cancel",
            json={"reason": "Einheitenzahl korrigiert", "credit_note_date": "2026-04-10"},
            headers=h,
        ),
        201,
    )
    credit_pdf = _ok(client.post(f"{A}/admin-fee-invoices/{credit['id']}/document", headers=h), 201)
    assert credit_pdf["document_id"] != first["document_id"]
    xml_url = f"{A}/admin-fee-invoices/{credit['id']}/xrechnung-credit-note"
    stored = _ok(client.post(f"{xml_url}/document", headers=h), 201)
    assert (
        _ok(client.post(f"{xml_url}/document", headers=h), 201)["document_id"]
        == stored["document_id"]
    )
    assert client.post(f"{xml_url}/document", headers=other).status_code == 404
    # the original invoice is no credit note
    assert (
        client.post(
            f"{A}/admin-fee-invoices/{invoice}/xrechnung-credit-note/document", headers=h
        ).status_code
        == 409
    )
    # the cancelled period can be invoiced again by the next run
    third = _ok(client.post(f"{A}/admin-fees-run", json={**body, "confirm": True}, headers=h))
    assert third["issued"] == 1


def _book(
    client: TestClient,
    h: dict[str, str],
    ledger: str,
    body: dict[str, Any],
    approver: dict[str, str],
) -> dict[str, Any]:
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    if body["kind"] == "opening_balance":
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve", headers=approver))
    return _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))  # type: ignore[no-any-return]


def _ledger(client: TestClient, h: dict[str, str], number: str) -> tuple[str, dict[str, Any], str]:
    prop = _property(client, h, number)
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(client, h, prop["id"], "01")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    return ledger, acc, unit["id"] if isinstance(unit, dict) else unit


def test_vat_overview_by_property(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q15admin"))
    acc_user = bearer(login(client, world, "q15acc"))
    care = bearer(login(client, world, "q15care"))
    other = bearer(login(client, world, "q15other"))
    ledger, acc, unit = _ledger(client, h, "811")
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/accounts/{acc['060100']['id']}/tax-flags",
            json={"eur_relevant": True, "ust_relevant": True, "mixed_use_review": False},
            headers=h,
        )
    )
    for net, vat, unit_id in (("100.00", "19.00", unit), ("50.00", "9.50", None)):
        gross = str(Decimal(net) + Decimal(vat))
        line: dict[str, Any] = {
            "account_id": acc["060100"]["id"],
            "credit": gross,
            "vat_percent": "19",
            "vat_amount": vat,
            "net_amount": net,
        }
        if unit_id:
            line["unit_id"] = unit_id
        _book(
            client,
            h,
            ledger,
            {
                "kind": "custom",
                "booking_date": "2026-03-10",
                "due_date": "2026-03-12",
                "text": "Erlös",
                "lines": [{"account_id": acc["001200"]["id"], "debit": gross}, line],
            },
            acc_user,
        )
    params = {"start": "2026-01-01", "end": "2026-12-31"}
    url = f"{A}/ledgers/{ledger}/reports/vat-overview-by-property"
    out = _ok(client.get(url, params=params, headers=h))
    by_label = {r["property_label"]: r for r in out["rows"]}
    assert Decimal(by_label["ohne Objekt"]["output_vat"]) == Decimal("9.50")
    named = next(r for r in out["rows"] if r["property_id"] is not None)
    assert Decimal(named["output_vat"]) == Decimal("19.00")
    assert Decimal(named["net_revenue"]) == Decimal("100.00")
    assert Decimal(out["total_output_vat"]) == Decimal("28.50")
    plain = _ok(client.get(f"{A}/ledgers/{ledger}/reports/vat-overview", params=params, headers=h))
    assert Decimal(plain["total_output_vat"]) == Decimal(out["total_output_vat"])
    assert "keine Umsatzsteuer-Voranmeldung" in out["note"]
    assert (
        client.get(url, params={"start": "2026-02-01", "end": "2026-01-01"}, headers=h).status_code
        == 422
    )
    assert client.get(url, params=params, headers=other).status_code == 404
    assert client.get(url, params=params, headers=care).status_code in (200, 403)


def test_year_carryover_drafts_and_four_eyes(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q15admin"))
    acc_user = bearer(login(client, world, "q15acc"))
    care = bearer(login(client, world, "q15care"))
    other = bearer(login(client, world, "q15other"))
    ledger, acc, _unit_id = _ledger(client, h, "821")
    _book(
        client,
        h,
        ledger,
        {
            "kind": "opening_balance",
            "booking_date": "2025-01-01",
            "text": "Anfangsbestand",
            "lines": [
                {"account_id": acc["001200"]["id"], "debit": "5000.00"},
                {"account_id": acc["001201"]["id"], "debit": "20000.00"},
                {"account_id": acc["009000"]["id"], "credit": "25000.00"},
            ],
        },
        acc_user,
    )
    url = f"{A}/ledgers/{ledger}/year-carryover"
    view = _ok(client.get(url, params={"fiscal_year": 2025}, headers=h))
    assert {c["number"]: c["balance"] for c in view["carried"]} == {
        "001200": "5000.00",
        "001201": "20000.00",
    }
    assert view["target_date"] == "2026-01-01"
    assert view["already_drafted"] is False
    assert client.post(url, params={"fiscal_year": 2026}, headers=h).status_code == 422  # not over
    assert client.post(url, params={"fiscal_year": 2025}, headers=care).status_code == 403
    assert client.post(url, params={"fiscal_year": 2025}, headers=other).status_code == 404
    drafts = _ok(client.post(url, params={"fiscal_year": 2025}, headers=h), 201)
    assert [d["kind"] for d in drafts] == ["custom", "opening_balance"]
    assert all(d["status"] == "draft" and d["booking_date"] == "2026-01-01" for d in drafts)
    repeat = _ok(client.post(url, params={"fiscal_year": 2025}, headers=h), 201)
    assert [d["id"] for d in repeat] == [d["id"] for d in drafts]
    opening = drafts[1]
    blocked = client.post(f"{A}/ledgers/{ledger}/entries/{opening['id']}/post", headers=h)
    assert blocked.status_code == 403, blocked.text  # four eyes
    assert (
        client.post(f"{A}/ledgers/{ledger}/entries/{opening['id']}/approve", headers=h).status_code
        == 403
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{opening['id']}/approve", headers=acc_user))
    for d in drafts:
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{d['id']}/post", headers=h))
    tb = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/reports/trial-balance", params={"as_of": "2026-06-30"}, headers=h
        )
    )
    assert tb["balanced"] is True
    bank = next(a for a in tb["accounts"] if a["number"] == "001200")
    assert Decimal(bank["balance"]) == Decimal("5000.00")  # cumulative balance unchanged
    done = _ok(client.get(url, params={"fiscal_year": 2025}, headers=h))
    assert done["already_drafted"] is True
