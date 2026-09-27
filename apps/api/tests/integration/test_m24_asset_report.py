"""M24-02 asset report per reporting date (W11) and M24-03 loans in the annual statement.

Expected values by hand (rule 0.1.8), all amounts EUR, year 2025, fresh ledger of WEG 746.

Owners (key MEA): unit 01 600, unit 02 400. Resolved advances (one posted month carries the
whole year, test simplification as in D01): hoa_fee 1.200,00 per unit, reserve 600,00 (01) and
400,00 (02). Payments 05.01.2025: unit 01 hoa_fee 1.200,00 and reserve 600,00 (to 001201),
unit 02 hoa_fee 700,00. Open: unit 02 hoa_fee 500,00 and reserve 400,00 = 900,00.
Cost 043000 800,00 on 01.03.2025 from 001200. Loan A (Sparkasse, 10.000,00 at 3,0 %, instalment
200,00, start 01.04.2025, account 008500): disbursement 10.000,00 posted 01.04.2025, repayment
500,00 and interest 25,00 (043000) posted 02.05.2025, each with a loan item. Loan B (Volksbank,
6.000,00 at 0 %, 12 months, start 15.01.2025, no items, no account).

Asset report as of 31.12.2025:
  001200: 1.200,00 + 700,00 + 10.000,00 - 800,00 - 500,00 - 25,00 = 10.575,00
  001201: 600,00; bank_total 11.175,00
  receivables 900,00 = debtor balance 3.400,00 - 2.500,00 = 900,00
  loans: A residual 10.000,00 - 500,00 = 9.500,00 (account 008500 9.500,00, difference 0,00);
    B residual booked 0,00; loans_total 9.500,00 = loan account balance
  manual item Heizölvorrat 350,00
  assets 11.175,00 + 900,00 + 350,00 = 12.425,00; liabilities 9.500,00; net 2.925,00
  reserve with opening 2.000,00, withdrawals 300,00, interest 10,00: resolved 1.000,00, paid
    600,00, Soll 2.000,00 + 1.000,00 - 300,00 + 10,00 = 2.710,00, Ist 2.310,00, bank 600,00,
    difference 600,00 - 2.310,00 = -1.710,00 -> check reserve_bank fails, not reconciled
  after patch opening 0,00, withdrawals 0,00, interest 0,00: Ist 600,00 = bank -> reconciled

Loan A schedule 2025 (A78 rule, interest = balance * 0,0025 rounded half up):
  01.05. 25,00/175,00 -> 9.825,00; 01.06. 24,56/175,44 -> 9.649,56; 01.07. 24,12/175,88
  -> 9.473,68; 01.08. 23,68/176,32 -> 9.297,36; 01.09. 23,24/176,76 -> 9.120,60; 01.10.
  22,80/177,20 -> 8.943,40; 01.11. 22,36/177,64 -> 8.765,76; 01.12. 21,91/178,09 -> 8.587,67
  planned interest 187,67, planned repayment 1.412,33, residual_schedule 8.587,67
Loan B linear: 500,00 per month from 15.02.2025, 11 instalments in 2025 = 5.500,00 planned
  repayment (source schedule), interest 0,00 (source none), residual_schedule 500,00.

Statement 2025 with cost items 043000 800,00 and Darlehenszinsen 25,00 (manual cost position),
loan A shown by MEA: interest 25,00 -> 15,00 / 10,00; repayment 500,00 -> 300,00 / 200,00.
  cost shares 825,00 -> 495,00 / 330,00; results 495,00 - 1.200,00 = -705,00 and -870,00,
  unchanged by the loan shares (information only).
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m24_hoa import _book_cost, _hoa_ledger, _ok, _owner
from tests.integration.test_m24_loans import _post, _settings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
H = "/api/v1/hoa"
BUCKET = "mhvp-a59"


class OpenG4:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G4


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"vb-{RUN}", name=f"VB {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"vbb-{RUN}", name=f"VBB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("vbadmin", a, "tenant_admin"),
            ("vbreader", a, "read_only"),
            ("vbother", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
        ):
            yield closed, open_


def _pay(
    c: TestClient, h: dict[str, str], ledger: str, item: dict[str, Any], bank: str, amount: str
) -> None:
    draft = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "debtor_payment",
                "booking_date": "2025-01-05",
                "text": "Zahlung",
                "lines": [
                    {"account_id": bank, "debit": amount},
                    {"account_id": item["account_id"], "credit": amount},
                ],
                "settlements": [{"open_item_id": item["id"], "amount": amount}],
            },
            headers=h,
        ),
        201,
    )
    _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))


def _setup(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    w = _hoa_ledger(client, h, "746")
    acc, ledger, keys, prop = w["acc"], w["ledger"], w["keys"], w["property"]
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    _, c1 = _owner(
        client, h, prop, "01", "600", keys["MEA"], {"hoa_fee": "1200.00", "reserve": "600.00"}
    )
    _, c2 = _owner(
        client, h, prop, "02", "400", keys["MEA"], {"hoa_fee": "1200.00", "reserve": "400.00"}
    )
    for c in (c1, c2):
        run = _ok(
            client.post(
                f"{A}/receivable-runs",
                json={"period_month": "2025-01-01", "scope": "contract", "scope_id": c["id"]},
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-01-31"}, headers=h)
    )
    assert len(items) == 4
    for item in items:
        if item["contract_id"] == c1["id"]:
            bank = acc["001201"] if item["remaining"] == "600.00" else acc["001200"]
            _pay(client, h, ledger, item, bank, item["remaining"])
        elif item["remaining"] == "1200.00":
            _pay(client, h, ledger, item, acc["001200"], "700.00")
    _book_cost(client, h, ledger, acc["001200"], acc["043000"], "800.00", "2025-03-01")
    loan_a = _ok(
        client.post(
            f"{H}/loans",
            json={
                "ledger_id": ledger,
                "lender": "Sparkasse",
                "reference": "DL-A",
                "principal": "10000.00",
                "interest_rate_percent": "3.0",
                "instalment": "200.00",
                "start_date": "2025-04-01",
                "purpose": "Dach",
                "account_id": acc["008500"],
            },
            headers=h,
        ),
        201,
    )
    loan_b = _ok(
        client.post(
            f"{H}/loans",
            json={
                "ledger_id": ledger,
                "lender": "Volksbank",
                "principal": "6000.00",
                "interest_rate_percent": "0",
                "term_months": 12,
                "start_date": "2025-01-15",
                "purpose": "Fenster",
            },
            headers=h,
        ),
        201,
    )
    disb = _post(
        client,
        h,
        ledger,
        "2025-04-01",
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
        "2025-05-02",
        "Tilgung",
        [
            {"account_id": acc["008500"], "debit": "500.00"},
            {"account_id": acc["001200"], "credit": "500.00"},
        ],
    )
    inte = _post(
        client,
        h,
        ledger,
        "2025-05-02",
        "Zins",
        [
            {"account_id": acc["043000"], "debit": "25.00"},
            {"account_id": acc["001200"], "credit": "25.00"},
        ],
    )
    for kind, day, amount, entry in [
        ("disbursement", "2025-04-01", "10000.00", disb),
        ("repayment", "2025-05-02", "500.00", rep),
        ("interest", "2025-05-02", "25.00", inte),
    ]:
        _ok(
            client.post(
                f"{H}/loans/{loan_a['id']}/items",
                json={
                    "kind": kind,
                    "booking_date": day,
                    "amount": amount,
                    "journal_entry_id": entry,
                },
                headers=h,
            ),
            201,
        )
    return w | {"loan_a": loan_a["id"], "loan_b": loan_b["id"]}


def test_m24_02_asset_report_and_m24_03_loans(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "vbadmin"))
    hr = bearer(login(client, world, "vbreader"))
    ho = bearer(login(client, world, "vbother"))
    w = _setup(client, h)
    ledger, keys, acc = w["ledger"], w["keys"], w["acc"]

    # --- M24-03: loan year figures and the statement block ------------------------------
    body = {
        "ledger_id": ledger,
        "as_of": "2025-12-31",
        "reserve_opening": "2000.00",
        "reserve_withdrawals": "300.00",
        "reserve_interest": "10.00",
        "manual_items": [
            {"label": "Heizölvorrat", "amount": "350.00", "note": "Lieferschein 12/2025"}
        ],
    }
    assert client.post(f"{H}/asset-reports", json=body, headers=hr).status_code == 403
    report = _ok(client.post(f"{H}/asset-reports", json=body, headers=h), 201)
    assert report["status"] == "draft"
    assert report["draft_notice"]
    rid = report["id"]
    # tenant separation: the other tenant sees nothing
    assert client.get(f"{H}/asset-reports/{rid}", headers=ho).status_code == 404
    assert client.get(f"{H}/asset-reports", params={"ledger_id": ledger}, headers=ho).json() == []
    assert (
        client.get(f"{H}/asset-reports/{rid}/pdf", headers=h).status_code == 409
    )  # not calculated

    calc = _ok(client.post(f"{H}/asset-reports/{rid}/calculate", headers=h))
    snap = calc["snapshot"]
    assert calc["status"] == "calculated"
    assert calc["snapshot_hash"]
    banks = {b["number"]: b for b in snap["bank_accounts"]}
    assert (banks["001200"]["balance"], banks["001201"]["balance"]) == ("10575.00", "600.00")
    assert banks["001201"]["reserve"] is True
    assert snap["bank_total"] == "11175.00"
    assert snap["receivables_total"] == "900.00"
    assert sorted((r["unit_number"], r["remaining"]) for r in snap["receivables"]) == [
        ("02", "400.00"),
        ("02", "500.00"),
    ]
    assert (snap["owner_credits_total"], snap["payables_total"]) == ("0.00", "0.00")
    loans = {loan["lender"]: loan for loan in snap["loans"]}
    assert (
        loans["Sparkasse"]["residual_booked"],
        loans["Sparkasse"]["account_balance"],
        loans["Sparkasse"]["account_difference"],
    ) == ("9500.00", "9500.00", "0.00")
    assert loans["Sparkasse"]["residual_schedule"] == "8587.67"
    assert loans["Sparkasse"]["interest_year"] == {
        "amount": "25.00",
        "source": "booked",
        "booked": "25.00",
        "planned": "187.67",
    }
    assert loans["Sparkasse"]["repayment_year"] == {
        "amount": "500.00",
        "source": "booked",
        "booked": "500.00",
        "planned": "1412.33",
    }
    assert (loans["Volksbank"]["residual_booked"], loans["Volksbank"]["residual_schedule"]) == (
        "0.00",
        "500.00",
    )
    assert loans["Volksbank"]["repayment_year"] == {
        "amount": "5500.00",
        "source": "schedule",
        "booked": "0.00",
        "planned": "5500.00",
    }
    assert loans["Volksbank"]["interest_year"]["source"] == "none"
    assert snap["loans_total"] == "9500.00"
    assert (
        snap["manual_total"],
        snap["assets_total"],
        snap["liabilities_total"],
        snap["net_assets"],
    ) == ("350.00", "12425.00", "9500.00", "2925.00")
    reserve = snap["legal_minimum"]["reserve"]
    assert (reserve["contributions_resolved"], reserve["contributions_paid"]) == (
        "1000.00",
        "600.00",
    )
    assert (
        reserve["target"],
        reserve["actual"],
        reserve["bank_balance"],
        reserve["bank_difference"],
    ) == ("2710.00", "2310.00", "600.00", "-1710.00")
    checks = {c["code"]: c for c in snap["reconciliation"]["checks"]}
    assert snap["reconciliation"]["reconciled"] is False
    assert checks["reserve_bank"]["ok"] is False
    assert checks["reserve_bank"]["difference"] == "1710.00"
    for code in ("journal_balanced", "bank", "receivables", "payables", "loans"):
        assert checks[code]["ok"] is True, checks[code]
    assert checks["receivables"] == {
        "code": "receivables",
        "label": checks["receivables"]["label"],
        "report": "900.00",
        "ledger": "900.00",
        "difference": "0.00",
        "ok": True,
    }

    # Issue: gate closed -> 403; gate open but differences -> 409; reconciled -> issued.
    gh = bearer(login(gated, world, "vbadmin"))
    assert (
        client.post(
            f"{H}/asset-reports/{rid}/transition", json={"target": "issued"}, headers=h
        ).status_code
        == 403
    )
    assert (
        gated.post(
            f"{H}/asset-reports/{rid}/transition", json={"target": "issued"}, headers=gh
        ).status_code
        == 409
    )
    patched = _ok(
        client.patch(
            f"{H}/asset-reports/{rid}",
            json={
                "reserve_opening": "0.00",
                "reserve_withdrawals": "0.00",
                "reserve_interest": "0.00",
            },
            headers=h,
        )
    )
    assert patched["status"] == "draft"
    assert patched["snapshot"] is None
    calc = _ok(client.post(f"{H}/asset-reports/{rid}/calculate", headers=h))
    assert calc["snapshot"]["reconciliation"]["reconciled"] is True
    assert calc["snapshot"]["legal_minimum"]["reserve"]["actual"] == "600.00"

    # PDF draft with letterhead (company data of the tenant, nothing invented).
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    pdf = client.get(f"{H}/asset-reports/{rid}/pdf", headers=h)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    assert client.get(f"{H}/asset-reports/{rid}/pdf", headers=hr).status_code == 200
    assert client.get(f"{H}/asset-reports/{rid}/pdf", headers=ho).status_code == 404

    issued = _ok(
        gated.post(f"{H}/asset-reports/{rid}/transition", json={"target": "issued"}, headers=gh)
    )
    assert issued["status"] == "issued"
    assert issued["issued_at"]
    assert issued["draft_notice"] is None
    assert (
        client.patch(f"{H}/asset-reports/{rid}", json={"note": "x"}, headers=h).status_code == 409
    )
    assert client.post(f"{H}/asset-reports/{rid}/calculate", headers=h).status_code == 409
    listed = _ok(client.get(f"{H}/asset-reports", params={"ledger_id": ledger}, headers=hr))
    assert [r["id"] for r in listed] == [rid]
    assert listed[0]["snapshot"] is None

    annual = _ok(client.get(f"{H}/loans/{w['loan_a']}/annual", params={"year": 2025}, headers=hr))
    assert annual["components"]["interest"]["amount"] == "25.00"
    assert annual["residual_schedule"] == "8587.67"
    assert (
        client.get(f"{H}/loans/{w['loan_a']}/annual", params={"year": 2025}, headers=ho).status_code
        == 404
    )

    # --- M24-03: statement with loan display -------------------------------------------
    st = _ok(
        client.post(f"{H}/statements", json={"ledger_id": ledger, "year": 2025}, headers=h), 201
    )
    sid = st["id"]
    for label, amount in [("Bewirtschaftungskosten", "800.00"), ("Darlehenszinsen", "25.00")]:
        _ok(
            client.post(
                f"{H}/statements/{sid}/costs",
                json={
                    "label": label,
                    "amount": amount,
                    "allocation_key_id": keys["MEA"],
                    "basis": "Beschluss 12.05.2025, Verteilung nach MEA",
                    "account_id": acc["043000"],
                },
                headers=h,
            ),
            201,
        )
    # foreign loan, wrong component and other tenant are refused
    other = _hoa_ledger(client, h, "747")
    foreign = _ok(
        client.post(
            f"{H}/loans",
            json={
                "ledger_id": other["ledger"],
                "lender": "Fremdbank",
                "principal": "1.00",
                "interest_rate_percent": "0",
                "start_date": "2025-01-01",
                "purpose": "fremd",
            },
            headers=h,
        ),
        201,
    )
    alloc = {
        "loans": [
            {
                "loan_id": w["loan_a"],
                "allocation_key_id": keys["MEA"],
                "basis": "Beschluss vom 12.05.2025 TOP 4, Ausweis nach MEA",
            }
        ]
    }
    assert (
        client.put(
            f"{H}/statements/{sid}/loan-allocation",
            json={"loans": [alloc["loans"][0] | {"loan_id": foreign["id"]}]},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{H}/statements/{sid}/loan-allocation",
            json={"loans": [alloc["loans"][0] | {"components": ["fee"]}]},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.put(f"{H}/statements/{sid}/loan-allocation", json=alloc, headers=ho).status_code
        == 404
    )
    assert (
        client.put(f"{H}/statements/{sid}/loan-allocation", json=alloc, headers=hr).status_code
        == 403
    )
    saved = _ok(client.put(f"{H}/statements/{sid}/loan-allocation", json=alloc, headers=h))
    assert saved["loan_allocation"][0]["components"] == ["interest", "repayment"]
    calc = _ok(client.post(f"{H}/statements/{sid}/calculate", headers=h))
    snap = calc["snapshot"]
    block = snap["loans"]
    assert len(block["loans"]) == 1
    assert block["note_text"]
    loan = block["loans"][0]
    assert (
        loan["components"]["interest"]["amount"],
        loan["components"]["repayment"]["amount"],
    ) == ("25.00", "500.00")
    assert loan["residual_booked"] == "9500.00"
    assert loan["basis"].startswith("Beschluss")
    by = {u["unit_number"]: u for u in snap["units"]}
    assert (by["01"]["loan_interest_share"], by["01"]["loan_repayment_share"]) == (
        "15.00",
        "300.00",
    )
    assert (by["02"]["loan_interest_share"], by["02"]["loan_repayment_share"]) == (
        "10.00",
        "200.00",
    )
    assert (by["01"]["cost_share"], by["01"]["result"]) == ("495.00", "-705.00")
    assert (by["02"]["cost_share"], by["02"]["result"]) == ("330.00", "-870.00")
    assert (
        client.put(f"{H}/statements/{sid}/loan-allocation", json=alloc, headers=h).status_code
        == 409
    )
