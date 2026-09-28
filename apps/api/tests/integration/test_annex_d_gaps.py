"""Annex D cases whose money flow had no test carrying the case id (traceability table in
`docs/acceptance/D-cases.md`, column "Automatisierter Test"): D04 and D05 on the bank import
path including the posting, D07 on the bank import path, D24 structure and lock only.

Expected values are the ones written in annex D (rule 0.1.8, D.3); every figure is recomputed
by hand in the docstrings. Where annex D gives no figure (D24), the model input is chosen for
this test only and the test asserts nothing but arithmetic identities, the separate display
and the locks. The productive gates stay closed: every client here uses the persistent
resolver, so G1 and G3 are closed and no ledger becomes leading."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m17_operating_costs import _rental_world, _statement

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
S = "/api/v1/statements"

# Synthetic IBANs with a valid check digit, as in the other banking tests (no real data).
D04_BANK_A = "DE02120300000000202051"
D04_BANK_B = "DE89370400440532013000"
D04_PAIR_A = "DE16100100101111111111"
D04_PAIR_B = "DE66100100102222222222"
D05_BANK = "DE02500105170137075030"
D05_PAYER = "DE27100777770209299700"
D07_BANK = "DE91100000000123456789"
D07_PAYER = "DE75512108001245126199"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"annexd-gaps-{RUN}", name=f"Anhang D Lücken {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("gapadmin", "tenant_admin"), ("gapacc", "accountant_no_banking")]:
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
    """Client with the persistent release gate resolver: G1 to G5 closed."""
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _line(account: str, debit: str = "0", credit: str = "0") -> dict[str, str]:
    return {"account_id": account, "debit": debit, "credit": credit}


def _post_entry(c: TestClient, h: dict[str, str], ledger: str, body: dict[str, Any]) -> Any:
    draft = _ok(c.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    return _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))


def _hoa(
    c: TestClient, h: dict[str, str], number: str, banks: list[tuple[str, str, str]]
) -> dict[str, Any]:
    """WEG with one owner, a ledger from the default template and the given bank accounts,
    each linked to its own ledger account (iban, account kind, ledger account number)."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Anhang D {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(c, h, prop["id"], "01")
    owner, _ = _party(c, h, f"Eig{number}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": owner,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    bank_ids: dict[str, str] = {}
    ledger_banks: dict[str, str] = {}
    for iban, kind, account_number in banks:
        bank_ids[iban] = _ok(
            c.post(
                f"/api/v1/properties/{prop['id']}/bank-accounts",
                json={
                    "legal_entity_id": hoa,
                    "kind": kind,
                    "iban": iban,
                    "holder": f"GdWE Anhang D {number}",
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )["id"]
        ledger_banks[iban] = _ok(
            c.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={
                    "number": account_number,
                    "name": f"Bank {account_number}",
                    "category": "bank",
                    "type": "asset",
                    "property_bank_account_id": bank_ids[iban],
                },
                headers=h,
            ),
            201,
        )["id"]
    accounts = {a["number"]: a for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    debtor = next(a["id"] for a in accounts.values() if a["category"] == "debtor")
    return {
        "property": prop["id"],
        "hoa": hoa,
        "contract": contract,
        "ledger": ledger,
        "accounts": accounts,
        "debtor": debtor,
        "bank_ids": bank_ids,
        "ledger_banks": ledger_banks,
    }


def _trial_balance(c: TestClient, h: dict[str, str], ledger: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-12-31"}, headers=h)
    )


def _txs(c: TestClient, h: dict[str, str], bank_account_id: str) -> list[dict[str, Any]]:
    return _ok(  # type: ignore[no-any-return]
        c.get(f"{B}/transactions", params={"bank_account_id": bank_account_id}, headers=h)
    )


def _entries(c: TestClient, h: dict[str, str], ledger: str) -> list[dict[str, Any]]:
    return _ok(c.get(f"{A}/ledgers/{ledger}/entries", headers=h))  # type: ignore[no-any-return]


def _assert_g1_closed(c: TestClient, h: dict[str, str], ledger: str) -> None:
    """G1 stays closed: the ledger cannot become the leading money process (18.0, ADR 0003)."""
    gate = c.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h)
    assert gate.status_code == 403, gate.text
    assert gate.json()["code"] == "MHVP-GATE-0001"
    assert _ok(c.get(f"{A}/ledgers/{ledger}", headers=h))["leading_system"] == "immoware24"


# --- D04 interner Banktransfer ------------------------------------------------------------


def _d04_world(
    c: TestClient,
    h: dict[str, str],
    acc_user: dict[str, str],
    number: str,
    iban_a: str,
    iban_b: str,
) -> dict[str, Any]:
    """Model WEG of D04: bank A 10.000,00 and bank B 20.000,00 (B is the reserve account, to
    check that the transfer is no reserve contribution). Opening balances approved by a
    second person; both bank statements of January imported."""
    w = _hoa(c, h, number, [(iban_a, "hoa", "001210"), (iban_b, "reserve", "001211")])
    bank_a, bank_b = w["ledger_banks"][iban_a], w["ledger_banks"][iban_b]
    opening = _ok(
        c.post(
            f"{A}/ledgers/{w['ledger']}/entries",
            json={
                "kind": "opening_balance",
                "booking_date": "2026-01-01",
                "text": "Anfangsbestand D04",
                "lines": [
                    _line(bank_a, "10000.00"),
                    _line(bank_b, "20000.00"),
                    _line(w["accounts"]["009000"]["id"], "0", "30000.00"),
                ],
            },
            headers=h,
        ),
        201,
    )
    _ok(c.post(f"{A}/ledgers/{w['ledger']}/entries/{opening['id']}/approve", headers=acc_user))
    _ok(c.post(f"{A}/ledgers/{w['ledger']}/entries/{opening['id']}/post", headers=h))
    # Bank A: 10.000,00 - 1.000,00 = 9.000,00. Bank B: 20.000,00 + 1.000,00 = 21.000,00.
    file_a = _camt(
        f"{number}-A",
        iban_a,
        "10000.00",
        "9000.00",
        [_ntry(f"{number}-A1", "1000.00", "DBIT", "2026-01-10", iban_b, "Umbuchung")],
    )
    file_b = _camt(
        f"{number}-B",
        iban_b,
        "20000.00",
        "21000.00",
        [_ntry(f"{number}-B1", "1000.00", "CRDT", "2026-01-11", iban_a, "Umbuchung")],
    )
    run_a = _ok(
        c.post(f"{B}/imports", json={"document_id": _upload(c, h, "d04a.xml", file_a)}, headers=h),
        201,
    )
    run_b = _ok(
        c.post(f"{B}/imports", json={"document_id": _upload(c, h, "d04b.xml", file_b)}, headers=h),
        201,
    )
    assert (run_a["counts"]["new"], run_b["counts"]["new"]) == (1, 1)
    assert run_b["counts"]["transfers"] == 1  # both statements imported, recognised as a pair
    (out,) = _txs(c, h, w["bank_ids"][iban_a])
    (into,) = _txs(c, h, w["bank_ids"][iban_b])
    assert (out["transfer_pair_id"], into["transfer_pair_id"]) == (into["id"], out["id"])
    return w | {
        "out": out,
        "into": into,
        "bank_a": bank_a,
        "bank_b": bank_b,
        "ibans": (iban_a, iban_b),
    }


def _assert_d04_balances(c: TestClient, h: dict[str, str], w: dict[str, Any]) -> None:
    """A 9.000,00, B 21.000,00, total still 30.000,00; no expense, no income, no reserve
    contribution (no revenue, cost or reserve account moved, no open item created)."""
    tb = _trial_balance(c, h, w["ledger"])
    by = {a["number"]: Decimal(a["balance"]) for a in tb["accounts"]}
    assert tb["balanced"] is True
    assert by["001210"] == Decimal("9000.00")
    assert by["001211"] == Decimal("21000.00")
    assert by["001210"] + by["001211"] == Decimal("30000.00")
    moved = {a["category"] for a in tb["accounts"] if Decimal(a["balance"]) != 0}
    assert not moved & {"cost", "revenue", "reserve"}
    assert (
        _ok(
            c.get(
                f"{A}/ledgers/{w['ledger']}/open-items",
                params={"as_of": "2026-12-31"},
                headers=h,
            )
        )
        == []
    )
    for iban in w["ibans"]:
        rec = _ok(c.get(f"{B}/accounts/{w['bank_ids'][iban]}/reconciliation", headers=h))
        assert [Decimal(r["statement_difference"]) for r in rec] == [Decimal("0.00")]
        assert [Decimal(r["ledger_difference"]) for r in rec] == [Decimal("0.00")]


def test_d04_transfer_between_own_accounts_is_booked_once_and_is_no_income(
    client: TestClient, world: World
) -> None:
    """D04: one posting of the pair against the partner bank account gives A 9.000,00 and
    B 21.000,00 (10.000 - 1.000; 20.000 + 1.000), total 30.000,00, no expense or income, no
    reserve contribution; bank and ledger agree on both accounts. G1 stays closed."""
    h = bearer(login(client, world, "gapadmin"))
    acc_user = bearer(login(client, world, "gapacc"))
    w = _d04_world(client, h, acc_user, "404", D04_BANK_A, D04_BANK_B)
    # A transfer is never booked against a personal or revenue account (no counter account).
    refused = client.post(f"{B}/transactions/{w['out']['id']}/book", json={}, headers=h)
    assert refused.status_code == 422, refused.text
    _ok(
        client.post(
            f"{B}/transactions/{w['out']['id']}/book",
            json={"counter_account_id": w["bank_b"]},
            headers=h,
        ),
        201,
    )
    kinds = [e["kind"] for e in _entries(client, h, w["ledger"]) if e["status"] == "posted"]
    assert sorted(kinds) == ["bank_transfer", "opening_balance"]
    _assert_d04_balances(client, h, w)
    _assert_g1_closed(client, h, w["ledger"])


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Defekt D04 (Anhang D: keine zweite Wirkung des Transfers): nach der Buchung der "
        "Abgangsseite lässt POST /banking/transactions/{id}/book die Partnerseite desselben "
        "Transferpaars erneut gegen Bank A buchen; mhvp.banking.matching.book_payment prüft "
        "nicht, ob der Partner über transfer_pair_id schon gebucht ist. Ergebnis A 8.000,00, "
        "B 22.000,00 statt 9.000,00 und 21.000,00."
    ),
)
def test_d04_second_half_of_the_transfer_pair_has_no_second_effect(
    client: TestClient, world: World
) -> None:
    """D04 forbidden error: booking the incoming half after the outgoing half must not move
    the money a second time; A stays 9.000,00, B 21.000,00."""
    h = bearer(login(client, world, "gapadmin"))
    acc_user = bearer(login(client, world, "gapacc"))
    w = _d04_world(client, h, acc_user, "414", D04_PAIR_A, D04_PAIR_B)
    _ok(
        client.post(
            f"{B}/transactions/{w['out']['id']}/book",
            json={"counter_account_id": w["bank_b"]},
            headers=h,
        ),
        201,
    )
    second = client.post(
        f"{B}/transactions/{w['into']['id']}/book",
        json={"counter_account_id": w["bank_a"]},
        headers=h,
    )
    assert second.status_code in (409, 422), second.text
    _assert_d04_balances(client, h, w)


# --- D05 echte Gleichzahlungen ------------------------------------------------------------


def test_d05_two_equal_real_payments_stay_two_after_reimport_and_booking(
    client: TestClient, world: World
) -> None:
    """D05: two payments of 400,00 each, same payer, day and purpose, told apart by their
    bank references. First import: two economic payments, 800,00. Both are booked. The same
    original records imported again: still 800,00 (neither 400,00 nor 1.600,00) on the bank
    transactions and on the bank ledger account; no further posting."""
    h = bearer(login(client, world, "gapadmin"))
    w = _hoa(client, h, "405", [(D05_BANK, "hoa", "001210")])
    statement = _camt(
        "D05",
        D05_BANK,
        "0.00",
        "800.00",
        [
            _ntry("D05-1", "400.00", "CRDT", "2026-01-05", D05_PAYER, "Hausgeld Januar"),
            _ntry("D05-2", "400.00", "CRDT", "2026-01-05", D05_PAYER, "Hausgeld Januar"),
        ],
    )
    first = _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "d05.xml", statement)},
            headers=h,
        ),
        201,
    )
    assert first["counts"]["new"] == 2
    txs = _txs(client, h, w["bank_ids"][D05_BANK])
    assert sorted(Decimal(t["amount"]) for t in txs) == [Decimal("400.00"), Decimal("400.00")]
    assert sum(Decimal(t["amount"]) for t in txs) == Decimal("800.00")
    # Book both against the owner's debtor account (payment on account, no open item here:
    # the credit stays on the personal account, never income).
    for t in txs:
        assert t["status"] == "new", t
        _ok(
            client.post(
                f"{B}/transactions/{t['id']}/book",
                json={"counter_account_id": w["debtor"]},
                headers=h,
            ),
            201,
        )
    again = _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "d05-wieder.xml", statement)},
            headers=h,
        ),
        201,
    )
    assert (again["counts"]["new"], again["counts"]["duplicates"]) == (0, 2)
    after = _txs(client, h, w["bank_ids"][D05_BANK])
    assert len(after) == 2
    assert sum(Decimal(t["amount"]) for t in after) == Decimal("800.00")
    assert {t["status"] for t in after} == {"booked"}
    tb = {
        a["number"]: Decimal(a["balance"])
        for a in _trial_balance(client, h, w["ledger"])["accounts"]
    }
    assert tb["001210"] == Decimal("800.00")
    payments = [e for e in _entries(client, h, w["ledger"]) if e["status"] == "posted"]
    assert len(payments) == 2
    _assert_g1_closed(client, h, w["ledger"])


# --- D07 Teil-/Überzahlung über den Bankimport --------------------------------------------


def test_d07_partial_then_overpayment_via_bank_import_leaves_separate_credit(
    client: TestClient, world: World
) -> None:
    """D07 on the bank path: due receivable 1.000,00; first payment 600,00 settled -> rest
    400,00; second actual payment 450,00 settles 400,00 -> receivable settled, 50,00
    (450 - 400) stay as separate credit on the debtor account. Revenue stays 1.000,00
    (credit is no additional income); no refund or other entry is created automatically."""
    h = bearer(login(client, world, "gapadmin"))
    w = _hoa(client, h, "407", [(D07_BANK, "hoa", "001210")])
    ledger, debtor = w["ledger"], w["debtor"]
    revenue = w["accounts"]["060100"]["id"]
    _post_entry(
        client,
        h,
        ledger,
        {
            "kind": "receivable",
            "booking_date": "2026-01-01",
            "due_date": "2026-01-03",
            "text": "Forderung D07",
            "contract_id": w["contract"]["id"],
            "lines": [_line(debtor, "1000.00"), _line(revenue, "0", "1000.00")],
        },
    )
    (item,) = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert Decimal(item["remaining"]) == Decimal("1000.00")
    n = w["contract"]["number"]
    statement = _camt(
        "D07",
        D07_BANK,
        "0.00",
        "1050.00",
        [
            _ntry("D07-1", "600.00", "CRDT", "2026-01-10", D07_PAYER, f"Forderung {n}"),
            _ntry("D07-2", "450.00", "CRDT", "2026-01-20", D07_PAYER, f"Forderung {n}"),
        ],
    )
    _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "d07.xml", statement)},
            headers=h,
        ),
        201,
    )
    txs = {t["bank_reference"]: t for t in _txs(client, h, w["bank_ids"][D07_BANK])}
    _ok(
        client.post(
            f"{B}/transactions/{txs['D07-1']['id']}/book",
            json={"settlements": [{"open_item_id": item["id"], "amount": "600.00"}]},
            headers=h,
        ),
        201,
    )
    (rest,) = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-15"}, headers=h)
    )
    assert Decimal(rest["remaining"]) == Decimal("400.00")
    # The item cannot be settled beyond its rest.
    over = client.post(
        f"{B}/transactions/{txs['D07-2']['id']}/book",
        json={"settlements": [{"open_item_id": item["id"], "amount": "450.00"}]},
        headers=h,
    )
    assert over.status_code == 422, over.text
    _ok(
        client.post(
            f"{B}/transactions/{txs['D07-2']['id']}/book",
            json={"settlements": [{"open_item_id": item["id"], "amount": "400.00"}]},
            headers=h,
        ),
        201,
    )
    assert (
        _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h
            )
        )
        == []
    )
    tb = _trial_balance(client, h, ledger)
    by = {a["number"]: a for a in tb["accounts"]}
    debtor_number = next(num for num, a in w["accounts"].items() if a["id"] == debtor)
    assert tb["balanced"] is True
    assert Decimal(by[debtor_number]["balance"]) == Decimal("-50.00")  # 1.000 - 600 - 450
    assert Decimal(by["060100"]["balance"]) == Decimal("-1000.00")  # no additional income
    assert Decimal(by["001210"]["balance"]) == Decimal("1050.00")
    kinds = sorted(e["kind"] for e in _entries(client, h, ledger) if e["status"] == "posted")
    assert kinds == ["debtor_payment", "debtor_payment", "receivable"]  # no automatic refund
    _assert_g1_closed(client, h, ledger)


# --- D24 offene Mietvorauszahlungen (nur Struktur und Sperre) ------------------------------


def _d24_world(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    """Rental unit with an operating cost advance, two monthly advances posted (January and
    February 2025), only January paid, one cost position. Figures are model input of this
    test (annex D names none): advance 100,00, cost position 120,00."""
    w = _rental_world(client, h, number)
    ledger, contract = w["ledger"], w["contract"]
    _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/payments",
            json={
                "payment_type_code": "operating_cost_advance",
                "net": "100.00",
                "gross": "100.00",
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": "2024-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    revenue = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "061000",
                "name": "BK-Vorauszahlungen",
                "category": "revenue",
                "type": "income",
            },
            headers=h,
        ),
        201,
    )["id"]
    bank = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={"number": "001210", "name": "Mietkonto", "category": "bank", "type": "asset"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "operating_cost_advance", "account_id": revenue},
            headers=h,
        )
    )
    for month in ("2025-01-01", "2025-02-01"):
        run = _ok(
            client.post(
                f"{A}/receivable-runs",
                json={"period_month": month, "scope": "contract", "scope_id": contract["id"]},
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-02-28"}, headers=h)
    )
    assert sorted(Decimal(i["remaining"]) for i in items) == [Decimal("100.00")] * 2
    january = min(items, key=lambda i: i["due_date"])
    _post_entry(
        client,
        h,
        ledger,
        {
            "kind": "debtor_payment",
            "booking_date": "2025-01-05",
            "text": "Vorauszahlung Januar",
            "lines": [_line(bank, "100.00"), _line(january["account_id"], "0", "100.00")],
            "settlements": [{"open_item_id": january["id"], "amount": "100.00"}],
        },
    )
    st = _statement(client, h, ledger)
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Gartenpflege",
                "amount": "120.00",
                "allocation_key_id": w["keys"]["WFL"],
                "basis": "§ 4 Mietvertrag, Nr. 10 BetrKV",
            },
            headers=h,
        ),
        201,
    )
    return w | {"statement": st}


def _open_remaining(client: TestClient, h: dict[str, str], ledger: str) -> Decimal:
    rows = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h)
    )
    return sum((Decimal(i["remaining"]) for i in rows), Decimal("0.00"))


def test_d24_open_advances_shown_apart_calculation_creates_no_claim_and_issue_is_locked(
    client: TestClient, world: World
) -> None:
    """D24, structure and lock only (annex D gives no figure and the advance rule M17-03 is
    not confirmed): due 200,00, paid 100,00 and open 100,00 (200 - 100) are shown apart; the
    calculation posts nothing and creates no open item (open items stay 100,00); issuing is
    refused while G3 is closed, so no statement claim arises next to the open advance."""
    h = bearer(login(client, world, "gapadmin"))
    acc_user = bearer(login(client, world, "gapacc"))
    w = _d24_world(client, h, "424")
    ledger, st = w["ledger"], w["statement"]
    entries_before = len(_entries(client, h, ledger))
    result = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    (row,) = result["snapshot"]["results"]
    assert (row["advances_due"], row["advances_paid"], row["advances_open"]) == (
        "200.00",
        "100.00",
        "100.00",
    )
    assert Decimal(row["advances_open"]) == Decimal(row["advances_due"]) - Decimal(
        row["advances_paid"]
    )
    assert result["status"] == "calculated"
    assert len(_entries(client, h, ledger)) == entries_before  # calculation posts nothing
    assert _open_remaining(client, h, ledger) == Decimal("100.00")
    _ok(
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=acc_user
        )
    )
    issue = client.post(
        f"{S}/{st['id']}/transition",
        json={"target": "issued", "delivered_at": "2026-01-15"},
        headers=acc_user,
    )
    assert issue.status_code == 403, issue.text
    assert issue.json()["code"] == "MHVP-GATE-0001"
    assert _ok(client.get(f"{S}/{st['id']}", headers=h))["status"] == "internally_approved"
    assert len(_entries(client, h, ledger)) == entries_before


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Defekt D24 (Anhang D: kein doppelter wirtschaftlicher Anspruch), Behandlung hängt an "
        "M17-03 (Betreiber mit Rechtsberatung, G3): der Abrechnungssaldo wird gegen die "
        "gezahlten Vorauszahlungen gerechnet (mhvp.billing.services, balance = costs - paid), "
        "der offene Vorauszahlungsposten bleibt daneben unverändert offen. Ausgewiesene "
        "Ansprüche 20,00 + 100,00 = 120,00 statt 20,00."
    ),
)
def test_d24_statement_balance_and_open_advance_items_claim_the_open_amount_once(
    client: TestClient, world: World
) -> None:
    """D24 forbidden error (double economic claim), arithmetic only: costs 120,00 minus paid
    advances 100,00 = 20,00 is all the tenant owes for the period, whatever advance rule is
    released. The statement balance plus the advance items still open must not exceed it."""
    h = bearer(login(client, world, "gapadmin"))
    w = _d24_world(client, h, "434")
    result = _ok(client.post(f"{S}/{w['statement']['id']}/calculate", headers=h))
    (row,) = result["snapshot"]["results"]
    owed = Decimal(row["costs"]) - Decimal(row["advances_paid"])
    assert owed == Decimal("20.00")
    visible = max(Decimal(row["balance"]), Decimal("0.00")) + _open_remaining(
        client, h, w["ledger"]
    )
    assert visible == owed
