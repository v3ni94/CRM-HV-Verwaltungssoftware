"""Annex D acceptance cases on money that were partial or untested in
`docs/acceptance/PROTOKOLL-2026-09-26.md`: D06 (bank balance unchanged at export and
submission, exact 1.190,00 without discount), D11 (year completeness after a mid year
takeover) and D56 (deposit funds apart from free property funds on the posting and payment
side). Expected values are computed by hand in each docstring (rule 0.1.8). G1 and G2 are
opened only through the test resolver of the second client; the productive flags stay off."""

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
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _upload
from tests.integration.test_m15_payments import _debit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
DD = "/api/v1/accounting/direct-debits"
OWN = "DE02120300000000202051"
RENT_IBAN = "DE75512108001245126199"
DEPOSIT_IBAN = "DE89370400440532013000"
PROVIDER = "DE91100000000123456789"


class OpenG1G2:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G2)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"annexd-money-{RUN}", name=f"Anhang D Geld {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("admadmin", "tenant_admin"),
            ("admacc", "accountant_banking"),
            ("admapprover", "tenant_admin"),
        ]:
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
            TestClient(create_app(settings, release_gate_resolver=OpenG1G2())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _accounts(client: TestClient, h: dict[str, str], ledger: str) -> dict[str, str]:
    return {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }


def _trial_balance(
    client: TestClient, h: dict[str, str], ledger: str, as_of: str, start: str | None = None
) -> dict[str, Decimal]:
    params = {"as_of": as_of} | ({"start": start} if start else {})
    return {
        a["number"]: Decimal(a["balance"])
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/trial-balance", params=params, headers=h))[
            "accounts"
        ]
    }


def _remaining(client: TestClient, h: dict[str, str], ledger: str) -> list[Decimal]:
    return sorted(
        Decimal(i["remaining"])
        for i in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h
            )
        )
    )


def _provider(client: TestClient, h: dict[str, str], approver: dict[str, str], name: str) -> str:
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"{name} {RUN} GmbH",
                "bank_accounts": [{"iban": PROVIDER, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, approver, provider)
    return str(provider)


def _invoice(
    client: TestClient,
    h: dict[str, str],
    acc_user: dict[str, str],
    ledger: str,
    provider: str,
    cost_account: str,
    number: str,
    gross: str,
) -> str:
    inv = _ok(
        client.post(
            f"{A}/invoices",
            json={
                "ledger_id": ledger,
                "provider_contact_id": provider,
                "number": number,
                "invoice_date": "2026-02-01",
                "due_date": "2026-02-20",
                "service_from": "2026-01-01",
                "net": gross,
                "vat": "0.00",
                "gross": gross,
                "payee_iban": PROVIDER,
                "lines": [{"account_id": cost_account, "net": gross}],
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
    return str(inv)


def _bank_account(
    client: TestClient, h: dict[str, str], prop: str, entity: str, kind: str, iban: str, holder: str
) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        client.post(
            f"/api/v1/properties/{prop}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": kind,
                "iban": iban,
                "holder": holder,
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )


def _ledger_account(
    client: TestClient, h: dict[str, str], ledger: str, number: str, name: str, **extra: Any
) -> str:
    return str(
        _ok(
            client.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={"number": number, "name": name, "category": "bank", "type": "asset", **extra},
                headers=h,
            ),
            201,
        )["id"]
    )


def _entry(
    client: TestClient,
    h: dict[str, str],
    ledger: str,
    day: str,
    text: str,
    lines: list[dict[str, str]],
    **extra: Any,
) -> dict[str, Any]:
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={"kind": "custom", "booking_date": day, "text": text, "lines": lines, **extra},
            headers=h,
        ),
        201,
    )
    return _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))  # type: ignore[no-any-return]


def test_d06_export_and_submission_leave_bank_and_payable_untouched(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D06 as in annex D, without discount: released invoice 1.190,00; payment file exported,
    submitted, later executed; no other payment.
    Expected: bank account 001210 balance 0,00 and payable open item 1.190,00 after export
    and after submission; executed without proof is refused; executed with the bank
    transaction settles once: payable [], bank -1.190,00, creditor 1.190,00 - 1.190,00 = 0;
    a second executed feedback returns the same journal entry and the bank stays -1.190,00."""
    client, gated = clients
    h = bearer(login(client, world, "admadmin"))
    acc_user = bearer(login(client, world, "admacc"))
    approver = bearer(login(client, world, "admapprover"))
    gh = bearer(login(gated, world, "admacc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "906", "name": "Zahlhaus D06", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank = _bank_account(client, h, prop["id"], hoa, "hoa", OWN, "GdWE Zahlhaus D06")["id"]
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ledger_account(client, h, ledger, "001210", "Bank", property_bank_account_id=bank)
    acc = _accounts(client, h, ledger)
    provider = _provider(client, h, approver, "Dienst D06")
    inv = _invoice(client, h, acc_user, ledger, provider, acc["040300"], "D06-1", "1190.00")
    assert _remaining(client, h, ledger) == [Decimal("1190.00")]

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
    assert (order["amount"], order["discount"]) == ("1190.00", "0.00")
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=h))
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=acc_user))
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))

    def bank_balance() -> Decimal:
        return _trial_balance(client, h, ledger, "2026-12-31").get("001210", Decimal("0.00"))

    batch = _ok(
        gated.post(f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=gh), 201
    )
    assert '<InstdAmt Ccy="EUR">1190.00</InstdAmt>' in batch["xml"]
    assert _remaining(client, h, ledger) == [Decimal("1190.00")]  # export pays nothing
    assert bank_balance() == Decimal("0.00")
    _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/bank-status",
            json={"status": "submitted"},
            headers=gh,
        )
    )
    assert _remaining(client, h, ledger) == [Decimal("1190.00")]  # submission pays nothing
    assert bank_balance() == Decimal("0.00")
    no_proof = gated.post(
        f"{B}/payment-batches/{batch['id']}/bank-status", json={"status": "executed"}, headers=gh
    )
    assert no_proof.status_code == 422
    assert bank_balance() == Decimal("0.00")

    stmt = _camt(
        "D06-1", OWN, "5000.00", "3810.00", [_debit("D06-D1", "1190.00", order["end_to_end_id"])]
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "d06.xml", stmt)}, headers=h
        ),
        201,
    )
    tx = next(
        t
        for t in _ok(client.get(f"{B}/transactions", headers=h))
        if t["bank_reference"] == "D06-D1"
    )
    done = _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/bank-status",
            json={"status": "executed", "bank_transaction_id": tx["id"]},
            headers=gh,
        )
    )
    assert done[0]["status"] == "executed"
    assert _remaining(client, h, ledger) == []
    assert bank_balance() == Decimal("-1190.00")
    again = _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/bank-status",
            json={"status": "executed", "bank_transaction_id": tx["id"]},
            headers=gh,
        )
    )
    assert again[0]["journal_entry_id"] == done[0]["journal_entry_id"]
    assert bank_balance() == Decimal("-1190.00")  # no second settlement
    assert _remaining(client, h, ledger) == []
    tb = _trial_balance(client, h, ledger, "2026-12-31")
    assert tb["040300"] == Decimal("1190.00")
    assert tb.get("027000", Decimal("0.00")) == Decimal("0.00")  # no discount line
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True


def test_d11_mid_year_takeover_year_costs_complete_with_documents(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D11: takeover during 2025. Opening balance imported (bank 5.000,00 against 009000,
    approved by a second person, 01.07.2025). Documented expenses 400,00 before the takeover
    (15.03.2025) and 600,00 after (15.09.2025), both on the cost account 043000.
    Expected: year costs 043000 = 400,00 + 600,00 = 1.000,00 (not 6.000,00 and not 600,00);
    the opening balance is on 009000 (-5.000,00) and the bank (5.000,00 - 400,00 - 600,00 =
    4.000,00), never on a cost account; both cost entries carry their document; the account
    sheet of 043000 for the year lists exactly the two documented entries; consistency
    checks pass."""
    client, _ = clients
    h = bearer(login(client, world, "admadmin"))
    approver = bearer(login(client, world, "admapprover"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "911", "name": "Übernahme D11", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = _accounts(client, h, ledger)

    opening = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "opening_balance",
                "booking_date": "2025-07-01",
                "text": "Anfangsbestand Übernahme 01.07.2025",
                "lines": [
                    {"account_id": acc["001200"], "debit": "5000.00"},
                    {"account_id": acc["009000"], "credit": "5000.00"},
                ],
            },
            headers=h,
        ),
        201,
    )
    assert (
        client.post(f"{A}/ledgers/{ledger}/entries/{opening['id']}/post", headers=h).status_code
        == 403
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{opening['id']}/approve", headers=approver))
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{opening['id']}/post", headers=h))

    docs = {
        "vor": _upload(client, h, "beleg-vor-uebernahme.xml", b"<beleg>400,00 EUR</beleg>"),
        "nach": _upload(client, h, "beleg-nach-uebernahme.xml", b"<beleg>600,00 EUR</beleg>"),
    }
    before = _entry(
        client,
        h,
        ledger,
        "2025-03-15",
        "Allgemeinstrom Q1 (vor Übernahme, aus Vorverwaltung belegt)",
        [
            {"account_id": acc["043000"], "debit": "400.00"},
            {"account_id": acc["001200"], "credit": "400.00"},
        ],
        document_id=docs["vor"],
    )
    after = _entry(
        client,
        h,
        ledger,
        "2025-09-15",
        "Allgemeinstrom Q3",
        [
            {"account_id": acc["043000"], "debit": "600.00"},
            {"account_id": acc["001200"], "credit": "600.00"},
        ],
        document_id=docs["nach"],
    )
    assert (before["document_id"], after["document_id"]) == (docs["vor"], docs["nach"])
    assert (before["kind"], after["kind"]) == ("custom", "custom")

    tb = _trial_balance(client, h, ledger, "2025-12-31", start="2025-01-01")
    assert tb["043000"] == Decimal("1000.00")
    assert tb["001200"] == Decimal("4000.00")
    assert tb["009000"] == Decimal("-5000.00")
    assert sum((v for k, v in tb.items() if k.startswith("04")), Decimal("0.00")) == Decimal(
        "1000.00"
    )
    sheet = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/accounts/{acc['043000']}/sheet",
            params={"start": "2025-01-01", "end": "2025-12-31"},
            headers=h,
        )
    )
    rows = [(r["booking_date"], r["kind"], r["entry_id"]) for r in sheet["movements"]]
    assert rows == [("2025-03-15", "custom", before["id"]), ("2025-09-15", "custom", after["id"])]
    assert Decimal(sheet["closing_balance"]) == Decimal("1000.00")
    for entry_id in (before["id"], after["id"]):
        assert _ok(client.get(f"{A}/ledgers/{ledger}/entries/{entry_id}", headers=h))["document_id"]
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True


def test_d56_deposit_funds_are_neither_free_liquidity_nor_a_payment_source(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D56: rental property, owner as legal entity; rent account with 2.000,00 and a
    segregated deposit account with a tenant deposit of 1.500,00 (liability 070000).
    Expected: liquidity free_funds 2.000,00, segregated_deposits 1.500,00 (not 3.500,00);
    an invoice of 500,00 cannot be paid from the deposit account (422), only from the rent
    account (order 500,00); a direct debit run may not collect onto the deposit account
    (422). Deposit interest and its allocation stay an operator decision (B15) and are not
    asserted here."""
    client, gated = clients
    h = bearer(login(client, world, "admadmin"))
    acc_user = bearer(login(client, world, "admacc"))
    approver = bearer(login(client, world, "admapprover"))
    gh = bearer(login(gated, world, "admacc"))
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "956", "name": "Miethaus D56", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    assert rental["legal_entities"] == []
    owner = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Bestand D56 {RUN} GmbH"},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": owner["id"]}]}, headers=h),
        201,
    )
    entity = _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": party["id"], "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    rent_bank = _bank_account(client, h, rental["id"], entity, "rent", RENT_IBAN, "Mietkonto")
    deposit_bank = _bank_account(
        client, h, rental["id"], entity, "deposit", DEPOSIT_IBAN, "Kautionskonto"
    )
    assert (rent_bank["segregated"], deposit_bank["segregated"]) == (False, True)
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    rent_acc = _ledger_account(
        client, h, ledger, "001210", "Mietkonto", property_bank_account_id=rent_bank["id"]
    )
    deposit_acc = _ledger_account(
        client, h, ledger, "001220", "Kautionskonto", property_bank_account_id=deposit_bank["id"]
    )
    liability = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "070000",
                "name": "Kautionsverbindlichkeiten",
                "category": "technical",
                "type": "liability",
            },
            headers=h,
        ),
        201,
    )["id"]
    acc = _accounts(client, h, ledger)
    revenue = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "080100",
                "name": "Mieterträge",
                "category": "revenue",
                "type": "income",
            },
            headers=h,
        ),
        201,
    )["id"]
    _entry(
        client,
        h,
        ledger,
        "2026-01-05",
        "Mieteingang",
        [
            {"account_id": rent_acc, "debit": "2000.00"},
            {"account_id": revenue, "credit": "2000.00"},
        ],
    )
    _entry(
        client,
        h,
        ledger,
        "2026-01-06",
        "Kaution Mieter WE 01",
        [
            {"account_id": deposit_acc, "debit": "1500.00"},
            {"account_id": liability, "credit": "1500.00"},
        ],
    )
    liquidity = _ok(
        client.get(f"{A}/ledgers/{ledger}/liquidity", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert Decimal(liquidity["free_funds"]) == Decimal("2000.00")
    assert Decimal(liquidity["segregated_deposits"]) == Decimal("1500.00")
    kinds = {a["number"]: a["kind"] for a in liquidity["accounts"]}
    assert (kinds["001210"], kinds["001220"]) == ("free", "deposit")

    provider = _provider(client, h, approver, "Dienst D56")
    cost_account = next(
        a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
        if a["category"] == "cost"
    )
    inv = _invoice(client, h, acc_user, ledger, provider, cost_account, "D56-1", "500.00")
    from_deposit = client.post(
        f"{B}/payment-orders",
        json={
            "invoice_id": inv,
            "property_bank_account_id": deposit_bank["id"],
            "execution_date": "2026-02-05",
        },
        headers=h,
    )
    assert from_deposit.status_code == 422, from_deposit.text
    assert "Kautionskonto" in from_deposit.json()["detail"]
    order = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv,
                "property_bank_account_id": rent_bank["id"],
                "execution_date": "2026-02-05",
            },
            headers=h,
        ),
        201,
    )
    assert order["amount"] == "500.00"
    assert acc["070000"] == liability

    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    _ok(
        client.put(
            f"{DD}/creditor-ids/legal-entities/{entity}",
            json={"sepa_creditor_id": "DE98ZZZ09999999999"},
            headers=h,
        )
    )
    debit_onto_deposit = client.post(
        DD,
        json={
            "ledger_id": ledger,
            "collection_date": "2026-12-31",
            "lead_days": 0,
            "property_bank_account_id": deposit_bank["id"],
        },
        headers=h,
    )
    assert debit_onto_deposit.status_code == 422, debit_onto_deposit.text
    assert "Kautionskonto" in debit_onto_deposit.json()["detail"]
    # The deposit stays booked where it is: bank 001220 1.500,00 against liability 070000.
    tb = _trial_balance(client, h, ledger, "2026-12-31")
    assert (tb["001220"], tb["070000"], tb["001210"]) == (
        Decimal("1500.00"),
        Decimal("-1500.00"),
        Decimal("2000.00"),
    )
