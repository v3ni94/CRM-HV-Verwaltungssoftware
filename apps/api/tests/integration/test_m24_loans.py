"""W10 loans, insurance claims, measures (A59) and W04 cash flow reconciliation (A60).

Expected values by hand (rule 0.1.8), all amounts EUR:

Loan (test_w10_loan): principal 20.000,00; posted disbursement 20.000,00, posted repayment
1.000,00, planned interest 300,00 and fee 50,00 without journal entry.
  balance_booked = 20.000,00 - 1.000,00 = 19.000,00 (interest and fees never reduce it)
  loan account 008500: credit 20.000,00 - debit 1.000,00 = 19.000,00 -> difference 0,00
  a further disbursement of 1,00 exceeds the principal -> 422

Claim (test_w10_insurance_claim): damage cost 4.000,00 posted, benefit 3.500,00 posted,
deductible 500,00 and recourse 200,00 planned.
  net_burden_booked = 4.000,00 - 3.500,00 - 0,00 (recourse not booked) = 500,00

Reconciliation (test_w04_reconciliation), year 2025, fresh ledger (opening 0,00):
  owner payment                 +3.000,00  (debtor)
  loan disbursement            +10.000,00  (loan item, W10)
  direct cost 043000            -1.200,00  (cost)
  invoice 041000 2.000,00 via creditor 070001, paid 1.500,00 in the year (creditor)
  loan repayment                  -400,00  (loan item)
  transfer 001200 -> 001201      2.500,00  (no counter line: neither inflow nor outflow)
  inflows 13.000,00; outflows 1.200,00 + 1.500,00 + 400,00 = 3.100,00
  closing 13.000,00 - 3.100,00 = 9.900,00 (001200: 7.400,00; 001201: 2.500,00)
  cost booked 1.200,00 + 2.000,00 = 3.200,00; creditor timing 1.500,00 - 2.000,00 = -500,00
  cost paid 3.100,00 - 400,00 = 2.700,00; residual 2.700,00 - (-500,00) - 3.200,00 = 0,00
  distributed: Allgemeinstrom 1.200,00 + Heizkosten (consumption) 2.300,00 = 3.500,00
  unexplained before note: 3.500,00 - 3.200,00 = 300,00 -> blocks
  note heating_accrual +300,00 -> unexplained 0,00 -> releasable
"""

import asyncio
import json
import uuid
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
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m24_hoa import _hoa_ledger, _ok, _owner

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
H = "/api/v1/hoa"
BUCKET = "mhvp-a59"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=200_000,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"a59-{RUN}", name=f"A59 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"a59b-{RUN}", name=f"A59B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("a59admin", a, "tenant_admin"),
            ("a59second", a, "tenant_admin"),
            ("a59reader", a, "read_only"),
            ("a59other", b, "tenant_admin"),
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
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _post(
    c: TestClient,
    h: dict[str, str],
    ledger: str,
    day: str,
    text: str,
    lines: list[dict[str, str]],
    **extra: Any,
) -> str:
    """Posted custom entry; returns its id."""
    draft = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/entries",
            json={"kind": "custom", "booking_date": day, "text": text, "lines": lines, **extra},
            headers=h,
        ),
        201,
    )
    _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    return str(draft["id"])


def test_w10_loan_measure_items_and_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a59admin"))
    hr = bearer(login(client, world, "a59reader"))
    ho = bearer(login(client, world, "a59other"))
    w = _hoa_ledger(client, h, "745")
    acc, ledger = w["acc"], w["ledger"]

    # Measure: the kind needs facts and legal basis, not an account proposal (W10).
    body = {"ledger_id": ledger, "title": "Dachsanierung", "cost_frame": "30000.00"}
    assert (
        client.post(f"{H}/measures", json=body | {"kind": "maintenance"}, headers=h).status_code
        == 422
    )
    measure = _ok(
        client.post(
            f"{H}/measures",
            json=body
            | {
                "kind": "maintenance",
                "kind_basis": "Erneuerung der Dacheindeckung ohne Änderung, Erhaltung "
                "nach Beschluss vom 12.05.2025",
            },
            headers=h,
        ),
        201,
    )
    loan = _ok(
        client.post(
            f"{H}/loans",
            json={
                "ledger_id": ledger,
                "lender": "Sparkasse",
                "reference": "DL-2025-1",
                "principal": "20000.00",
                "interest_rate_percent": "3.5",
                "term_months": 60,
                "instalment": "363.83",
                "start_date": "2025-04-01",
                "purpose": "Teilfinanzierung Dachsanierung",
                "measure_id": measure["id"],
                "account_id": acc["008500"],
            },
            headers=h,
        ),
        201,
    )
    assert loan["status"] == "draft"
    # bank account 001200 is no loan account
    assert (
        client.post(
            f"{H}/loans",
            json={
                "ledger_id": ledger,
                "lender": "X",
                "principal": "1.00",
                "interest_rate_percent": "0",
                "start_date": "2025-04-01",
                "purpose": "falsches Konto",
                "account_id": acc["001200"],
            },
            headers=h,
        ).status_code
        == 422
    )
    for source, extra in [("reserve", {}), ("loan", {"loan_id": loan["id"]})]:
        _ok(
            client.post(
                f"{H}/measures/{measure['id']}/financing",
                json={"source": source, "amount": "10000.00" if source == "reserve" else "20000.00"}
                | extra,
                headers=h,
            ),
            201,
        )
    m = _ok(client.get(f"{H}/measures/{measure['id']}", headers=h))
    assert (m["financed_total"], m["financing_gap"], m["loan_ids"]) == (
        "30000.00",
        "0.00",
        [loan["id"]],
    )

    # Items: only a posted journal entry of the same ledger makes an amount a financial fact.
    disb = _post(
        client,
        h,
        ledger,
        "2025-04-01",
        "Darlehensauszahlung",
        [
            {"account_id": acc["001200"], "debit": "20000.00"},
            {"account_id": acc["008500"], "credit": "20000.00"},
        ],
    )
    rep = _post(
        client,
        h,
        ledger,
        "2025-05-02",
        "Tilgung",
        [
            {"account_id": acc["008500"], "debit": "1000.00"},
            {"account_id": acc["001200"], "credit": "1000.00"},
        ],
    )
    assert (
        client.post(
            f"{H}/loans/{loan['id']}/items",
            json={
                "kind": "disbursement",
                "booking_date": "2025-04-01",
                "amount": "20000.00",
                "journal_entry_id": str(uuid.uuid4()),
            },
            headers=h,
        ).status_code
        == 422
    )
    item = _ok(
        client.post(
            f"{H}/loans/{loan['id']}/items",
            json={
                "kind": "disbursement",
                "booking_date": "2025-04-01",
                "amount": "20000.00",
                "journal_entry_id": disb,
            },
            headers=h,
        ),
        201,
    )
    assert item["booked"] is True
    for kind, amount, entry in [
        ("repayment", "1000.00", rep),
        ("interest", "300.00", None),
        ("fee", "50.00", None),
    ]:
        _ok(
            client.post(
                f"{H}/loans/{loan['id']}/items",
                json={
                    "kind": kind,
                    "booking_date": "2025-05-02",
                    "amount": amount,
                    "journal_entry_id": entry,
                },
                headers=h,
            ),
            201,
        )
    assert (
        client.post(
            f"{H}/loans/{loan['id']}/items",
            json={"kind": "disbursement", "booking_date": "2025-06-01", "amount": "1.00"},
            headers=h,
        ).status_code
        == 422
    )
    report = _ok(client.get(f"{H}/loans/{loan['id']}", headers=h))
    assert report["status"] == "active"
    assert report["balance_booked"] == "19000.00"
    assert (report["account_balance"], report["account_difference"]) == ("19000.00", "0.00")
    assert report["totals"] == {
        "disbursement": {"booked": "20000.00", "planned": "0.00"},
        "repayment": {"booked": "1000.00", "planned": "0.00"},
        "interest": {"booked": "0.00", "planned": "300.00"},
        "fee": {"booked": "0.00", "planned": "50.00"},
    }
    assert [i["kind"] for i in report["items"]] == ["disbursement", "repayment", "interest", "fee"]

    # Document evidence via DocumentLink (6.7).
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("vertrag.txt", b"Darlehensvertrag", "text/plain")},
            data={
                "links": json.dumps(
                    [{"entity_type": "hoa_loan", "entity_id": loan["id"], "role": "attachment"}]
                )
            },
            headers=h,
        ),
        201,
    )
    assert _ok(client.get(f"{H}/loans/{loan['id']}", headers=h))["document_ids"] == [doc["id"]]

    # Authorization and tenant separation.
    assert (
        _ok(client.get(f"{H}/loans", params={"legal_entity_id": w["hoa"]}, headers=hr))[0]["id"]
        == loan["id"]
    )
    assert (
        client.post(
            f"{H}/loans/{loan['id']}/items",
            json={"kind": "fee", "booking_date": "2025-06-01", "amount": "1.00"},
            headers=hr,
        ).status_code
        == 403
    )
    assert client.get(f"{H}/loans/{loan['id']}", headers=ho).status_code == 404
    assert client.get(f"{H}/measures/{measure['id']}", headers=ho).status_code == 404
    assert _ok(client.get(f"{H}/loans", params={"legal_entity_id": w["hoa"]}, headers=ho)) == []


def test_w10_insurance_claim_items(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a59admin"))
    ho = bearer(login(client, world, "a59other"))
    w = _hoa_ledger(client, h, "746")
    acc, ledger = w["acc"], w["ledger"]
    _, contract = _owner(client, h, w["property"], "01", "1000", w["keys"]["MEA"], {})
    claim = _ok(
        client.post(
            f"{H}/insurance-claims",
            json={
                "ledger_id": ledger,
                "title": "Wasserschaden Keller",
                "damage_date": "2025-03-02",
                "insurer": "Gebäudeversicherung AG",
                "policy_reference": "GV-1234",
                "deductible": "500.00",
            },
            headers=h,
        ),
        201,
    )
    cost = _post(
        client,
        h,
        ledger,
        "2025-03-20",
        "Trocknung",
        [
            {"account_id": acc["043000"], "debit": "4000.00"},
            {"account_id": acc["001200"], "credit": "4000.00"},
        ],
    )
    benefit = _post(
        client,
        h,
        ledger,
        "2025-05-15",
        "Versicherungsleistung",
        [
            {"account_id": acc["001200"], "debit": "3500.00"},
            {"account_id": acc["043000"], "credit": "3500.00"},
        ],
    )
    for kind, amount, entry, extra in [
        ("damage_cost", "4000.00", cost, {}),
        ("benefit", "3500.00", benefit, {}),
        ("deductible", "500.00", None, {}),
        ("regress", "200.00", None, {}),
        ("owner_payment", "150.00", None, {"contract_id": contract["id"]}),
    ]:
        _ok(
            client.post(
                f"{H}/insurance-claims/{claim['id']}/items",
                json={
                    "kind": kind,
                    "booking_date": "2025-05-15",
                    "amount": amount,
                    "journal_entry_id": entry,
                }
                | extra,
                headers=h,
            ),
            201,
        )
    assert (
        client.post(
            f"{H}/insurance-claims/{claim['id']}/items",
            json={"kind": "owner_payment", "booking_date": "2025-05-15", "amount": "1.00"},
            headers=h,
        ).status_code
        == 422
    )
    _ok(
        client.patch(
            f"{H}/insurance-claims/{claim['id']}",
            json={"status": "settled", "claim_number": "S-77"},
            headers=h,
        )
    )
    report = _ok(client.get(f"{H}/insurance-claims/{claim['id']}", headers=h))
    assert (report["status"], report["claim_number"]) == ("settled", "S-77")
    assert report["net_burden_booked"] == "500.00"
    assert report["owner_payments_booked"] == "0.00"
    assert report["totals"]["regress"] == {"booked": "0.00", "planned": "200.00"}
    assert report["totals"]["benefit"] == {"booked": "3500.00", "planned": "0.00"}
    assert client.get(f"{H}/insurance-claims/{claim['id']}", headers=ho).status_code == 404


def test_w04_reconciliation_blocks_until_explained(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a59admin"))
    h2 = bearer(login(client, world, "a59second"))
    w = _hoa_ledger(client, h, "747")
    acc, ledger = w["acc"], w["ledger"]
    _, c1 = _owner(client, h, w["property"], "01", "1000", w["keys"]["MEA"], {"hoa_fee": "3000.00"})
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": acc["060100"]},
            headers=h,
        )
    )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2025-01-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-01-31"}, headers=h)
    )[0]
    _post(
        client,
        h,
        ledger,
        "2025-01-05",
        "Hausgeld",
        [
            {"account_id": acc["001200"], "debit": "3000.00"},
            {"account_id": item["account_id"], "credit": "3000.00"},
        ],
        settlements=[{"open_item_id": item["id"], "amount": "3000.00"}],
    )
    creditor = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "070001",
                "name": "Kreditor Heizöl",
                "category": "creditor",
                "type": "liability",
            },
            headers=h,
        ),
        201,
    )["id"]
    _post(
        client,
        h,
        ledger,
        "2025-02-10",
        "Allgemeinstrom",
        [
            {"account_id": acc["043000"], "debit": "1200.00"},
            {"account_id": acc["001200"], "credit": "1200.00"},
        ],
    )
    _post(
        client,
        h,
        ledger,
        "2025-11-20",
        "Heizöl Rechnung",
        [
            {"account_id": acc["041000"], "debit": "2000.00"},
            {"account_id": creditor, "credit": "2000.00"},
        ],
    )
    _post(
        client,
        h,
        ledger,
        "2025-12-05",
        "Heizöl Teilzahlung",
        [
            {"account_id": creditor, "debit": "1500.00"},
            {"account_id": acc["001200"], "credit": "1500.00"},
        ],
    )
    _post(
        client,
        h,
        ledger,
        "2025-06-30",
        "Umbuchung Rücklage",
        [
            {"account_id": acc["001201"], "debit": "2500.00"},
            {"account_id": acc["001200"], "credit": "2500.00"},
        ],
    )
    loan = _ok(
        client.post(
            f"{H}/loans",
            json={
                "ledger_id": ledger,
                "lender": "Bank",
                "principal": "10000.00",
                "interest_rate_percent": "2",
                "start_date": "2025-03-01",
                "purpose": "Fassade",
                "account_id": acc["008500"],
            },
            headers=h,
        ),
        201,
    )
    disb = _post(
        client,
        h,
        ledger,
        "2025-03-01",
        "Auszahlung",
        [
            {"account_id": acc["001200"], "debit": "10000.00"},
            {"account_id": acc["008500"], "credit": "10000.00"},
        ],
    )
    rep = _post(
        client,
        h,
        ledger,
        "2025-09-01",
        "Tilgung",
        [
            {"account_id": acc["008500"], "debit": "400.00"},
            {"account_id": acc["001200"], "credit": "400.00"},
        ],
    )
    for kind, amount, entry in [("disbursement", "10000.00", disb), ("repayment", "400.00", rep)]:
        _ok(
            client.post(
                f"{H}/loans/{loan['id']}/items",
                json={
                    "kind": kind,
                    "booking_date": "2025-09-01",
                    "amount": amount,
                    "journal_entry_id": entry,
                },
                headers=h,
            ),
            201,
        )

    sid = _ok(
        client.post(f"{H}/statements", json={"ledger_id": ledger, "year": 2025}, headers=h), 201
    )["id"]
    for label, amount, number in [
        ("Allgemeinstrom", "1200.00", "043000"),
        ("Heizkosten laut Heizkostenabrechnung", "2300.00", "041000"),
    ]:
        _ok(
            client.post(
                f"{H}/statements/{sid}/costs",
                json={
                    "label": label,
                    "amount": amount,
                    "allocation_key_id": w["keys"]["MEA"],
                    "basis": "Gemeinschaftsordnung",
                    "account_id": acc[number],
                },
                headers=h,
            ),
            201,
        )
    snap = _ok(client.post(f"{H}/statements/{sid}/calculate", headers=h))["snapshot"]
    recon = snap["reconciliation"]
    assert recon["cash"] == {
        "accounts": [
            {
                "number": "001200",
                "name": "WEG-Konto",
                "category": "bank",
                "opening": "0.00",
                "closing": "7400.00",
            },
            {
                "number": "001201",
                "name": "Rücklagenkonto",
                "category": "bank",
                "opening": "0.00",
                "closing": "2500.00",
            },
            {
                "number": "001300",
                "name": "Kasse",
                "category": "cash",
                "opening": "0.00",
                "closing": "0.00",
            },
        ],
        "opening": "0.00",
        "inflows": "13000.00",
        "outflows": "3100.00",
        "closing": "9900.00",
        "check_ok": True,
    }
    assert recon["inflows"] == {"debtor": "3000.00", "loan_disbursement": "10000.00"}
    assert recon["outflows"] == {
        "cost": "1200.00",
        "creditor": "1500.00",
        "loan_repayment": "400.00",
    }
    assert recon["loan_positions"] == {"disbursement": "10000.00", "repayment": "400.00"}
    bridge = {b["code"]: b["amount"] for b in recon["bridge"]}
    assert (bridge["loan"], bridge["cost_paid"], bridge["creditor_timing"]) == (
        "-400.00",
        "2700.00",
        "500.00",
    )
    assert (bridge["structure_residual"], bridge["cost_booked"], bridge["cost_distributed"]) == (
        "0.00",
        "3200.00",
        "3500.00",
    )
    assert recon["unexplained"] == "300.00"

    package = _ok(client.get(f"{H}/statements/{sid}/package", headers=h))
    assert [f["code"] for f in package["blocking"]] == ["reconciliation_unexplained"]
    assert "300.00" in package["blocking"][0]["detail"]
    blocked = client.post(
        f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
    )
    assert blocked.status_code == 409
    assert "Überleitungsrechnung" in blocked.json()["detail"]

    # Explanation without a reason text is refused; the heating accrual closes the bridge.
    assert (
        client.put(
            f"{H}/statements/{sid}/reconciliation-notes",
            json={"notes": [{"code": "heating_accrual", "amount": "300.00", "note": ""}]},
            headers=h,
        ).status_code
        == 422
    )
    st = _ok(
        client.put(
            f"{H}/statements/{sid}/reconciliation-notes",
            json={
                "notes": [
                    {
                        "code": "heating_accrual",
                        "amount": "300.00",
                        "note": "Heizkostenabrechnung 2025: Verbrauch 2.300,00 gegenüber gebuchten Brennstoffkosten 2.000,00",
                    }
                ]
            },
            headers=h,
        )
    )
    assert st["reconciliation_notes"][0]["amount"] == "300.00"
    package = _ok(client.get(f"{H}/statements/{sid}/package", headers=h))
    assert (package["blocking"], package["releasable"]) == ([], True)
    assert package["reconciliation"]["unexplained"] == "0.00"
    assert package["reconciliation"]["explained_manual"][0]["code"] == "heating_accrual"
    approved = _ok(
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    assert approved["status"] == "internally_approved"
    assert (
        client.put(
            f"{H}/statements/{sid}/reconciliation-notes", json={"notes": []}, headers=h
        ).status_code
        == 409
    )
