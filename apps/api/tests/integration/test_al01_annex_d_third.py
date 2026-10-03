"""AL01 (GAI-612 rest of AK09, rule 0.1.8): second independent tests for the annex D cases
D05, D06, D15, D18 and D20, which were named by a single test only (SINGLE_TEST_CASES in
tests/unit/test_aj19_test_guards.py).

Each test computes its expected values by hand in the docstring before the run; no value is
taken from an observed result. The tests use their own world (tenant slug and user names with
the prefix ``al01``) and vary inputs or path compared with the first test of the case (other
amounts, other order of the import files, an extra bank status step, another transfer and
resolution date, another sub community, two charged instalments), so a shared error in one
scenario does not hide behind two identical tests. G1, G2 and G4 are opened only through the
test resolver of the second client; the productive flags stay off.
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m15_payments import _debit
from tests.integration.test_m24_hoa import _book_cost, _owner

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
H = "/api/v1/hoa"
# Synthetic IBANs with a valid check digit (no real data), as in the other banking tests.
D05_BANK = "DE02500105170137075030"
D05_PAYER = "DE27100777770209299700"
OWN = "DE02120300000000202051"
PROVIDER = "DE91100000000123456789"
USERS = (
    ("al01admin", "tenant_admin"),
    ("al01acc", "accountant_banking"),
    ("al01approver", "tenant_admin"),
    ("al01second", "tenant_admin"),
)


class OpenGates:
    """Opens G1, G2 and G4 for the second client; G3 and G5 stay closed."""

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G2, ReleaseGate.G4)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"al01-{RUN}", name=f"AL01 Anhang D {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in USERS:
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenGates())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _hoa_ledger(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AL01 WEG {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    return {"property": prop["id"], "hoa": hoa, "keys": keys, "ledger": ledger, "acc": acc}


def _bank(
    client: TestClient, h: dict[str, str], w: dict[str, Any], iban: str, number: str
) -> tuple[str, str]:
    """Property bank account of the HOA plus its own linked ledger bank account."""
    bank = _ok(
        client.post(
            f"/api/v1/properties/{w['property']}/bank-accounts",
            json={
                "legal_entity_id": w["hoa"],
                "kind": "hoa",
                "iban": iban,
                "holder": f"GdWE AL01 {number}",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    account = _ok(
        client.post(
            f"{A}/ledgers/{w['ledger']}/accounts",
            json={
                "number": number,
                "name": "Bank AL01",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank,
            },
            headers=h,
        ),
        201,
    )["id"]
    return str(bank), str(account)


def _balances(client: TestClient, h: dict[str, str], ledger: str) -> dict[str, Decimal]:
    return {
        a["number"]: Decimal(a["balance"])
        for a in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-12-31"}, headers=h
            )
        )["accounts"]
    }


def _post(
    client: TestClient,
    h: dict[str, str],
    ledger: str,
    kind: str,
    day: str,
    lines: list[dict[str, str]],
    settlements: list[dict[str, str]] | None = None,
) -> None:
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": kind,
                "booking_date": day,
                "text": "AL01",
                "lines": lines,
                "settlements": settlements or [],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))


def _open_items(client: TestClient, h: dict[str, str], ledger: str, as_of: str) -> list[Any]:
    return _ok(  # type: ignore[no-any-return]
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": as_of}, headers=h)
    )


# D05: equal real payments, re-imported in another file order --------------------------------


@pytest.mark.annex_d("D05")
def test_al01_equal_payments_reimported_one_by_one_and_in_reverse(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D05 second test, other path than the first one: the two original records (400,00 each,
    same payer, same day 2026-01-12, same purpose, bank references AL01-R1 and AL01-R2) arrive
    in one file; they are not booked. Re-import first as two single record files (R2 alone,
    then R1 alone), then once more as one file in reverse order.
    Expected by hand: first import 2 new, sum 400 + 400 = 800,00. Each single file: 0 new,
    1 duplicate. Reverse file: 0 new, 2 duplicates. After all imports: exactly 2 transactions,
    800,00 (neither 400,00 nor 1.600,00 nor 2.400,00 after three re-imports), references
    {AL01-R1, AL01-R2}; no journal entry is written by an import (entry count unchanged)."""
    client, _ = clients
    h = bearer(login(client, world, "al01admin"))
    w = _hoa_ledger(client, h, "951")
    bank, _ = _bank(client, h, w, D05_BANK, "001215")

    def record(ref: str) -> str:
        return _ntry(ref, "400.00", "CRDT", "2026-01-12", D05_PAYER, "Hausgeld Januar 01")

    def imp(name: str, refs: list[str], closing: str) -> dict[str, Any]:
        data = _camt(f"AL01-{name}", D05_BANK, "0.00", closing, [record(r) for r in refs])
        return _ok(  # type: ignore[no-any-return]
            client.post(
                f"{B}/imports",
                json={"document_id": _upload(client, h, f"{name}.xml", data)},
                headers=h,
            ),
            201,
        )["counts"]

    def txs() -> list[dict[str, Any]]:
        return _ok(  # type: ignore[no-any-return]
            client.get(f"{B}/transactions", params={"bank_account_id": bank}, headers=h)
        )

    entries_before = len(_ok(client.get(f"{A}/ledgers/{w['ledger']}/entries", headers=h)))
    first = imp("al01-d05", ["AL01-R1", "AL01-R2"], "800.00")
    assert first["new"] == 2
    assert sum(Decimal(t["amount"]) for t in txs()) == Decimal("800.00")
    for name, refs, closing in (
        ("al01-d05-r2", ["AL01-R2"], "400.00"),
        ("al01-d05-r1", ["AL01-R1"], "400.00"),
    ):
        counts = imp(name, refs, closing)
        assert (counts["new"], counts["duplicates"]) == (0, 1)
    counts = imp("al01-d05-rev", ["AL01-R2", "AL01-R1"], "800.00")
    assert (counts["new"], counts["duplicates"]) == (0, 2)
    after = txs()
    assert len(after) == 2
    assert sorted(Decimal(t["amount"]) for t in after) == [Decimal("400.00")] * 2
    assert sum(Decimal(t["amount"]) for t in after) == Decimal("800.00")
    assert {t["bank_reference"] for t in after} == {"AL01-R1", "AL01-R2"}
    entries_after = len(_ok(client.get(f"{A}/ledgers/{w['ledger']}/entries", headers=h)))
    assert entries_after == entries_before


# D06: payment is not the export, with an extra bank acceptance step --------------------------


@pytest.mark.annex_d("D06")
def test_al01_export_submission_and_bank_acceptance_pay_nothing(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D06 second test with the extra status accepted_by_bank and another cost account (043000
    instead of 040300): released invoice 1.190,00, no other payment.
    Expected by hand: after export, submission and acceptance by the bank the payable stays
    open with 1.190,00 and the bank account 001216 stays 0,00. Execution with the bank
    transaction settles once: open items [], bank 0,00 - 1.190,00 = -1.190,00, cost account
    043000 +1.190,00. A second executed feedback returns the same journal entry; bank stays
    -1.190,00 (not -2.380,00)."""
    client, gated = clients
    h = bearer(login(client, world, "al01admin"))
    acc_user = bearer(login(client, world, "al01acc"))
    approver = bearer(login(client, world, "al01approver"))
    gh = bearer(login(gated, world, "al01acc"))
    w = _hoa_ledger(client, h, "952")
    bank, _ = _bank(client, h, w, OWN, "001216")
    ledger = w["ledger"]
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"AL01 Dienst {RUN} GmbH",
                "bank_accounts": [{"iban": PROVIDER, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, approver, provider)
    inv = _ok(
        client.post(
            f"{A}/invoices",
            json={
                "ledger_id": ledger,
                "provider_contact_id": provider,
                "number": "AL01-D06",
                "invoice_date": "2026-02-01",
                "due_date": "2026-02-20",
                "service_from": "2026-01-01",
                "net": "1190.00",
                "vat": "0.00",
                "gross": "1190.00",
                "payee_iban": PROVIDER,
                "lines": [{"account_id": w["acc"]["043000"], "net": "1190.00"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    for step in ("completeness", "factual", "arithmetic_tax"):
        _ok(
            client.post(
                f"{A}/invoices/{inv}/reviews",
                json={"step": step, "result": "ok", "reason": "geprüft"},
                headers=h,
            ),
            201,
        )
    _ok(client.post(f"{A}/invoices/{inv}/release", headers=acc_user))
    _ok(client.post(f"{A}/invoices/{inv}/post", headers=h))

    def remaining() -> list[Decimal]:
        return sorted(Decimal(i["remaining"]) for i in _open_items(client, h, ledger, "2026-12-31"))

    def bank_balance() -> Decimal:
        return _balances(client, h, ledger).get("001216", Decimal("0.00"))

    assert remaining() == [Decimal("1190.00")]
    order = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv,
                "property_bank_account_id": bank,
                "execution_date": "2026-02-05",
            },
            headers=h,
        ),
        201,
    )
    assert order["amount"] == "1190.00"
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=h))
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=acc_user))
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    batch = _ok(
        gated.post(f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=gh), 201
    )
    assert (remaining(), bank_balance()) == ([Decimal("1190.00")], Decimal("0.00"))
    for status in ("submitted", "accepted_by_bank"):
        _ok(
            gated.post(
                f"{B}/payment-batches/{batch['id']}/bank-status",
                json={"status": status},
                headers=gh,
            )
        )
        assert (remaining(), bank_balance()) == ([Decimal("1190.00")], Decimal("0.00")), status
    stmt = _camt(
        "AL01-D06",
        OWN,
        "3000.00",
        "1810.00",
        [_debit("AL01-D06-1", "1190.00", order["end_to_end_id"])],
    )
    _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "al01-d06.xml", stmt)},
            headers=h,
        ),
        201,
    )
    tx = next(
        t
        for t in _ok(client.get(f"{B}/transactions", params={"bank_account_id": bank}, headers=h))
        if t["bank_reference"] == "AL01-D06-1"
    )
    feedback = {"status": "executed", "bank_transaction_id": tx["id"]}
    done = _ok(
        gated.post(f"{B}/payment-batches/{batch['id']}/bank-status", json=feedback, headers=gh)
    )
    assert done[0]["status"] == "executed"
    assert remaining() == []
    assert bank_balance() == Decimal("-1190.00")
    again = _ok(
        gated.post(f"{B}/payment-batches/{batch['id']}/bank-status", json=feedback, headers=gh)
    )
    assert again[0]["journal_entry_id"] == done[0]["journal_entry_id"]
    assert bank_balance() == Decimal("-1190.00")
    assert _balances(client, h, ledger)["043000"] == Decimal("1190.00")


# D15: owner change, other amounts and dates ---------------------------------------------------


@pytest.mark.annex_d("D15")
def test_al01_owner_change_seller_keeps_arrears_buyer_gets_result(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D15 second test (ordinary purchase, no special liability), other numbers than the first:
    MEA 1.000 / 1.000; hoa_fee 1.500,00 resolved for 2025 per unit (one posted run, due day 3);
    seller of 01 paid 1.200,00 (arrears 1.500 - 1.200 = 300,00), owner of 02 paid 1.500,00.
    Costs 4.000,00 -> 2.000,00 per unit. Result 01: 2.000 - 1.500 = 500,00; result 02 also
    500,00, arrears 02 0,00. Title transfer of 01 to the buyer on 15.02.2026, resolution on
    20.06.2026.
    Expected: the snapshot shows the seller as the only 2025 owner of 01 (365 days); posting
    writes 2 entries; the buyer's contract gets exactly one open item 500,00 due 20.06.2026,
    the seller's contract keeps exactly its open item 300,00; the buyer has a new debtor
    account."""
    client, gated = clients
    h = bearer(login(client, world, "al01admin"))
    h2 = bearer(login(client, world, "al01second"))
    gh = bearer(login(gated, world, "al01admin"))
    w = _hoa_ledger(client, h, "953")
    _, seller = _owner(
        client, h, w["property"], "01", "1000", w["keys"]["MEA"], {"hoa_fee": "1500.00"}
    )
    _, other = _owner(
        client, h, w["property"], "02", "1000", w["keys"]["MEA"], {"hoa_fee": "1500.00"}
    )
    ledger, acc = w["ledger"], w["acc"]
    for code in ("hoa_fee", "statement_result"):
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc["060100"]},
                headers=h,
            )
        )
    for c in (seller, other):
        run = _ok(
            client.post(
                f"{A}/receivable-runs",
                json={"period_month": "2025-01-01", "scope": "contract", "scope_id": c["id"]},
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    paid = {seller["id"]: "1200.00", other["id"]: "1500.00"}
    for item in _open_items(client, h, ledger, "2025-01-31"):
        pay = paid[item["contract_id"]]
        _post(
            client,
            h,
            ledger,
            "debtor_payment",
            "2025-01-06",
            [
                {"account_id": acc["001200"], "debit": pay},
                {"account_id": item["account_id"], "credit": pay},
            ],
            [{"open_item_id": item["id"], "amount": pay}],
        )
    _book_cost(client, h, ledger, acc["001200"], acc["043000"], "4000.00", "2025-04-01")
    buyer_party, _ = _party(client, h, "AL01KaeuferD15")
    buyer = _ok(
        client.post(
            f"/api/v1/contracts/{seller['id']}/ownership-transfer",
            json={
                "new_party_id": buyer_party,
                "title_transfer_date": "2026-02-15",
                "benefit_burden_date": "2026-03-01",
                "acquisition_kind": "purchase",
            },
            headers=h,
        ),
        201,
    )
    assert buyer["debtor_account"]["number"] != seller["debtor_account"]["number"]
    st = _ok(
        client.post(
            f"{H}/statements",
            json={
                "ledger_id": ledger,
                "year": 2025,
                "reserve_opening": "0.00",
                "reserve_withdrawals": "0.00",
                "reserve_interest": "0.00",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/statements/{st['id']}/costs",
            json={
                "label": "Bewirtschaftungskosten",
                "amount": "4000.00",
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
                "account_id": acc["043000"],
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(client.post(f"{H}/statements/{st['id']}/calculate", headers=h))
    by = {u["unit_number"]: u for u in calc["snapshot"]["units"]}
    assert (by["01"]["result"], by["01"]["arrears"]) == ("500.00", "300.00")
    assert (by["02"]["result"], by["02"]["arrears"]) == ("500.00", "0.00")
    assert [(p["contract_id"], p["days"]) for p in by["01"]["ownership_periods"]] == [
        (seller["id"], 365)
    ]
    sid = st["id"]
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    res = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2026-06-20",
                "subject": "Abrechnung 2025",
                "wording": "Die Abrechnungsspitzen 2025 werden beschlossen.",
                "status": "positive",
                "subject_type": "hoa_statement",
                "subject_id": sid,
                "snapshot_hash": calc["snapshot_hash"],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition",
            json={"target": "resolved", "resolution_id": res["id"]},
            headers=h,
        )
    )
    for target in ("issued", "due"):
        _ok(gated.post(f"{H}/statements/{sid}/transition", json={"target": target}, headers=gh))
    posted = _ok(gated.post(f"{H}/statements/{sid}/post", headers=gh))
    assert len(posted["posted_entry_ids"]) == 2
    open_: dict[str, list[tuple[str, str]]] = {}
    for i in _open_items(client, h, ledger, "2026-12-31"):
        open_.setdefault(i["contract_id"], []).append((i["remaining"], i["due_date"]))
    assert [r for r, _ in open_[seller["id"]]] == ["300.00"]
    assert open_[buyer["id"]] == [("500.00", "2026-06-20")]


# D18: sub community of units 02 and 03 ------------------------------------------------------


@pytest.mark.annex_d("D18")
def test_al01_sub_community_filter_blocks_until_declaration_is_named(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D18 second test with another sub community (units 02 and 03 of three, values 300 / 600)
    and the declaration of division instead of a resolution as source.
    Item 900,00 on key HAUS_B: 900 * 300 / 900 = 300,00 for 02 and 900 * 600 / 900 = 600,00
    for 03, unit 01 gets nothing from it. A second item 900,00 on MEA (1.000 each, 300,00 per
    unit) covers all units, so the only finding is the sub community; booked costs 1.800,00. With the free basis "Filter Haus B" the package blocks with
    scope_unfounded, releasable false, the internal approval is refused (409) and the status
    stays calculated. The same split with "Teilungserklärung vom 01.03.2019, § 6: Kosten
    Haus B nur Einheiten 02 und 03" has no finding and is approvable."""
    client, _ = clients
    h = bearer(login(client, world, "al01admin"))
    h2 = bearer(login(client, world, "al01second"))
    w = _hoa_ledger(client, h, "954")
    units = {
        no: _owner(client, h, w["property"], no, "1000", w["keys"]["MEA"], {})[0]
        for no in ("01", "02", "03")
    }
    haus_b = _ok(
        client.post(
            f"/api/v1/properties/{w['property']}/allocation-keys",
            json={"code": "HAUS_B", "name": "Haus B", "unit_of_measure": "MEA", "kind": "static"},
            headers=h,
        ),
        201,
    )["id"]
    for no, value in (("02", "300"), ("03", "600")):
        _ok(
            client.post(
                f"/api/v1/units/{units[no]}/allocation-values",
                json={"allocation_key_id": haus_b, "value": value, "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )

    def statement(year: int, basis: str) -> tuple[str, dict[str, Any]]:
        _book_cost(
            client,
            h,
            w["ledger"],
            w["acc"]["001200"],
            w["acc"]["043000"],
            "1800.00",
            f"{year}-05-02",
        )
        sid = _ok(
            client.post(
                f"{H}/statements", json={"ledger_id": w["ledger"], "year": year}, headers=h
            ),
            201,
        )["id"]
        for label, key, item_basis in (
            ("Versicherung", w["keys"]["MEA"], "Teilungserklärung, Verteilung nach MEA"),
            ("Treppenhaus Haus B", haus_b, basis),
        ):
            _ok(
                client.post(
                    f"{H}/statements/{sid}/costs",
                    json={
                        "label": label,
                        "amount": "900.00",
                        "allocation_key_id": key,
                        "basis": item_basis,
                        "account_id": w["acc"]["043000"],
                    },
                    headers=h,
                ),
                201,
            )
        calc = _ok(client.post(f"{H}/statements/{sid}/calculate", headers=h))
        return str(sid), calc["snapshot"]

    sid, snap = statement(2025, "Filter Haus B")
    split = next(p for p in snap["positions"] if p["label"] == "Treppenhaus Haus B")["split"]
    assert sorted(split.values()) == ["300.00", "600.00"]
    assert units["01"] not in split
    package = _ok(client.get(f"{H}/statements/{sid}/package", headers=h))
    assert [f["code"] for f in package["blocking"]] == ["scope_unfounded"]
    assert "2 von 3" in package["blocking"][0]["detail"]
    assert package["releasable"] is False
    refused = client.post(
        f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
    )
    assert refused.status_code == 409, refused.text
    assert _ok(client.get(f"{H}/statements/{sid}", headers=h))["status"] == "calculated"

    sid2, snap2 = statement(
        2024, "Teilungserklärung vom 01.03.2019, § 6: Kosten Haus B nur Einheiten 02 und 03"
    )
    assert sorted(
        next(p for p in snap2["positions"] if p["label"] == "Treppenhaus Haus B")["split"].values()
    ) == ["300.00", "600.00"]
    package2 = _ok(client.get(f"{H}/statements/{sid2}/package", headers=h))
    assert (package2["blocking"], package2["releasable"]) == ([], True)
    approved = _ok(
        client.post(
            f"{H}/statements/{sid2}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    assert approved["status"] == "internally_approved"


# D20: special levy, two charged instalments, partial refund ---------------------------------


@pytest.mark.annex_d("D20")
def test_al01_levy_two_units_charged_then_partial_refund(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D20 second test, other numbers and both units charged: levy 3.000,00 for the roof in 2
    instalments from May 2026, MEA 700 / 300: unit 01 2 x 1.050,00 (3.000 * 0,7 / 2), unit 02
    2 x 450,00. The May instalments of both units are charged and paid: 1.050 + 450 =
    1.500,00. Roof costs paid 400,00. Report: resolved 3.000,00, charged 1.500,00, received
    1.500,00, open 0,00, used 400,00, earmarked 1.500 - 400 = 1.100,00.
    Amendment to 2.000,00 with refund reason: new shares 1.400,00 / 600,00, differences
    1.400 - 2.100 = -700,00 and 600 - 900 = -300,00, as two draft credits, nothing charged.
    The old version stays superseded with purpose and 3.000,00; the new report keeps charged
    and received 1.500,00 and used 400,00 (not 800,00), earmarked 1.100,00; due months of the
    first version 2026-05-01 and 2026-06-01."""
    client, _ = clients
    h = bearer(login(client, world, "al01admin"))
    w = _hoa_ledger(client, h, "955")
    _, c1 = _owner(client, h, w["property"], "01", "700", w["keys"]["MEA"], {})
    _, c2 = _owner(client, h, w["property"], "02", "300", w["keys"]["MEA"], {})
    ledger, acc = w["ledger"], w["acc"]
    use, revenue = (
        _ok(
            client.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={"number": number, "name": name, "category": category, "type": type_},
                headers=h,
            ),
            201,
        )["id"]
        for number, name, category, type_ in [
            ("049800", "Dachsanierung AL01", "cost", "expense"),
            ("060300", "Sonderumlage AL01", "revenue", "income"),
        ]
    )
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "special_levy", "account_id": revenue},
            headers=h,
        )
    )

    def resolve(levy_id: str, hash_: str, wording: str) -> None:
        res = _ok(
            client.post(
                f"{H}/resolutions",
                json={
                    "legal_entity_id": w["hoa"],
                    "decided_on": "2026-04-15",
                    "subject": "Sonderumlage Dach",
                    "wording": wording,
                    "status": "positive",
                    "subject_type": "special_levy",
                    "subject_id": levy_id,
                    "snapshot_hash": hash_,
                },
                headers=h,
            ),
            201,
        )["id"]
        _ok(
            client.post(
                f"{H}/special-levies/{levy_id}/resolve", json={"resolution_id": res}, headers=h
            )
        )

    lid = _ok(
        client.post(
            f"{H}/special-levies",
            json={
                "ledger_id": ledger,
                "purpose": "Dachsanierung",
                "total": "3000.00",
                "allocation_key_id": w["keys"]["MEA"],
                "first_due": "2026-05-01",
                "instalments": 2,
                "account_id": use,
            },
            headers=h,
        ),
        201,
    )["id"]
    calc = _ok(client.post(f"{H}/special-levies/{lid}/calculate", headers=h))
    by = {u["unit_number"]: u for u in calc["snapshot"]["units"]}
    assert [i["amount"] for i in by["01"]["instalments"]] == ["1050.00"] * 2
    assert [i["amount"] for i in by["02"]["instalments"]] == ["450.00"] * 2
    assert [i["due_month"] for i in by["01"]["instalments"]] == ["2026-05-01", "2026-06-01"]
    resolve(lid, calc["snapshot_hash"], "Sonderumlage Dach 3.000,00 in zwei Raten.")
    assert _ok(client.post(f"{H}/special-levies/{lid}/apply", headers=h))["payments_created"] == 4

    for c in (c1, c2):
        run = _ok(
            client.post(
                f"{A}/receivable-runs",
                json={"period_month": "2026-05-01", "scope": "contract", "scope_id": c["id"]},
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _open_items(client, h, ledger, "2026-05-31")
    assert sorted(i["remaining"] for i in items) == ["1050.00", "450.00"]
    for item in items:
        amount = item["remaining"]
        _post(
            client,
            h,
            ledger,
            "debtor_payment",
            "2026-05-10",
            [
                {"account_id": acc["001200"], "debit": amount},
                {"account_id": item["account_id"], "credit": amount},
            ],
            [{"open_item_id": item["id"], "amount": amount}],
        )
    _post(
        client,
        h,
        ledger,
        "custom",
        "2026-05-20",
        [{"account_id": use, "debit": "400.00"}, {"account_id": acc["001200"], "credit": "400.00"}],
    )
    report = _ok(client.get(f"{H}/special-levies/{lid}/report", headers=h))
    assert (report["resolved"], report["charged"], report["received"], report["open"]) == (
        "3000.00",
        "1500.00",
        "1500.00",
        "0.00",
    )
    assert (report["used"], report["earmarked_remaining"]) == ("400.00", "1100.00")

    reason = "Dachsanierung günstiger vergeben, Teilerstattung an die Eigentümer"
    new = _ok(
        client.post(
            f"{H}/special-levies/{lid}/amend",
            json={"total": "2000.00", "difference_due": "2026-09-01", "reason": reason},
            headers=h,
        ),
        201,
    )
    assert (new["purpose"], new["change_reason"], new["version"], new["supersedes_id"]) == (
        "Dachsanierung",
        reason,
        2,
        lid,
    )
    calc2 = _ok(client.post(f"{H}/special-levies/{new['id']}/calculate", headers=h))
    assert {u["unit_number"]: u["difference"] for u in calc2["snapshot"]["units"]} == {
        "01": "-700.00",
        "02": "-300.00",
    }
    resolve(new["id"], calc2["snapshot_hash"], "Sonderumlage Dach wird auf 2.000,00 gesenkt.")
    applied = _ok(client.post(f"{H}/special-levies/{new['id']}/apply", headers=h))
    assert (applied["charges_created"], applied["credit_drafts"]) == (0, 2)
    credits = [
        e
        for e in _ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h))
        if e["text"].startswith("Gutschrift Sonderumlage V2")
    ]
    assert len(credits) == 2
    assert {e["status"] for e in credits} == {"draft"}
    old = _ok(client.get(f"{H}/special-levies/{lid}", headers=h))
    assert (old["status"], old["purpose"], old["total"]) == (
        "superseded",
        "Dachsanierung",
        "3000.00",
    )
    rep2 = _ok(client.get(f"{H}/special-levies/{new['id']}/report", headers=h))
    assert (rep2["resolved"], rep2["charged"], rep2["received"], rep2["open"]) == (
        "2000.00",
        "1500.00",
        "1500.00",
        "0.00",
    )
    assert (rep2["used"], rep2["earmarked_remaining"]) == ("400.00", "1100.00")
    per_unit = {
        u["unit_number"]: (u["resolved"], u["charged"], u["received"]) for u in rep2["units"]
    }
    assert per_unit == {
        "01": ("1400.00", "1050.00", "1050.00"),
        "02": ("600.00", "450.00", "450.00"),
    }
