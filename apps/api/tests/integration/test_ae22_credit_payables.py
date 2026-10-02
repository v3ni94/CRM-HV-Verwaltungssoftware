"""AE22 (P04-04, Q01-01, M15-07): payables from statement credits.

Expected values by hand: the posted result entry of the rental statement credits the debtor
account of the contract with 80,00 EUR (Guthaben). Variant ``subledger``: the release adds a
payable of 80,00 on the debtor account, the payout order is 80,00. Variant ``reclass``: the
release writes a draft 80,00 debit debtor, credit creditor 070900; posting creates one payable
of 80,00 on 070900 and no receivable on the debtor; the withdrawal reverses the reclass entry
and leaves 0,00 open.

Fixture shortcut: the statement result entry is written through the accounting API with the
idempotency key of ``billing.results`` and the statement row is set to ``due`` with this entry
in ``result_entry_ids`` (the full statement flow is covered by the M17 tests).
"""

import asyncio
import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
C = "/api/v1/accounting/credit-payables"
OWN = "DE02120300000000202051"
TENANT_IBAN = "DE89370400440532013000"


class Gates:
    def __init__(self, *gates: ReleaseGate) -> None:
        self.gates = set(gates)

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in self.gates


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae22-{RUN}", name=f"AE22 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae22b-{RUN}", name=f"AE22B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae22admin", a, "tenant_admin"),
            ("ae22approver", a, "tenant_admin"),
            ("ae22reader", a, "read_only"),
            ("ae22other", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[dict[str, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=Gates(ReleaseGate.G3))) as g3,
        TestClient(
            create_app(settings, release_gate_resolver=Gates(ReleaseGate.G2, ReleaseGate.G3))
        ) as g23,
        TestClient(
            create_app(settings, release_gate_resolver=Gates(ReleaseGate.G1, ReleaseGate.G3))
        ) as g13,
    ):
        yield {"closed": closed, "g3": g3, "g23": g23, "g13": g13}


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _setup(
    c: TestClient,
    h: dict[str, str],
    approver: dict[str, str],
    database: Database,
    tenant: UUID,
    n: str,
) -> dict[str, Any]:
    """Rental property, owner entity with rent bank account, tenancy with approved tenant IBAN,
    owner ledger, posted statement credit of 80,00 on the debtor and a statement in ``due``."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": n, "name": f"AE22 Haus {n}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(c, h, f"AE22Vermieter{n}", "company")
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    bank = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "rent",
                "iban": OWN,
                "holder": f"Vermieter {n}",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    building = _ok(
        c.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    tenant_party, contact = _party(c, h, f"AE22Mieter{n}", iban=TENANT_IBAN)
    contact = approve_bank_accounts(c, approver, contact)
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant_party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    ledger = _ok(c.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)["id"]
    accounts = _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    debtor = next(a["id"] for a in accounts if a["category"] == "debtor")
    result = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "060900",
                "name": "Abrechnungsergebnis BK",
                "category": "revenue",
                "type": "income",
            },
            headers=h,
        ),
        201,
    )["id"]
    statement = _ok(
        c.post(
            "/api/v1/statements",
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )["id"]
    today = local_today().isoformat()
    entry = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "booking_date": today,
                "due_date": today,
                "text": f"Betriebskostenabrechnung 2025 Guthaben Einheit 01 {n}",
                "kind": "statement_result",
                "contract_id": contract,
                "idempotency_key": f"rent-statement:{statement}:{contract}",
                "lines": [
                    {"account_id": debtor, "debit": "0.00", "credit": "80.00"},
                    {"account_id": result, "debit": "80.00", "credit": "0.00"},
                ],
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(c.post(f"{A}/ledgers/{ledger}/entries/{entry}/post", headers=h))
    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        conn.execute(
            text(
                "UPDATE statement SET status = 'due', result_entry_ids = CAST(:ids AS jsonb) "
                "WHERE id = :id"
            ),
            {"ids": json.dumps([entry]), "id": statement},
        )
    engine.dispose()
    return {
        "ledger": ledger,
        "bank": bank,
        "contract": contract,
        "statement": statement,
        "entry": entry,
        "debtor": debtor,
        "payee": contact["bank_accounts"][0]["id"],
        "entity": entity,
        "property": prop["id"],
    }


def _open_items(c: TestClient, h: dict[str, str], ledger: str) -> list[dict[str, Any]]:
    return list(
        _ok(c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2099-12-31"}, headers=h))
    )


def test_ae22_subledger_release_order_and_storno(
    clients: dict[str, TestClient], world: World, database: Database
) -> None:
    c, g3, g23 = clients["closed"], clients["g3"], clients["g23"]
    h = bearer(login(c, world, "ae22admin"))
    approver = bearer(login(c, world, "ae22approver"))
    reader = bearer(login(c, world, "ae22reader"))
    other = bearer(login(c, world, "ae22other"))
    ctx = _setup(c, h, approver, database, world.tenant_a, "221")
    body = {
        "source_type": "rent_statement",
        "source_id": ctx["statement"],
        "contract_id": ctx["contract"],
    }

    # Default off: candidates are visible, nothing can be created.
    settings = _ok(c.get(f"{C}/settings", headers=reader))
    assert (settings["mode"], settings["four_eyes_required"]) == ("off", True)
    cands = _ok(c.get(f"{C}/candidates", params={"ledger_id": ctx["ledger"]}, headers=reader))
    assert [(x["source_type"], x["amount"], x["payout_reason"]) for x in cands] == [
        ("rent_statement", "80.00", "statement_credit")
    ]
    assert _ok(c.get(f"{C}/candidates", headers=other)) == []  # RLS
    assert c.get(f"{C}/candidates", params={"foo": "1"}, headers=reader).status_code == 422
    off = c.post(C, json=body, headers=h)
    assert off.status_code == 409
    assert "ausgeschaltet" in off.json()["detail"]
    assert c.put(f"{C}/settings", json={"mode": "subledger"}, headers=reader).status_code == 403
    assert c.put(f"{C}/settings", json={"mode": "auto"}, headers=h).status_code == 422
    _ok(c.put(f"{C}/settings", json={"mode": "subledger"}, headers=h))

    # Validation: amount of a statement credit is fixed, unknown sources are 404.
    assert c.post(C, json={**body, "amount": "70.00"}, headers=h).status_code == 422
    assert c.post(C, json={**body, "source_type": "x"}, headers=h).status_code == 422
    assert c.post(C, json=body, headers=reader).status_code == 403
    owner_sub = c.post(
        C, json={"source_type": "owner_statement", "source_id": ctx["statement"]}, headers=h
    )
    assert owner_sub.status_code == 409  # subledger needs a posted credit
    row = _ok(c.post(C, json=body, headers=h), 201)
    assert (row["status"], row["state"], row["variant"], row["amount"]) == (
        "proposed",
        "proposed",
        "subledger",
        "80.00",
    )
    assert c.post(C, json=body, headers=h).status_code == 409  # one active proposal
    assert c.get(f"{C}/{row['id']}", headers=other).status_code == 404
    assert _ok(c.get(f"{C}/candidates", params={"ledger_id": ctx["ledger"]}, headers=h)) == []

    # Release: G3, four eyes, accounting:approve.
    release = f"{C}/{row['id']}/release"
    closed = c.post(release, json={}, headers=approver)
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    gh = bearer(login(g3, world, "ae22admin"))
    gapprover = bearer(login(g3, world, "ae22approver"))
    assert (
        g3.post(release, json={}, headers=bearer(login(g3, world, "ae22reader"))).status_code == 403
    )
    same = g3.post(release, json={}, headers=gh)
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    released = _ok(g3.post(release, json={}, headers=gapprover))
    assert (released["status"], released["state"], released["remaining"]) == (
        "released",
        "open",
        "80.00",
    )
    payable = next(
        i for i in _open_items(c, h, ctx["ledger"]) if i["id"] == released["open_item_id"]
    )
    assert payable["kind"] == "payable"
    assert g3.post(release, json={}, headers=gapprover).status_code == 409

    # Payment order without invoice: G2 and G3.
    order_body = {
        "contact_bank_account_id": ctx["payee"],
        "property_bank_account_id": ctx["bank"],
        "execution_date": local_today().isoformat(),
    }
    options = _ok(c.get(f"{C}/{row['id']}/payout-options", headers=reader))
    assert [p["id"] for p in options["payees"]] == [ctx["payee"]]
    assert [b["id"] for b in options["bank_accounts"]] == [ctx["bank"]]
    assert c.get(f"{C}/{row['id']}/payout-options", headers=other).status_code == 404
    order_url = f"{C}/{row['id']}/payment-order"
    assert g3.post(order_url, json=order_body, headers=gh).status_code == 403
    oh = bearer(login(g23, world, "ae22admin"))
    assert g23.post(order_url, json={**order_body, "x": 1}, headers=oh).status_code == 422
    order = _ok(g23.post(order_url, json=order_body, headers=oh), 201)
    assert (order["kind"], order["amount"], order["payout_reason"], order["invoice_id"]) == (
        "payout",
        "80.00",
        "statement_credit",
        None,
    )
    assert g23.post(order_url, json=order_body, headers=oh).status_code == 409
    state = _ok(c.get(f"{C}/{row['id']}", headers=reader))
    assert (state["state"], state["payment_order_id"]) == ("ordered", order["id"])

    # Storno path: never while ordered; subledger only through the reversal of the result.
    withdraw = f"{C}/{row['id']}/withdraw"
    assert c.post(withdraw, json={"reason": "x"}, headers=approver).status_code == 422
    assert c.post(withdraw, json={"reason": "Fehler"}, headers=approver).status_code == 409
    _ok(c.post(f"/api/v1/banking/payment-orders/{order['id']}/cancel", headers=h))
    sub = c.post(withdraw, json={"reason": "Fehler"}, headers=approver)
    assert sub.status_code == 409
    assert "Ergebnisbuchung" in sub.json()["detail"]
    _ok(
        c.post(
            f"{A}/ledgers/{ctx['ledger']}/entries/{ctx['entry']}/reverse",
            json={"reason": "Korrektur der Abrechnung"},
            headers=h,
        ),
        201,
    )
    assert _ok(c.get(f"{C}/{row['id']}", headers=h))["state"] == "reversed"
    done = _ok(c.post(withdraw, json={"reason": "Abrechnung korrigiert"}, headers=approver))
    assert (done["status"], done["state"], done["withdraw_reason"]) == (
        "withdrawn",
        "withdrawn",
        "Abrechnung korrigiert",
    )
    assert c.post(withdraw, json={"reason": "erneut"}, headers=approver).status_code == 409
    assert [r["id"] for r in _ok(c.get(C, params={"status": "withdrawn"}, headers=h))] == [
        row["id"]
    ]
    assert _ok(c.get(C, headers=other)) == []


def test_ae22_reclass_draft_posting_and_reversal(
    clients: dict[str, TestClient], world: World, database: Database
) -> None:
    c, g3, g13 = clients["closed"], clients["g3"], clients["g13"]
    h = bearer(login(c, world, "ae22admin"))
    approver = bearer(login(c, world, "ae22approver"))
    ctx = _setup(c, h, approver, database, world.tenant_a, "222")
    _ok(c.put(f"{C}/settings", json={"mode": "reclass", "four_eyes_required": False}, headers=h))
    body = {
        "source_type": "rent_statement",
        "source_id": ctx["statement"],
        "contract_id": ctx["contract"],
    }
    unknown = c.post(
        C,
        json={"source_type": "deposit_settlement", "source_id": ctx["statement"]},
        headers=h,
    )
    assert unknown.status_code == 404
    row = _ok(c.post(C, json=body, headers=h), 201)
    assert row["variant"] == "reclass"
    gh = bearer(login(g3, world, "ae22admin"))
    release = f"{C}/{row['id']}/release"
    missing = g3.post(release, json={}, headers=gh)
    assert missing.status_code == 409
    assert "Kreditorenkonto" in missing.json()["detail"]
    creditor = _ok(
        c.post(
            f"{A}/ledgers/{ctx['ledger']}/accounts",
            json={
                "number": "070900",
                "name": "Verbindlichkeiten aus Guthaben",
                "category": "creditor",
                "type": "liability",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(c.put(f"{C}/settings", json={"creditor_account_number": "070900"}, headers=h))
    # Four eyes switched off: the proposer may release.
    released = _ok(g3.post(release, json={}, headers=gh))
    assert (released["state"], released["reclass_entry_status"]) == ("reclass_draft", "draft")
    draft = _ok(
        c.get(f"{A}/ledgers/{ctx['ledger']}/entries/{released['reclass_entry_id']}", headers=h)
    )
    assert draft["kind"] == "credit_reclass"
    lines = {(ln["account_id"], ln["debit"], ln["credit"]) for ln in draft["lines"]}
    assert lines == {(ctx["debtor"], "80.00", "0.00"), (creditor, "0.00", "80.00")}
    oh = bearer(login(clients["g23"], world, "ae22admin"))
    no_item = clients["g23"].post(
        f"{C}/{row['id']}/payment-order",
        json={
            "contact_bank_account_id": ctx["payee"],
            "property_bank_account_id": ctx["bank"],
            "execution_date": local_today().isoformat(),
        },
        headers=oh,
    )
    assert no_item.status_code == 409  # the reclass is not posted yet

    _ok(
        c.post(
            f"{A}/ledgers/{ctx['ledger']}/entries/{released['reclass_entry_id']}/post", headers=h
        )
    )
    posted = _ok(c.get(f"{C}/{row['id']}", headers=h))
    assert (posted["state"], posted["remaining"]) == ("open", "80.00")
    payable = next(i for i in _open_items(c, h, ctx["ledger"]) if i["id"] == posted["open_item_id"])
    assert payable["kind"] == "payable"
    debtor_items = [
        i
        for i in _open_items(c, h, ctx["ledger"])
        if i["kind"] == "receivable" and i.get("account_id") == ctx["debtor"]
    ]
    assert debtor_items == []  # no receivable from the debtor debit of the reclass

    # Storno: the posted reclass is reversed, only with G1.
    withdraw = f"{C}/{row['id']}/withdraw"
    closed = c.post(withdraw, json={"reason": "Verrechnung statt Auszahlung"}, headers=approver)
    assert closed.status_code == 403
    g1h = bearer(login(g13, world, "ae22approver"))
    done = _ok(g13.post(withdraw, json={"reason": "Verrechnung statt Auszahlung"}, headers=g1h))
    assert done["status"] == "withdrawn"
    assert done["reversal_entry_id"]
    assert done["remaining"] is None or done["remaining"] == "0.00"
    reversal = _ok(
        c.get(f"{A}/ledgers/{ctx['ledger']}/entries/{done['reversal_entry_id']}", headers=h)
    )
    assert reversal["kind"] == "reversal"
    # The credit can be proposed again after the withdrawal.
    again = _ok(c.post(C, json=body, headers=h), 201)
    assert again["id"] != row["id"]
    # A draft reclass is discarded by the withdrawal.
    _ok(g3.post(f"{C}/{again['id']}/release", json={}, headers=gh))
    discarded = _ok(c.post(f"{C}/{again['id']}/withdraw", json={"reason": "Entwurf"}, headers=h))
    assert (discarded["status"], discarded["reclass_entry_id"]) == ("withdrawn", None)


def test_gae05_reversal_cancels_open_payment_order(
    clients: dict[str, TestClient], world: World, database: Database
) -> None:
    """GAE-05: the reversal of the result entry cancels a not yet submitted payout order
    (status cancelled, nothing executed); an order handed to the bank blocks the reversal."""
    c, g3, g23 = clients["closed"], clients["g3"], clients["g23"]
    h = bearer(login(c, world, "ae22admin"))
    approver = bearer(login(c, world, "ae22approver"))
    ctx = _setup(c, h, approver, database, world.tenant_a, "223")
    _ok(c.put(f"{C}/settings", json={"mode": "subledger", "four_eyes_required": True}, headers=h))
    row = _ok(
        c.post(
            C,
            json={
                "source_type": "rent_statement",
                "source_id": ctx["statement"],
                "contract_id": ctx["contract"],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        g3.post(
            f"{C}/{row['id']}/release", json={}, headers=bearer(login(g3, world, "ae22approver"))
        )
    )
    oh = bearer(login(g23, world, "ae22admin"))
    order = _ok(
        g23.post(
            f"{C}/{row['id']}/payment-order",
            json={
                "contact_bank_account_id": ctx["payee"],
                "property_bank_account_id": ctx["bank"],
                "execution_date": local_today().isoformat(),
            },
            headers=oh,
        ),
        201,
    )
    reverse = f"{A}/ledgers/{ctx['ledger']}/entries/{ctx['entry']}/reverse"
    engine = create_engine(database.migrator_url)

    def set_status(status: str) -> None:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
            )
            conn.execute(
                text(
                    "UPDATE payment_order SET status = CAST(:s AS payment_order_status) "
                    "WHERE id = :id"
                ),
                {"s": status, "id": order["id"]},
            )

    try:
        set_status("submitted")
        handed = c.post(reverse, json={"reason": "Korrektur"}, headers=h)
        assert handed.status_code == 409
        assert "Bank" in handed.json()["detail"]
        set_status("draft")
        _ok(c.post(reverse, json={"reason": "Korrektur der Abrechnung"}, headers=h), 201)
    finally:
        engine.dispose()
    listed = _ok(c.get("/api/v1/banking/payment-orders", params={"status": "cancelled"}, headers=h))
    cancelled = next(o for o in listed if o["id"] == order["id"])
    assert cancelled.get("executed_amount") in (None, "0.00")
    assert _ok(c.get(f"{C}/{row['id']}", headers=h))["state"] == "reversed"


def test_gae07_delete_reclass_draft_refused(
    clients: dict[str, TestClient], world: World, database: Database
) -> None:
    """GAE-07: the reclass draft of a released payable is not deleted directly (409)."""
    c, g3 = clients["closed"], clients["g3"]
    h = bearer(login(c, world, "ae22admin"))
    approver = bearer(login(c, world, "ae22approver"))
    ctx = _setup(c, h, approver, database, world.tenant_a, "224")
    _ok(
        c.put(
            f"{C}/settings",
            json={
                "mode": "reclass",
                "four_eyes_required": False,
                "creditor_account_number": "070900",
            },
            headers=h,
        )
    )
    _creditor(c, h, ctx["ledger"])
    row = _ok(
        c.post(
            C,
            json={
                "source_type": "rent_statement",
                "source_id": ctx["statement"],
                "contract_id": ctx["contract"],
            },
            headers=h,
        ),
        201,
    )
    released = _ok(
        g3.post(f"{C}/{row['id']}/release", json={}, headers=bearer(login(g3, world, "ae22admin")))
    )
    url = f"{A}/ledgers/{ctx['ledger']}/entries/{released['reclass_entry_id']}"
    refused = c.delete(url, headers=h)
    assert refused.status_code == 409
    assert "withdraw" in refused.json()["detail"]
    assert _ok(c.get(url, headers=h))["status"] == "draft"
    state = _ok(c.get(f"{C}/{row['id']}", headers=h))
    assert (state["state"], state["reclass_entry_id"]) == (
        "reclass_draft",
        released["reclass_entry_id"],
    )
    assert c.delete(url, headers=bearer(login(c, world, "ae22reader"))).status_code == 403
    assert c.delete(url, headers=bearer(login(c, world, "ae22other"))).status_code == 404


def _creditor(c: TestClient, h: dict[str, str], ledger: str) -> str:
    return str(
        _ok(
            c.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={
                    "number": "070900",
                    "name": "Verbindlichkeiten aus Guthaben",
                    "category": "creditor",
                    "type": "liability",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def test_gae06_owner_statement_reclass_end_to_end(
    clients: dict[str, TestClient], world: World, database: Database
) -> None:
    """GAE-06: owner statement payout 2.643,00 (income 12.000,00 minus expenses 3.000,00 minus
    fee 357,00 minus payouts 6.000,00), variant reclass: release writes the draft 2.643,00
    debit 060900 / credit 070900, posting opens a payable of 2.643,00, the withdrawal (G1)
    reverses it."""
    c, g3, g13 = clients["closed"], clients["g3"], clients["g13"]
    h = bearer(login(c, world, "ae22admin"))
    approver = bearer(login(c, world, "ae22approver"))
    ctx = _setup(c, h, approver, database, world.tenant_a, "225")
    creditor = _creditor(c, h, ctx["ledger"])
    _ok(
        c.put(
            f"{C}/settings",
            json={
                "mode": "reclass",
                "four_eyes_required": False,
                "creditor_account_number": "070900",
                "owner_debit_account_number": "060900",
            },
            headers=h,
        )
    )
    snapshot = {
        "results": {
            "income": {"total": "12000.00"},
            "expenses": {"total": "3000.00"},
            "admin_fee": {"gross": "357.00"},
            "payouts": {"total": "6000.00"},
            "liquidity": {"free": "0.00"},
        }
    }
    import uuid as _uuid

    sid = str(_uuid.uuid4())
    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        conn.execute(
            text(
                "INSERT INTO owner_statement (id, tenant_id, ledger_id, legal_entity_id, "
                "property_id, kind, period_from, period_to, status, rule_version, snapshot) "
                "SELECT :id, :t, :l, :e, :p, e.enumlabel::owner_statement_kind, "
                "'2025-01-01', '2025-12-31', 'issued', 'gae06', CAST(:s AS jsonb) "
                "FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'owner_statement_kind' ORDER BY e.enumsortorder LIMIT 1"
            ),
            {
                "id": sid,
                "t": str(world.tenant_a),
                "l": ctx["ledger"],
                "e": ctx["entity"],
                "p": ctx["property"],
                "s": json.dumps(snapshot),
            },
        )
    engine.dispose()
    cands = _ok(c.get(f"{C}/candidates", params={"ledger_id": ctx["ledger"]}, headers=h))
    assert ("owner_statement", sid, "2643.00") in {
        (x["source_type"], x["source_id"], x["amount"]) for x in cands
    }
    row = _ok(c.post(C, json={"source_type": "owner_statement", "source_id": sid}, headers=h), 201)
    assert (row["variant"], row["amount"]) == ("reclass", "2643.00")
    released = _ok(
        g3.post(f"{C}/{row['id']}/release", json={}, headers=bearer(login(g3, world, "ae22admin")))
    )
    draft = _ok(
        c.get(f"{A}/ledgers/{ctx['ledger']}/entries/{released['reclass_entry_id']}", headers=h)
    )
    accounts = {
        a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ctx['ledger']}/accounts", headers=h))
    }
    assert {(ln["account_id"], ln["debit"], ln["credit"]) for ln in draft["lines"]} == {
        (accounts["060900"], "2643.00", "0.00"),
        (creditor, "0.00", "2643.00"),
    }
    _ok(
        c.post(
            f"{A}/ledgers/{ctx['ledger']}/entries/{released['reclass_entry_id']}/post", headers=h
        )
    )
    posted = _ok(c.get(f"{C}/{row['id']}", headers=h))
    assert (posted["state"], posted["remaining"]) == ("open", "2643.00")
    g1h = bearer(login(g13, world, "ae22approver"))
    done = _ok(
        g13.post(f"{C}/{row['id']}/withdraw", json={"reason": "Abrechnung korrigiert"}, headers=g1h)
    )
    assert done["status"] == "withdrawn"
    reversal = _ok(
        c.get(f"{A}/ledgers/{ctx['ledger']}/entries/{done['reversal_entry_id']}", headers=h)
    )
    assert reversal["kind"] == "reversal"
