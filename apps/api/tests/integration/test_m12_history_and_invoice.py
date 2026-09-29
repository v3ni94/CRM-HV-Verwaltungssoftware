"""Learning bookkeeper, step S3 (ADR 0013, rule M12-04, plan M12): stage 1d memory and the
account assignment from a linked posted invoice, both proposals only.

Fixed expected values (rule 0.1.8): the history source appears from the second confirmed
booking of the same payer in the same legal entity and direction (confidence 0,6 for two,
0,7 for three cases), names the debtor account, the exactly fitting open item and the
journal entries; a reversal with reason code turns a booking into a counter example and
halves the confidence at once; the pending snapshot refreshes because the features changed;
the history never appears with the switch off, never for another legal entity with the same
payer IBAN, never for another tenant (404) and never without accounting:read (403). A
posted invoice linked to an outgoing transaction yields the invoice source with the creditor
account, the open payable and the cost accounts of the lines; an own payment order found by
its end-to-end id makes the payable match unambiguous. Nothing here posts automatically."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.banking.tasks import compute_proposals_once, process_events_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m11_invoice_matching import _review_all
from tests.integration.test_m12_posting_decisions import (
    PAYERS,
    _decisions,
    _hoa,
    _import,
    _later,
    _ok,
    _receivable,
    _settings,
)

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
A = "/api/v1/accounting"
BANK3 = "DE27100777770209299700"
BANK4 = "DE12500105170648489890"
KNOWN = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lbh-{RUN}", name=f"Verlauf {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lbi-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("hsadmin", a, "tenant_admin"),
            ("hssecond", a, "tenant_admin"),
            ("hscare", a, "caretaker"),
            ("hsother", b, "tenant_admin"),
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


def _ntry_e2e(ref: str, amount: str, ind: str, day: str, iban: str, purpose: str, e2e: str) -> str:
    party = "Dbtr" if ind == "CRDT" else "Cdtr"
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{ind}</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>{day}</Dt></BookgDt><ValDt><Dt>{day}</Dt></ValDt><AcctSvcrRef>{ref}</AcctSvcrRef>
<NtryDtls><TxDtls><Refs><EndToEndId>{e2e}</EndToEndId></Refs>
<RltdPties><{party}><Nm>Gegenpartei</Nm></{party}><{party}Acct><Id><IBAN>{iban}</IBAN></Id></{party}Acct></RltdPties>
<RmtInf><Ustrd>{purpose}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def _proposals(client: TestClient, h: dict[str, str], tx_id: str) -> dict[str, Any]:
    return dict(_ok(client.get(f"{B}/transactions/{tx_id}/posting-proposals", headers=h)))


def _history(proposals: dict[str, Any]) -> dict[str, Any] | None:
    return next((p for p in proposals["stage1"] if p["source"] == "history"), None)


def _book_best(client: TestClient, h: dict[str, str], tx_id: str) -> dict[str, Any]:
    shown = _proposals(client, h, tx_id)
    full = next(p for p in shown["stage1"] if p["kind"] == "full")
    return dict(
        _ok(
            client.post(
                f"{B}/transactions/{tx_id}/book",
                json={
                    "settlements": [
                        {"open_item_id": s["open_item_id"], "amount": s["amount"]}
                        for s in full["splits"]
                    ],
                    "proposal_id": shown["learning"]["decision_id"],
                    "chosen": shown["stage1"].index(full),
                },
                headers=h,
            ),
            201,
        )
    )


def test_history_source_from_confirmed_decisions_with_reversal_as_counter_example(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "hsadmin"))
    care = bearer(login(client, world, "hscare"))
    other = bearer(login(client, world, "hsother"))
    w = _hoa(client, h, "811", BANK3)
    first = w["contracts"][0]
    n1 = first["number"]
    debtor = w["debtors"][first["unit_id"]]
    debtor_number = next(
        a["number"]
        for a in _ok(client.get(f"{A}/ledgers/{w['ledger']}/accounts", headers=h))
        if a["id"] == debtor
    )
    _ok(
        client.put(
            f"{B}/learning",
            json={"enabled": True, "reason": "Datenschutzprüfung im Test simuliert"},
            headers=h,
        )
    )
    asyncio.run(process_events_once(settings))
    third_entry = ""

    # Three bookings of the same payer to the same debtor account, each confirmed by a
    # person from the full match (contract number in the purpose). Before the second
    # booking there is one case only: no history proposal (minimum two).
    for k, month in enumerate(["Februar", "März", "April"], start=1):
        if k > 1:
            _receivable(
                client, h, w["ledger"], debtor, w["income"], first["id"], text_=f"Hausgeld {month}"
            )
        run = _import(
            client,
            h,
            f"H-{k}",
            BANK3,
            [_ntry(f"H{k}", "250.00", "CRDT", f"2026-0{k + 1}-05", PAYERS[0], f"Hausgeld {n1}")],
        )
        tx_id = run["txs"][f"H{k}"]["id"]
        shown = _proposals(client, h, tx_id)
        if k == 1:
            assert _history(shown) is None
        elif k == 2:
            assert _history(shown) is None  # one confirmed case is below the minimum
        else:
            memory = _history(shown)
            assert memory is not None
            assert memory["evidence"]["count"] == 2
            assert memory["confidence"] == 0.6
        booked = _book_best(client, h, tx_id)
        assert booked["number"]
        if k == 3:
            third_entry = booked["journal_entry_id"]

    # Fourth payment without any contract number: the deterministic match is weak (IBAN on
    # file plus amount), the history names the debtor account with three cases, the exactly
    # fitting open item and the three journal entries with labels.
    _receivable(client, h, w["ledger"], debtor, w["income"], first["id"], text_="Hausgeld Mai")
    fourth = _import(
        client,
        h,
        "H-4",
        BANK3,
        [_ntry("H4", "250.00", "CRDT", "2026-05-05", PAYERS[0], "Ueberweisung")],
    )
    t4 = fourth["txs"]["H4"]["id"]
    run4 = uuid.UUID(fourth["run"]["id"])
    shown = _proposals(client, h, t4)
    memory = _history(shown)
    assert memory is not None
    assert memory["kind"] == "history"
    assert memory["confidence"] == 0.7
    assert memory["unambiguous"] is False
    assert memory["postable"] is False
    assert memory["account_number"] == debtor_number
    assert memory["evidence"]["count"] == 3
    assert memory["evidence"]["contradictions"] == 0
    assert memory["evidence"]["accounts"] == [debtor_number]
    entries = memory["evidence"]["entries"]
    assert len(entries) == 3
    assert all(e["journal_entry_id"] and e["label"] and e["reversed"] is False for e in entries)
    assert [e["booking_date"] for e in entries] == ["2026-02-05", "2026-03-05", "2026-04-05"]
    assert memory["reasoning"][0] == "Zuletzt 3 mal so gebucht, 0 Widersprüche"
    assert any("kein Nachweis" in r for r in memory["reasoning"])
    assert len(memory["splits"]) == 1  # exactly one open item of the account with 250,00
    weak = next(p for p in shown["stage1"] if p["source"] == "match")
    assert weak["kind"] == "weak"
    # The pending snapshot carries the same history (counts only in the minimised summary).
    pending = _decisions(client, h, t4)[-1]
    assert pending["status"] == "pending"
    assert pending["features"]["history_count"] == 3
    assert pending["features"]["history_reversed"] == 0
    assert _history({"stage1": pending["proposals"]}) is not None
    assert "history" not in pending["features"]  # no entries in the stored summary
    assert pending["engine_version"] == "2026.09.28-2"

    # Reversal of the third booking with reason code: counter example at once (2 consistent,
    # 1 contradiction, 0,6 halved to 0,3); the consumer reopens the transaction and the
    # pending snapshot of the fourth payment is refreshed (features changed, new round).
    _ok(
        client.post(
            f"{A}/ledgers/{w['ledger']}/entries/{third_entry}/reverse",
            json={"reason": "Falsches Konto", "reason_code": "wrong_assignment"},
            headers=h,
        ),
        201,
    )
    consumed = asyncio.run(process_events_once(settings, now=_later()))
    assert consumed["failed"] == 0
    shown = _proposals(client, h, t4)
    memory = _history(shown)
    assert memory is not None
    assert memory["confidence"] == 0.3
    assert memory["evidence"]["count"] == 2
    assert memory["evidence"]["contradictions"] == 1
    assert [e["reversed"] for e in memory["evidence"]["entries"]] == [False, False, True]
    assert any("storniert" in r for r in memory["reasoning"])
    refreshed = asyncio.run(compute_proposals_once(settings, world.tenant_a, run4))
    assert refreshed["computed"] == 1
    rows = _decisions(client, h, t4)
    assert [r["status"] for r in rows] == ["expired", "pending"]
    assert rows[-1]["features"]["history_reversed"] == 1

    # Permissions and separation: caretaker 403, other tenant 404, same payer IBAN in another
    # legal entity of the same tenant: no history (B01, E01).
    assert client.get(f"{B}/transactions/{t4}/posting-proposals", headers=care).status_code == 403
    assert client.get(f"{B}/transactions/{t4}/posting-proposals", headers=other).status_code == 404
    w2 = _hoa(client, h, "812", BANK4)
    foreign = _import(
        client,
        h,
        "H-5",
        BANK4,
        [_ntry("H5", "250.00", "CRDT", "2026-05-06", PAYERS[0], "Ueberweisung")],
    )
    t5 = foreign["txs"]["H5"]["id"]
    assert _history(_proposals(client, h, t5)) is None
    assert w2["hoa"] != w["hoa"]

    # Switch off: the history disappears from the proposals; nothing else changes.
    _ok(client.put(f"{B}/learning", json={"enabled": False, "reason": "Test Ende"}, headers=h))
    off = _proposals(client, h, t4)
    assert _history(off) is None
    assert off["learning"]["enabled"] is False
    assert any(p["source"] == "match" for p in off["stage1"])


def test_invoice_source_from_linked_posted_invoice_and_own_payment_order(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "hsadmin"))
    second = bearer(login(client, world, "hssecond"))
    w = _hoa(client, h, "813", "DE02100100100006820101")
    accounts = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{w['ledger']}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Aufzug Verlauf {RUN} GmbH",
                "bank_accounts": [{"iban": KNOWN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, second, provider)
    number = f"RV-{RUN}-1"
    inv = _ok(
        client.post(
            f"{A}/invoices",
            json={
                "ledger_id": w["ledger"],
                "provider_contact_id": provider,
                "number": number,
                "invoice_date": "2026-02-01",
                "due_date": "2026-02-15",
                "service_from": "2026-01-01",
                "service_to": "2026-01-31",
                "net": "1000.00",
                "vat": "190.00",
                "gross": "1190.00",
                "payee_iban": KNOWN,
                "order_reference": "AUF-1",
                "lines": [
                    {
                        "account_id": accounts["040100"],
                        "net": "1000.00",
                        "vat_percent": "19",
                        "vat": "190.00",
                        "text": "Wartung Aufzug",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    _review_all(client, h, inv["id"])
    _ok(client.post(f"{A}/invoices/{inv['id']}/release", headers=second))
    posted = _ok(client.post(f"{A}/invoices/{inv['id']}/post", headers=h))
    assert posted["posting_status"] == "posted"

    # Outgoing payment with the invoice number: linked by the invoice matching (evidence
    # only), then the invoice source carries creditor account, payable and line accounts.
    paid = _import(
        client,
        h,
        "I-1",
        w["iban"],
        [_ntry("I1", "1190.00", "DBIT", "2026-02-10", KNOWN, f"{number} Zahlung")],
    )
    t1 = paid["txs"]["I1"]["id"]
    before = _proposals(client, h, t1)
    assert all(p["source"] != "invoice" for p in before["stage1"])
    matched = _ok(client.post(f"{B}/invoice-matching/{inv['id']}/match", headers=h))
    assert len(matched["matches"]) == 1
    shown = _proposals(client, h, t1)
    from_invoice = next(p for p in shown["stage1"] if p["source"] == "invoice")
    assert from_invoice["kind"] == "invoice"
    assert from_invoice["confidence"] == 0.9
    assert from_invoice["unambiguous"] is True
    assert from_invoice["postable"] is False
    assert from_invoice["account_number"].startswith("07")  # creditor account of the provider
    assert from_invoice["evidence"]["number"] == number
    assert from_invoice["evidence"]["match_basis"] == "amount_and_number"
    (line,) = from_invoice["evidence"]["lines"]
    assert (line["account_number"], line["net"], line["text"]) == (
        "040100",
        "1000.00",
        "Wartung Aufzug",
    )
    assert len(from_invoice["splits"]) == 1
    assert from_invoice["splits"][0]["amount"] == "1190.00"
    payable = next(p for p in shown["stage1"] if p["source"] == "match")
    assert payable["kind"] == "invoice"
    assert payable["splits"][0]["open_item_id"] == from_invoice["splits"][0]["open_item_id"]

    # Own payment order (draft, G2 closed, nothing is paid) found by its end-to-end id: the
    # payable match of a second transaction without invoice number gains the end-to-end
    # evidence and becomes unambiguous.
    order = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv["id"],
                "property_bank_account_id": w["bank_id"],
                "execution_date": "2026-02-20",
            },
            headers=h,
        ),
        201,
    )
    assert order["status"] == "draft"
    e2e = order["end_to_end_id"]
    run = _ok(
        client.post(
            f"{B}/imports",
            json={
                "document_id": _upload(
                    client,
                    h,
                    "I-2.xml",
                    _camt(
                        "I-2",
                        w["iban"],
                        "0.00",
                        "0.00",
                        [_ntry_e2e("I2", "1190.00", "DBIT", "2026-02-21", KNOWN, "Zahlung", e2e)],
                    ),
                )
            },
            headers=h,
        ),
        201,
    )
    assert run["id"]
    t2 = next(
        t["id"]
        for t in _ok(client.get(f"{B}/transactions", headers=h))
        if t["bank_reference"] == "I2"
    )
    shown = _proposals(client, h, t2)
    payable = next(p for p in shown["stage1"] if p["source"] == "match")
    assert payable["kind"] == "invoice"
    assert payable["unambiguous"] is True
    assert "End-to-End-Referenz des eigenen Zahlungsauftrags" in payable["reasoning"]
    assert all(p["postable"] is False for p in shown["stage1"])
