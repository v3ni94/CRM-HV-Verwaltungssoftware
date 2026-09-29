"""Creditor memory in the receipt intake, step S7 (ADR 0014, rule M12-04, plan M12, 9.2):
cost account proposals per invoice line from the confirmed invoices and the bank decisions
of the same creditor in the same ledger, source Verlauf, decision diff captured.

Fixed expected values (rule 0.1.8): with the switch off the answer says so and proposes
nothing; the first invoice of a creditor has no proposal (outcome ``no_proposal``); the
second draft gets the accounts of the first invoice per line (count 1, reason names the
invoice and the position or wording); confirming other accounts records ``modified`` with the
diff per line, confirming the proposal records ``accepted_unchanged``; a booked outgoing bank
transaction of the creditor counts as bank decision; another ledger (legal entity) of the
same tenant sees nothing; caretaker 403, other tenant 404, unknown ledger 404. Nothing is
taken over automatically and nothing is posted."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m11_banking import _camt, _ntry
from tests.integration.test_m14_receipt_drafts import (
    KNOWN,
    PROVIDER,
    FakeProvider,
    _confirm_body,
    _ok,
    _settings,
    _setup_ledger,
    _start,
    _upload,
    _xrechnung,
)

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
R = "/api/v1/receipts"
T = "/api/v1/tenant"
BUCKET = "mhvp-receipts"
HOA_IBAN = "DE27100777770209299700"


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rcha-{RUN}", name=f"Verlauf {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rcvb-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("rhadmin", a, "tenant_admin"),
            ("rhsecond", a, "tenant_admin"),
            ("rhcare", a, "caretaker"),
            ("rhother", b, "tenant_admin"),
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


def _draft(client: TestClient, h: dict[str, str], number: str, supplier: str) -> dict[str, Any]:
    doc = _upload(client, h, f"{number}.xml", _xrechnung(number, supplier), "application/xml")
    draft = _start(client, h, doc)
    assert draft["status"] == "proposed"
    assert draft["account_proposals"] is None  # nothing without ledger and provider
    return dict(draft)


def _read(
    client: TestClient, h: dict[str, str], draft_id: str, ledger: str, provider: str
) -> dict[str, Any]:
    return dict(
        _ok(
            client.get(
                f"{R}/drafts/{draft_id}",
                params={"ledger_id": ledger, "provider_contact_id": provider},
                headers=h,
            )
        )["account_proposals"]
    )


def _lines(accounts: dict[str, str], first: str, second: str) -> list[dict[str, str]]:
    """Two lines with the wording of the XML lines (the reviewer keeps the descriptions)."""
    return [
        {
            "account_id": accounts[first],
            "net": "400.00",
            "vat_percent": "19",
            "vat": "76.00",
            "text": "Arbeitszeit Reinigung",
        },
        {
            "account_id": accounts[second],
            "net": "100.00",
            "vat_percent": "19",
            "vat": "19.00",
            "text": "Reinigungsmittel",
        },
    ]


def test_account_proposals_from_creditor_history_with_decision_diff(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "rhadmin"))
    second = bearer(login(client, world, "rhsecond"))
    care = bearer(login(client, world, "rhcare"))
    other = bearer(login(client, world, "rhother"))
    dpa = _upload(client, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        client.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=admin,
        )
    )
    _ok(client.post("/api/v1/ai/providers/anthropic/release", headers=second))
    ledger, accounts, provider, property_id = _setup_ledger(client, admin, offset=71)
    cost = sorted(n for n in accounts if n.startswith("04") and n != "040100")
    other_cost = cost[0]
    supplier = f"Belegki Handwerk {RUN} GmbH"
    calls_before = len(fake.calls)

    # Switch off: the answer says so, proposes nothing, and confirming records no decision.
    first = _draft(client, admin, f"VH-{RUN}-1", supplier)
    off = _read(client, admin, first["id"], ledger, provider)
    assert off == {**off, "enabled": False, "lines": []}
    _ok(
        client.put(
            f"{B}/learning",
            json={"enabled": True, "reason": "Datenschutzprüfung im Test simuliert"},
            headers=admin,
        )
    )

    # First invoice of the creditor: no history yet, the reviewer chooses freely; the
    # decision is recorded as no_proposal.
    on = _read(client, admin, first["id"], ledger, provider)
    assert on["enabled"] is True
    assert [ln["proposals"] for ln in on["lines"]] == [[], []]  # two XML lines, no history
    assert on["sources"] == {"invoices": 0, "bank_decisions": 0}
    confirmed = _ok(
        client.post(
            f"{R}/drafts/{first['id']}/confirm",
            json=_confirm_body(
                ledger,
                accounts,
                provider,
                invoice={"number": f"VH-{RUN}-1", "lines": _lines(accounts, "040100", other_cost)},
            ),
            headers=admin,
        ),
        201,
    )
    assert confirmed["account_proposal_decision"]["outcome"] == "no_proposal"
    assert confirmed["account_proposal_decision"]["diff"] == []
    invoice = _ok(client.get(f"{A}/invoices/{confirmed['invoice_id']}", headers=admin))
    assert invoice["posting_status"] == "unposted"  # confirming never posts

    # Second draft of the same creditor: the accounts of the first invoice per line, the
    # reason names the invoice and the same wording (the XML lines repeat).
    second_draft = _draft(client, admin, f"VH-{RUN}-2", supplier)
    proposals = _read(client, admin, second_draft["id"], ledger, provider)
    assert proposals["sources"] == {"invoices": 1, "bank_decisions": 0}
    line0, line1 = proposals["lines"]
    assert line0["proposals"][0]["account_number"] == "040100"
    assert line1["proposals"][0]["account_number"] == other_cost
    top = line0["proposals"][0]
    assert (top["count"], top["count_invoices"], top["count_posted"], top["count_bank"]) == (
        1,
        1,
        0,
        0,
    )
    assert top["source"] == "history"
    assert top["last_used_on"] == "2026-03-01"
    assert top["reason"] == "1 mal auf Rechnungen des Ausstellers erfasst, gleicher Positionstext"
    assert top["account_id"] == accounts["040100"]
    # Only identity and counts travel: no allocation, cost type or VAT attribute.
    assert not {"allocation_category", "operating_cost_type", "vat_option"} & set(top)
    assert "Umlagefähigkeit" in proposals["note"]
    # Confirming other accounts than proposed: modified, diff per line, event carries it.
    confirmed2 = _ok(
        client.post(
            f"{R}/drafts/{second_draft['id']}/confirm",
            json=_confirm_body(
                ledger,
                accounts,
                provider,
                invoice={"number": f"VH-{RUN}-2", "lines": _lines(accounts, other_cost, "040100")},
            ),
            headers=admin,
        ),
        201,
    )
    decision = confirmed2["account_proposal_decision"]
    assert decision["outcome"] == "modified"
    assert [d["index"] for d in decision["diff"]] == [0, 1]
    assert decision["diff"][0]["proposed_account_id"] == accounts["040100"]
    assert decision["diff"][0]["final_account_id"] == accounts[other_cost]
    assert decision["ledger_id"] == ledger
    events = _ok(
        client.get(f"{T}/events", params={"type": "receipt_draft.confirmed"}, headers=admin)
    )
    mine = next(e for e in events if e["entity_id"] == second_draft["id"])
    assert mine["payload"]["account_proposal_outcome"] == "modified"
    assert len(mine["payload"]["account_proposal_diff"]) == 2

    # A booked outgoing bank transaction of the creditor (counter account chosen by a
    # person) counts as bank decision for that account.
    bank_id = _ok(
        client.post(
            f"/api/v1/properties/{property_id}/bank-accounts",
            json={
                "legal_entity_id": invoice["ledger_id"] and _ledger_entity(client, admin, ledger),
                "kind": "hoa",
                "iban": HOA_IBAN,
                "holder": "GdWE Verlauf",
                "valid_from": "2020-01-01",
            },
            headers=admin,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001210",
                "name": "WEG-Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank_id,
            },
            headers=admin,
        ),
        201,
    )
    _ok(
        client.post(
            f"{B}/imports",
            json={
                "document_id": _upload(
                    client,
                    admin,
                    "VH.xml",
                    _camt(
                        "VH-1",
                        HOA_IBAN,
                        "0.00",
                        "0.00",
                        [_ntry("V1", "80.00", "DBIT", "2026-04-02", KNOWN, "Abschlag Reinigung")],
                    ),
                    "application/xml",
                )
            },
            headers=admin,
        ),
        201,
    )
    tx = next(
        t
        for t in _ok(client.get(f"{B}/transactions", headers=admin))
        if t["bank_reference"] == "V1"
    )
    _ok(
        client.post(
            f"{B}/transactions/{tx['id']}/book",
            json={"settlements": [], "counter_account_id": accounts["040100"]},
            headers=admin,
        ),
        201,
    )
    third = _draft(client, admin, f"VH-{RUN}-3", supplier)
    proposals = _read(client, admin, third["id"], ledger, provider)
    assert proposals["sources"] == {"invoices": 2, "bank_decisions": 1}
    top = proposals["lines"][0]["proposals"][0]
    assert top["account_number"] == "040100"
    assert (top["count"], top["count_invoices"], top["count_bank"]) == (3, 2, 1)
    assert top["last_used_on"] == "2026-04-02"
    assert "1 mal bei Bankumsätzen des Ausstellers gewählt" in top["reason"]
    # Confirming the proposal as shown: accepted_unchanged.
    proposed = [ln["proposals"][0]["account_number"] for ln in proposals["lines"]]
    confirmed3 = _ok(
        client.post(
            f"{R}/drafts/{third['id']}/confirm",
            json=_confirm_body(
                ledger,
                accounts,
                provider,
                invoice={
                    "number": f"VH-{RUN}-3",
                    "lines": _lines(accounts, proposed[0], proposed[1]),
                },
            ),
            headers=admin,
        ),
        201,
    )
    assert confirmed3["account_proposal_decision"]["outcome"] == "accepted_unchanged"
    assert confirmed3["account_proposal_decision"]["diff"] == []
    assert len(fake.calls) == calls_before  # XRechnung: no provider call at any point

    # Separation: another ledger of the same tenant sees no invoices of this creditor;
    # caretaker 403, other tenant 404, unknown ledger 404; switch off hides everything.
    ledger2, _accounts2, _provider2, _prop2 = _setup_ledger(client, admin, offset=72)
    fourth = _draft(client, admin, f"VH-{RUN}-4", supplier)
    foreign = _read(client, admin, fourth["id"], ledger2, provider)
    assert foreign["sources"] == {"invoices": 0, "bank_decisions": 0}
    assert [ln["proposals"] for ln in foreign["lines"]] == [[], []]
    params = {"ledger_id": ledger, "provider_contact_id": provider}
    assert client.get(f"{R}/drafts/{fourth['id']}", params=params, headers=care).status_code == 403
    assert client.get(f"{R}/drafts/{fourth['id']}", params=params, headers=other).status_code == 404
    assert (
        client.get(
            f"{R}/drafts/{fourth['id']}",
            params={**params, "ledger_id": "00000000-0000-0000-0000-000000000001"},
            headers=admin,
        ).status_code
        == 404
    )
    _ok(client.put(f"{B}/learning", json={"enabled": False, "reason": "Test Ende"}, headers=admin))
    assert _read(client, admin, fourth["id"], ledger, provider)["enabled"] is False
    confirmed4 = _ok(
        client.post(
            f"{R}/drafts/{fourth['id']}/confirm",
            json=_confirm_body(ledger, accounts, provider, invoice={"number": f"VH-{RUN}-4"}),
            headers=admin,
        ),
        201,
    )
    assert confirmed4["account_proposal_decision"] is None


def _ledger_entity(client: TestClient, h: dict[str, str], ledger: str) -> str:
    return str(_ok(client.get(f"{A}/ledgers/{ledger}", headers=h))["legal_entity_id"])
