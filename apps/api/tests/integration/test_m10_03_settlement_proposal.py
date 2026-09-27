"""M10-03 (7.4 Nr. 5, D39): settlement proposal in the statutory order via the API. The
proposal writes nothing; a confirmation makes a draft with an explicit settlement plan and an
audit event with the rule version; posting stays on the existing path and immediate posting is
locked by G1. Expected values are computed by hand in the comments (rule 0.1.8)."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import (
    A,
    _book,
    _entry,
    _hoa_ledger,
    _line,
    _ok,
)

pytestmark = pytest.mark.integration
P = "open-items/settlement-proposal"


async def _world(settings: Any) -> World:
    """Own tenants and users; the ledger module's fixture must not be provisioned twice."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"l3-{RUN}", name=f"Buch3 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"l4-{RUN}", name=f"Buch4 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m1003admin", a, "tenant_admin"),
            ("m1003reader", a, "read_only"),
            ("m1003clerk", a, "clerk_no_accounting"),
            ("m1003other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _code(response: Any) -> str:
    return str(response.json().get("code"))


def _open(c: TestClient, h: dict[str, str], ledger: str, day: str) -> dict[str, str]:
    rows = _ok(c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": day}, headers=h))
    return {r["id"]: str(r["remaining"]) for r in rows}


def test_statutory_order_determination_confirmation_and_locks(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "m1003admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "731")

    # Open items of the debtor (all posted, non leading ledger):
    #   R1 Hausgeld 08/2026: 300,00 due 01.08.2026, reference SO-8
    #   R2 Hausgeld 09/2026: 250,00 due 01.09.2026, reference SO-9
    #   F  Mahngebühr:        5,00 due 01.08.2026 (costs, kind dunning_fee)
    #   R3 Hausgeld 10/2026: 200,00 due 01.10.2026 (not yet due on 26.09.2026)
    def receivable(kind: str, amount: str, day: str, due: str, ref: str) -> str:
        entry = _book(
            client,
            h,
            ledger,
            _entry(
                kind,
                day,
                [_line(debtor, amount), _line(acc["060100"], "0", amount)],
                due_date=due,
                reference=ref,
            ),
        )
        return str(entry["id"])

    e1 = receivable("receivable", "300.00", "2026-07-20", "2026-08-01", "SO-8")
    e2 = receivable("receivable", "250.00", "2026-08-20", "2026-09-01", "SO-9")
    ef = receivable("dunning_fee", "5.00", "2026-08-15", "2026-08-01", "MG-1")
    e3 = receivable("receivable", "200.00", "2026-09-20", "2026-10-01", "SO-10")
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-09-26"}, headers=h)
    )
    by_entry = {r["journal_entry_id"]: r["id"] for r in items}
    r1, r2, f, r3 = by_entry[e1], by_entry[e2], by_entry[ef], by_entry[e3]
    before = _open(client, h, ledger, "2026-09-26")

    # Payment 500,00 without determination on 26.09.2026. Statutory order: due items first,
    # oldest due date 01.08. with costs before principal -> F 5,00, R1 300,00; then R2 195,00
    # (partial). R3 (due 01.10.) is not touched.
    body = {
        "account_id": debtor,
        "amount": "500.00",
        "as_of": "2026-09-26",
        "purpose": "Hausgeld",
    }
    proposal = _ok(client.post(f"{A}/ledgers/{ledger}/{P}", json=body, headers=h))
    assert proposal["rule"] == "M10-03"
    assert proposal["rule_version"] == "1"
    assert proposal["requires_confirmation"] is True
    assert proposal["note"] == "Vorschlag nach gesetzlicher Reihenfolge, Rechtsprüfung vor G1 offen"
    assert proposal["basis"] == "statutory_order"
    assert [(a["open_item_id"], a["amount"]) for a in proposal["allocations"]] == [
        (f, "5.00"),
        (r1, "300.00"),
        (r2, "195.00"),
    ]
    assert proposal["allocations"][0]["claim_class"] == "costs"
    assert Decimal(proposal["unallocated"]) == Decimal("0.00")
    # Nothing was written: open items unchanged, no draft.
    assert _open(client, h, ledger, "2026-09-26") == before
    drafts = _ok(client.get(f"{A}/ledgers/{ledger}/entries", params={"status": "draft"}, headers=h))
    assert [d for d in drafts if d["status"] == "draft"] == []

    # D39: a determination in the purpose ("Hausgeld 10/2026") wins over the statutory order.
    named = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/{P}",
            json={**body, "amount": "200.00", "purpose": "Hausgeld 10/2026"},
            headers=h,
        )
    )
    assert named["basis"] == "determination"
    assert [(a["open_item_id"], a["amount"], a["reason"]) for a in named["allocations"]] == [
        (r3, "200.00", "Bestimmung des Zahlers")
    ]
    # Explicit determination list with an amount: 100,00 on R2, the remaining 20,00 of a 120,00
    # payment in statutory order -> F 5,00, R1 15,00.
    mixed = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/{P}",
            json={
                **body,
                "amount": "120.00",
                "determination": [{"open_item_id": r2, "amount": "100.00"}],
            },
            headers=h,
        )
    )
    assert mixed["basis"] == "mixed"
    assert [(a["open_item_id"], a["amount"]) for a in mixed["allocations"]] == [
        (r2, "100.00"),
        (f, "5.00"),
        (r1, "15.00"),
    ]

    # Confirmation is required and audited: reader may compute, not confirm; wrong fingerprint
    # is refused; the confirmed proposal becomes a draft with the settlement plan.
    reader = bearer(login(client, world, "m1003reader"))
    assert client.post(f"{A}/ledgers/{ledger}/{P}", json=body, headers=reader).status_code == 200
    confirm = {
        **body,
        "fingerprint": proposal["fingerprint"],
        "bank_account_id": acc["001200"],
        "booking_date": "2026-09-26",
    }
    assert (
        client.post(f"{A}/ledgers/{ledger}/{P}/confirm", json=confirm, headers=reader).status_code
        == 403
    )
    stale = client.post(
        f"{A}/ledgers/{ledger}/{P}/confirm",
        json={**confirm, "fingerprint": "0" * 64},
        headers=h,
    )
    assert stale.status_code == 409
    # G1 closed: immediate posting through the confirmation is refused, nothing is written.
    gated = client.post(
        f"{A}/ledgers/{ledger}/{P}/confirm",
        json={**confirm, "post_immediately": True},
        headers=h,
    )
    assert gated.status_code == 403
    assert _code(gated) == "MHVP-GATE-0001"
    assert _open(client, h, ledger, "2026-09-26") == before

    draft = _ok(client.post(f"{A}/ledgers/{ledger}/{P}/confirm", json=confirm, headers=h), 201)
    assert draft["status"] == "draft"
    assert draft["kind"] == "debtor_payment"
    assert [(p["open_item_id"], p["amount"]) for p in draft["settlement_plan"]] == [
        (f, "5.00"),
        (r1, "300.00"),
        (r2, "195.00"),
    ]
    assert {(line["debit"], line["credit"]) for line in draft["lines"]} == {
        ("500.00", "0.00"),
        ("0.00", "500.00"),
    }
    assert _open(client, h, ledger, "2026-09-26") == before  # draft: still nothing settled
    events = _ok(
        client.get(
            "/api/v1/tenant/events",
            params={"type": "open_item_settlement.proposal_confirmed", "page_size": 200},
            headers=h,
        )
    )
    event = next(e for e in events if e["entity_id"] == draft["id"])["payload"]
    assert event["rule"] == "M10-03"
    assert event["rule_version"] == "1"
    assert event["fingerprint"] == proposal["fingerprint"]
    assert event["basis"] == "statutory_order"
    assert [a["rank"] for a in event["allocations"]] == [1, 2, 3]

    # Posting stays on the existing path (non leading ledger). Rest afterwards:
    # F 0, R1 0, R2 250 - 195 = 55,00, R3 200,00.
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    after = _open(client, h, ledger, "2026-09-26")
    assert after == {r2: "55.00", r3: "200.00"}

    # Overpayment: 100,00 on the remaining 55,00 + 200,00 (not due) -> R2 55,00, R3 45,00.
    over = _ok(
        client.post(f"{A}/ledgers/{ledger}/{P}", json={**body, "amount": "100.00"}, headers=h)
    )
    assert [(a["open_item_id"], a["amount"]) for a in over["allocations"]] == [
        (r2, "55.00"),
        (r3, "45.00"),
    ]
    more = _ok(
        client.post(f"{A}/ledgers/{ledger}/{P}", json={**body, "amount": "300.00"}, headers=h)
    )
    assert Decimal(more["unallocated"]) == Decimal("45.00")  # credit, never income (D07)

    # Tenant separation and legal entity: other tenant 404, foreign debtor account 404.
    other = bearer(login(client, world, "m1003other"))
    assert client.post(f"{A}/ledgers/{ledger}/{P}", json=body, headers=other).status_code == 404
    other_ledger, _, other_debtor = _hoa_ledger(client, h, "732")
    foreign = client.post(
        f"{A}/ledgers/{other_ledger}/{P}", json={**body, "account_id": debtor}, headers=h
    )
    assert foreign.status_code == 404
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/{P}", json={**body, "account_id": other_debtor}, headers=h
        ).status_code
        == 404
    )
    clerk = bearer(login(client, world, "m1003clerk"))
    assert client.post(f"{A}/ledgers/{ledger}/{P}", json=body, headers=clerk).status_code == 403
