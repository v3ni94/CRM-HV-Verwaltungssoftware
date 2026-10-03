"""GAG-07 (GAE-06, AE22): deposit settlement with the reclass variant as one flow.

Expected values by hand (rule 0.1.8): tenancy 01.01.2025 to 30.06.2026, deposit payment
1.200,00 on 01.01.2025, offset 200,00 (damage) on 01.04.2026, settlement on 30.06.2026 without
interest: payout 1.200,00 - 200,00 = 1.000,00. Variant ``reclass``: the release of the payable
writes a draft 1.000,00 debit 090500 (deposit liability) / credit 070900 (creditor) in the ledger
of the owner entity (B01, legal entity of the debtor account, not the management company);
posting opens one payable of 1.000,00; the withdrawal reverses the posted entry (B03, G1) and
never edits or deletes it; the reversal mirrors the lines.

Gates: the settlement release and the payable release stay locked while G3 is closed (403
MHVP-GATE-0001); G3 is opened only by the injected test resolver, never for the tenant.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
C = "/api/v1/accounting/credit-payables"
DEPOSIT_IBAN = "DE02120300000000202051"


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
        a, _ = await services.provision_tenant(factory, slug=f"4-ah04-{RUN}", name=f"AH04 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"4-ah04b-{RUN}", name=f"AH04B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ah04admin", a, "tenant_admin"),
            ("ah04approver", a, "tenant_admin"),
            ("ah04reader", a, "read_only"),
            ("ah04other", b, "tenant_admin"),
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
            create_app(settings, release_gate_resolver=Gates(ReleaseGate.G1, ReleaseGate.G3))
        ) as g13,
    ):
        yield {"closed": closed, "g3": g3, "g13": g13}


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _setup(c: TestClient, h: dict[str, str], n: str) -> dict[str, Any]:
    """Rental property of an owner entity with a deposit account, ended tenancy, owner ledger
    with deposit liability and creditor account, cash deposit with payment and offset."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": n, "name": f"AH04 Haus {n}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )["id"]
    owner, _ = _party(c, h, f"AH04Vermieter{n}", "company")
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    bank = _ok(
        c.post(
            f"/api/v1/properties/{prop}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "deposit",
                "iban": DEPOSIT_IBAN,
                "holder": f"Kaution {n}",
                "valid_from": "2025-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    building = _ok(
        c.post(f"/api/v1/properties/{prop}/buildings", json={"name": "Haus"}, headers=h), 201
    )["id"]
    unit = _ok(
        c.post(
            f"/api/v1/properties/{prop}/units",
            json={"building_id": building, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    tenant_party, _ = _party(c, h, f"AH04Mieter{n}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant_party,
                "start_date": "2025-01-01",
                "end_date": "2026-06-30",
            },
            headers=h,
        ),
        201,
    )["id"]
    ledger = _ok(c.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)["id"]
    accounts = {}
    for number, name, category, kind in [
        ("090500", "Kautionsverbindlichkeit", "technical", "liability"),
        ("070900", "Verbindlichkeiten aus Guthaben", "creditor", "liability"),
    ]:
        accounts[number] = _ok(
            c.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={"number": number, "name": name, "category": category, "type": kind},
                headers=h,
            ),
            201,
        )["id"]
    deposit = _ok(
        c.post(
            f"/api/v1/contracts/{contract}/deposits",
            json={
                "kind": "cash",
                "amount_due": "1200.00",
                "valid_from": "2025-01-01",
                "property_bank_account_id": bank,
            },
            headers=h,
        ),
        201,
    )["id"]
    moves = f"/api/v1/deposits/{deposit}/movements"
    _ok(
        c.post(
            moves, json={"date": "2025-01-01", "amount": "1200.00", "kind": "payment"}, headers=h
        ),
        201,
    )
    _ok(
        c.post(
            moves,
            json={"date": "2026-04-01", "amount": "200.00", "kind": "offset", "reason": "Schaden"},
            headers=h,
        ),
        201,
    )
    return {
        "ledger": ledger,
        "entity": entity,
        "bank": bank,
        "contract": contract,
        "deposit": deposit,
        "accounts": accounts,
    }


def test_ah04_deposit_settlement_reclass_flow(clients: dict[str, TestClient], world: World) -> None:
    c, g3, g13 = clients["closed"], clients["g3"], clients["g13"]
    h = bearer(login(c, world, "ah04admin"))
    approver = bearer(login(c, world, "ah04approver"))
    reader = bearer(login(c, world, "ah04reader"))
    other = bearer(login(c, world, "ah04other"))
    ctx = _setup(c, h, "441")
    ledger = ctx["ledger"]

    # Settlement draft: 1.200,00 - 200,00 = 1.000,00, no interest.
    settlement = _ok(
        c.post(
            f"/api/v1/deposits/{ctx['deposit']}/settlements",
            json={"settlement_date": "2026-06-30", "interest_mode": "none"},
            headers=h,
        ),
        201,
    )
    assert (settlement["status"], settlement["payout_amount"]) == ("draft", "1000.00")
    sid = settlement["id"]
    # A draft is no candidate; G3 closed locks the settlement release.
    assert _ok(c.get(f"{C}/candidates", params={"ledger_id": ledger}, headers=h)) == []
    locked = c.post(f"/api/v1/deposit-settlements/{sid}/release", headers=h)
    assert locked.status_code == 403
    assert (locked.json()["code"], locked.json()["gate"]) == ("MHVP-GATE-0001", "G3")
    gh = bearer(login(g3, world, "ah04admin"))
    assert g3.post(f"/api/v1/deposit-settlements/{sid}/release", headers=other).status_code == 404
    # AK14 (GAI-410): four eyes, the creator of the draft cannot release it (409).
    own = g3.post(f"/api/v1/deposit-settlements/{sid}/release", headers=gh)
    assert (own.status_code, own.json()["code"]) == (409, "MHVP-CONTR-0002"), own.text
    g3_approver = bearer(login(g3, world, "ah04approver"))
    released_settlement = _ok(
        g3.post(f"/api/v1/deposit-settlements/{sid}/release", headers=g3_approver)
    )
    assert released_settlement["status"] == "released"

    # Candidate in the ledger of the owner entity (B01), invisible to the foreign tenant.
    cands = _ok(c.get(f"{C}/candidates", params={"ledger_id": ledger}, headers=reader))
    assert [
        (x["source_type"], x["source_id"], x["amount"], x["payout_reason"], x["ledger_id"])
        for x in cands
    ] == [("deposit_settlement", sid, "1000.00", "deposit_refund", ledger)]
    assert _ok(c.get(f"{C}/candidates", headers=other)) == []

    # Reclass variant, four eyes on; the debit account of the deposit refund is required.
    _ok(
        c.put(
            f"{C}/settings",
            json={"mode": "reclass", "creditor_account_number": "070900"},
            headers=h,
        )
    )
    body = {"source_type": "deposit_settlement", "source_id": sid, "contract_id": ctx["contract"]}
    assert c.post(C, json={**body, "contract_id": None}, headers=h).status_code == 404
    assert c.post(C, json=body, headers=reader).status_code == 403
    assert c.post(C, json={**body, "amount": "1000.01"}, headers=h).status_code in (409, 422)
    row = _ok(c.post(C, json=body, headers=h), 201)
    assert (row["variant"], row["amount"], row["payout_reason"], row["state"]) == (
        "reclass",
        "1000.00",
        "deposit_refund",
        "proposed",
    )
    assert row["ledger_id"] == ledger
    assert c.get(f"{C}/{row['id']}", headers=other).status_code == 404
    release = f"{C}/{row['id']}/release"
    closed = c.post(release, json={}, headers=approver)
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    gapprover = bearer(login(g3, world, "ah04approver"))
    missing = g3.post(release, json={}, headers=gapprover)
    assert missing.status_code == 409
    assert "Kautionsrückzahlung" in missing.json()["detail"]
    _ok(c.put(f"{C}/settings", json={"deposit_debit_account_number": "090500"}, headers=h))
    same = g3.post(release, json={}, headers=gh)
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    released = _ok(g3.post(release, json={}, headers=gapprover))
    assert (released["status"], released["state"], released["reclass_entry_status"]) == (
        "released",
        "reclass_draft",
        "draft",
    )
    assert g3.post(release, json={}, headers=gapprover).status_code == 409

    # The draft: 1.000,00 debit 090500 / credit 070900 in the owner ledger.
    entry_url = f"{A}/ledgers/{ledger}/entries/{released['reclass_entry_id']}"
    draft = _ok(c.get(entry_url, headers=h))
    assert (draft["kind"], draft["status"], draft["ledger_id"]) == (
        "credit_reclass",
        "draft",
        ledger,
    )
    assert {(ln["account_id"], ln["debit"], ln["credit"]) for ln in draft["lines"]} == {
        (ctx["accounts"]["090500"], "1000.00", "0.00"),
        (ctx["accounts"]["070900"], "0.00", "1000.00"),
    }
    assert c.delete(entry_url, headers=h).status_code == 409  # only through withdraw

    # Posting opens one payable of 1.000,00 on the creditor account.
    _ok(c.post(f"{entry_url}/post", headers=h))
    posted = _ok(c.get(f"{C}/{row['id']}", headers=reader))
    assert (posted["state"], posted["remaining"]) == ("open", "1000.00")
    items = _ok(
        c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2099-12-31"}, headers=h)
    )
    payable = next(i for i in items if i["id"] == posted["open_item_id"])
    assert (payable["kind"], payable["amount"]) == ("payable", "1000.00")
    # Posting again is idempotent: still one payable, no second entry.
    assert _ok(c.post(f"{entry_url}/post", headers=h))["status"] == "posted"
    items = _ok(
        c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2099-12-31"}, headers=h)
    )
    assert [i["id"] for i in items if i["kind"] == "payable"] == [posted["open_item_id"]]
    options = _ok(c.get(f"{C}/{row['id']}/payout-options", headers=reader))
    assert [b["id"] for b in options["bank_accounts"]] == [ctx["bank"]]  # segregated only

    # Storno: G1 closed locks the reversal; with G1 the posted entry is reversed, not edited.
    withdraw = f"{C}/{row['id']}/withdraw"
    locked_g1 = c.post(withdraw, json={"reason": "Kaution verrechnet"}, headers=approver)
    assert locked_g1.status_code == 403
    assert _ok(c.get(entry_url, headers=h))["status"] == "posted"
    g1h = bearer(login(g13, world, "ah04approver"))
    assert g13.post(withdraw, json={"reason": "x"}, headers=g1h).status_code == 422
    done = _ok(g13.post(withdraw, json={"reason": "Kaution verrechnet"}, headers=g1h))
    assert done["status"] == "withdrawn"
    assert done["remaining"] in (None, "0.00")
    original = _ok(c.get(entry_url, headers=h))
    assert original["status"] in ("posted", "reversed")
    assert {(ln["account_id"], ln["debit"], ln["credit"]) for ln in original["lines"]} == {
        (ctx["accounts"]["090500"], "1000.00", "0.00"),
        (ctx["accounts"]["070900"], "0.00", "1000.00"),
    }
    reversal = _ok(c.get(f"{A}/ledgers/{ledger}/entries/{done['reversal_entry_id']}", headers=h))
    assert reversal["kind"] == "reversal"
    assert {(ln["account_id"], ln["debit"], ln["credit"]) for ln in reversal["lines"]} == {
        (ctx["accounts"]["090500"], "0.00", "1000.00"),
        (ctx["accounts"]["070900"], "1000.00", "0.00"),
    }
    assert g13.post(withdraw, json={"reason": "erneut"}, headers=g1h).status_code == 409
    # After the withdrawal the released settlement is a candidate again; the settlement stays
    # released (no change of the source).
    again = _ok(c.get(f"{C}/candidates", params={"ledger_id": ledger}, headers=h))
    assert [(x["source_id"], x["amount"]) for x in again] == [(sid, "1000.00")]
    listed = _ok(c.get(f"/api/v1/deposits/{ctx['deposit']}/settlements", headers=h))
    assert [(s["id"], s["status"]) for s in listed] == [(sid, "released")]
