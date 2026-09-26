"""Annex D acceptance cases on the WEG statement that were only partially covered in
`docs/acceptance/PROTOKOLL-2026-09-26.md` (D02, D13, D14, D15) and D09 (heating bridge in the
cash flow reconciliation W04). Expected values are computed by hand in the docstring of each
test before the run (rule 0.1.8); nothing is derived from the observed result.

Model object (as D01 to D03): MEA 3.000 / 2.500, costs 5.500,00 -> 3.000,00 / 2.500,00,
both units resolved hoa_fee advances 2.800,00 (one posted month), paid 2.500,00.
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
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
from tests.integration.test_m24_hoa import _book_cost, _owner

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
H = "/api/v1/hoa"
DD = "/api/v1/accounting/direct-debits"


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
        a, _ = await services.provision_tenant(
            factory, slug=f"annexd-hoa-{RUN}", name=f"Anhang D WEG {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("adadmin", "adsecond"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _weg(
    client: TestClient, h: dict[str, str], number: str, *, cost: str = "5500.00"
) -> dict[str, Any]:
    """Model WEG of D01: two units, resolved advances 2.800,00 each (one posted month), paid
    2.500,00 each, costs `cost` paid from the bank in the statement year 2025."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG Anhang D {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    u1, c1 = _owner(client, h, prop["id"], "01", "3000", keys["MEA"], {"hoa_fee": "2800.00"})
    u2, c2 = _owner(client, h, prop["id"], "02", "2500", keys["MEA"], {"hoa_fee": "2800.00"})
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
    for code, account in [("hoa_fee", "060100"), ("statement_result", "060100")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[account]},
                headers=h,
            )
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
    assert sorted(i["remaining"] for i in items) == ["2800.00", "2800.00"]
    for item in items:
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "debtor_payment",
                    "booking_date": "2025-01-05",
                    "text": "Hausgeldzahlung",
                    "lines": [
                        {"account_id": acc["001200"], "debit": "2500.00"},
                        {"account_id": item["account_id"], "credit": "2500.00"},
                    ],
                    "settlements": [{"open_item_id": item["id"], "amount": "2500.00"}],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    if Decimal(cost) != 0:
        _book_cost(client, h, ledger, acc["001200"], acc["043000"], cost, "2025-03-01")
    return {
        "property": prop,
        "hoa": hoa,
        "keys": keys,
        "units": {"01": u1, "02": u2},
        "contracts": {"01": c1, "02": c2},
        "ledger": ledger,
        "acc": acc,
    }


def _statement(
    client: TestClient, h: dict[str, str], w: dict[str, Any], cost: str = "5500.00"
) -> dict[str, Any]:
    st = _ok(
        client.post(
            f"{H}/statements",
            json={
                "ledger_id": w["ledger"],
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
                "amount": cost,
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
                "account_id": w["acc"]["043000"],
            },
            headers=h,
        ),
        201,
    )
    return _ok(client.post(f"{H}/statements/{st['id']}/calculate", headers=h))  # type: ignore[no-any-return]


def _resolve(
    client: TestClient,
    h: dict[str, str],
    h2: dict[str, str],
    w: dict[str, Any],
    st: dict[str, Any],
    decided_on: str = "2026-05-10",
) -> dict[str, Any]:
    """Internal approval by a second person, positive resolution on this snapshot, resolved."""
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
                "decided_on": decided_on,
                "subject": "Abrechnung 2025",
                "wording": "Die Abrechnungsspitzen 2025 werden beschlossen.",
                "status": "positive",
                "subject_type": "hoa_statement",
                "subject_id": sid,
                "snapshot_hash": st["snapshot_hash"],
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
    return res  # type: ignore[no-any-return]


def _issue_due_post(gated: TestClient, gh: dict[str, str], sid: str) -> dict[str, Any]:
    for target in ("issued", "due"):
        _ok(gated.post(f"{H}/statements/{sid}/transition", json={"target": target}, headers=gh))
    return _ok(gated.post(f"{H}/statements/{sid}/post", headers=gh))  # type: ignore[no-any-return]


def _open_by_contract(
    client: TestClient, h: dict[str, str], ledger: str, as_of: str
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for i in _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": as_of}, headers=h)
    ):
        out.setdefault(i["contract_id"], []).append(i)
    return out


def test_d02_credit_result_is_neither_paid_out_nor_offset_against_arrears(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D02 unit 02: cost share 2.500,00; resolved advances 2.800,00; paid 2.500,00.
    Result = 2.500,00 - 2.800,00 = -300,00 (Anpassung); arrears = 2.800,00 - 2.500,00 = 300,00;
    information total = -300,00 + 300,00 = 0,00.
    After posting the resolved result: the arrears item stays open with 300,00 (not written
    off, not settled); the credit is a posting on the debtor account (balance 090001:
    +300,00 arrears - 300,00 credit = 0,00), it is no payable and no payment order; the
    ledger has no payable open item and no expected outflow; no payment order exists."""
    client, gated = clients
    h = bearer(login(client, world, "adadmin"))
    h2 = bearer(login(client, world, "adsecond"))
    gh = bearer(login(gated, world, "adadmin"))
    w = _weg(client, h, "902")
    st = _statement(client, h, w)
    by = {u["unit_number"]: u for u in st["snapshot"]["units"]}
    assert (by["02"]["result"], by["02"]["arrears"], by["02"]["information_total"]) == (
        "-300.00",
        "300.00",
        "0.00",
    )
    _resolve(client, h, h2, w, st)
    posted = _issue_due_post(gated, gh, st["id"])
    assert posted["status"] == "posted"
    assert len(posted["posted_entry_ids"]) == 2  # +200,00 unit 01 and -300,00 unit 02

    c2 = w["contracts"]["02"]["id"]
    open_ = _open_by_contract(client, h, w["ledger"], "2026-05-31")
    arrears = open_[c2]
    assert [(i["kind"], i["remaining"], i["amount"]) for i in arrears] == [
        ("receivable", "300.00", "2800.00")
    ]  # the old claim survives with its own legal basis (W05); no 300,00 payable
    all_items = _ok(
        client.get(
            f"{A}/ledgers/{w['ledger']}/open-items", params={"as_of": "2026-05-31"}, headers=h
        )
    )
    assert [i for i in all_items if i["kind"] == "payable"] == []
    tb = {
        a["number"]: a["balance"]
        for a in _ok(
            client.get(
                f"{A}/ledgers/{w['ledger']}/trial-balance",
                params={"as_of": "2026-05-31"},
                headers=h,
            )
        )["accounts"]
    }
    debtor2 = w["contracts"]["02"]["debtor_account"]["number"]
    assert Decimal(tb[debtor2]) == Decimal("0.00")  # rechnerisch 0,00, only as information
    liquidity = _ok(
        client.get(
            f"{A}/ledgers/{w['ledger']}/liquidity", params={"as_of": "2026-05-31"}, headers=h
        )
    )
    assert Decimal(liquidity["expected_outflows"]) == Decimal("0.00")
    assert _ok(client.get(f"{B}/payment-orders", headers=h)) == []  # no automatic payout
    # Posting again changes nothing (B08) and the credit entry carries the unit's contract.
    again = _ok(gated.post(f"{H}/statements/{st['id']}/post", headers=gh))
    assert again["posted_entry_ids"] == posted["posted_entry_ids"]


def test_d09_fuel_payment_and_consumption_differ_and_the_bridge_explains_it(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D09 model (rule status P02 open, see docs/OPEN_QUESTIONS.md): fuel paid 10.000,00 in
    the year; consumed and distributed 8.000,00; no other heating costs.
    Cash flow (W04): outflows 10.000,00 (cost category), cost_booked 10.000,00,
    cost_distributed 8.000,00; unexplained = 8.000,00 - 10.000,00 = -2.000,00 before the
    manager explains it; the package blocks (reconciliation_unexplained).
    With the note heating_accrual -2.000,00 (fuel stock carried into the next period):
    unexplained = 8.000,00 - 10.000,00 - (-2.000,00) = 0,00; outflows still 10.000,00, the
    2.000,00 stay visible as an explained line and are never netted away."""
    client, _ = clients
    h = bearer(login(client, world, "adadmin"))
    w = _weg(client, h, "909", cost="0.00")  # no other cost payment
    _book_cost(
        client, h, w["ledger"], w["acc"]["001200"], w["acc"]["041000"], "10000.00", "2025-02-10"
    )
    st = _ok(
        client.post(
            f"{H}/statements",
            json={
                "ledger_id": w["ledger"],
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
                "label": "Brennstoff verbraucht",
                "amount": "8000.00",
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA (Modellfall D09)",
                "account_id": w["acc"]["041000"],
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(client.post(f"{H}/statements/{st['id']}/calculate", headers=h))
    recon = calc["snapshot"]["reconciliation"]
    assert recon["cash"]["outflows"] == "10000.00"
    assert recon["outflows"] == {"cost": "10000.00"}
    assert (recon["cost_booked"], recon["cost_distributed"]) == ("10000.00", "8000.00")
    assert recon["unexplained"] == "-2000.00"
    bridge = {b["code"]: b["amount"] for b in recon["bridge"]}
    assert (bridge["outflows"], bridge["cost_paid"], bridge["cost_booked"]) == (
        "10000.00",
        "10000.00",
        "10000.00",
    )
    assert bridge["cost_distributed"] == "8000.00"
    package = _ok(client.get(f"{H}/statements/{st['id']}/package", headers=h))
    assert [f["code"] for f in package["blocking"]] == ["reconciliation_unexplained"]
    assert "-2000.00" in package["blocking"][0]["detail"]

    _ok(
        client.put(
            f"{H}/statements/{st['id']}/reconciliation-notes",
            json={
                "notes": [
                    {
                        "code": "heating_accrual",
                        "amount": "-2000.00",
                        "note": "Brennstoffbestand 31.12.2025, Zahlung 10.000,00 EUR, "
                        "Verbrauch 8.000,00 EUR (Modellfall D09).",
                    }
                ]
            },
            headers=h,
        )
    )
    package = _ok(client.get(f"{H}/statements/{st['id']}/package", headers=h))
    assert package["blocking"] == []
    live = package["reconciliation"]
    assert live["unexplained"] == "0.00"
    assert live["cash"]["outflows"] == "10000.00"  # the payment is not reduced to 8.000,00
    assert live["explained_manual"] == [
        {
            "code": "heating_accrual",
            "amount": "-2000.00",
            "note": "Brennstoffbestand 31.12.2025, Zahlung 10.000,00 EUR, "
            "Verbrauch 8.000,00 EUR (Modellfall D09).",
        }
    ]
    manual = [b for b in live["bridge"] if b.get("manual")]
    assert [(b["code"], b["amount"]) for b in manual] == [("heating_accrual", "-2000.00")]
    # An explanation with the wrong sign or amount does not close the bridge.
    _ok(
        client.put(
            f"{H}/statements/{st['id']}/reconciliation-notes",
            json={"notes": [{"code": "heating_accrual", "amount": "2000.00", "note": "falsch"}]},
            headers=h,
        )
    )
    package = _ok(client.get(f"{H}/statements/{st['id']}/package", headers=h))
    assert package["reconciliation"]["unexplained"] == "-4000.00"
    assert [f["code"] for f in package["blocking"]] == ["reconciliation_unexplained"]


def test_d13_no_resolution_means_no_result_claim_and_no_direct_debit(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D13: the result is confirmed internally (calculated, internally approved) but no
    resolution is recorded. Expected: posting the result is refused even with G4 open; the
    open items hold only the advance arrears (2 x 300,00 = 2.800,00 - 2.500,00), no 200,00
    result claim; the direct debit preview lists exactly these two 300,00 items (control sum
    600,00 for eligible items would need mandates, so here: candidates 2 x 300,00) and no
    result amount."""
    client, gated = clients
    h = bearer(login(client, world, "adadmin"))
    h2 = bearer(login(client, world, "adsecond"))
    gh = bearer(login(gated, world, "adadmin"))
    w = _weg(client, h, "913")
    st = _statement(client, h, w)
    sid = st["id"]
    by = {u["unit_number"]: u for u in st["snapshot"]["units"]}
    assert by["01"]["result"] == "200.00"

    # Calculated only: no posting.
    refused = gated.post(f"{H}/statements/{sid}/post", headers=gh)
    assert refused.status_code == 409, refused.text
    # Internally approved: still no resolution, no resolved status, no posting.
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    no_res = client.post(f"{H}/statements/{sid}/transition", json={"target": "resolved"}, headers=h)
    assert no_res.status_code == 422, no_res.text
    refused = gated.post(f"{H}/statements/{sid}/post", headers=gh)
    assert refused.status_code == 409, refused.text
    assert "not allowed" in refused.json()["detail"]
    for target in ("issued", "due"):
        assert (
            gated.post(
                f"{H}/statements/{sid}/transition", json={"target": target}, headers=gh
            ).status_code
            == 409
        )
    current = _ok(client.get(f"{H}/statements/{sid}", headers=h))
    assert (current["status"], current["resolution_id"]) == ("internally_approved", None)
    assert not current["posted_entry_ids"]

    # No claim from the statement in the ledger, none in a direct debit.
    items = _ok(
        client.get(
            f"{A}/ledgers/{w['ledger']}/open-items", params={"as_of": "2026-12-31"}, headers=h
        )
    )
    assert sorted(i["remaining"] for i in items) == ["300.00", "300.00"]
    assert {i["amount"] for i in items} == {"2800.00"}
    _ok(
        client.put(
            f"{DD}/creditor-ids/legal-entities/{w['hoa']}",
            json={"sepa_creditor_id": "DE98ZZZ09999999999"},
            headers=h,
        )
    )
    preview = _ok(
        client.post(
            f"{DD}/preview",
            json={"ledger_id": w["ledger"], "collection_date": "2026-12-31", "lead_days": 0},
            headers=h,
        )
    )
    assert sorted(c["amount"] for c in preview["items"]) == ["300.00", "300.00"]
    assert {c["open_item_id"] for c in preview["items"]} == {i["id"] for i in items}


def test_d14_new_result_version_after_resolution_keeps_the_resolution_on_the_old_one(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D14: version 1 (costs 5.500,00) is resolved. Version 2 adds 100,00 -> 5.600,00:
    unit 01 = 5.600,00 * 3.000 / 5.500 = 3.054,545... -> 3.054,55; unit 02 = 2.545,45;
    result 01 = 3.054,55 - 2.800,00 = 254,55 (difference to version 1: +54,55),
    result 02 = 2.545,45 - 2.800,00 = -254,55.
    Expected: version 2 has a different snapshot hash and no resolution; the resolution of
    version 1 cannot be attached to version 2 (409); version 1 keeps its resolution; the
    package of version 2 shows the unexplained difference to the booked costs (5.600,00 -
    5.500,00 = 100,00) and blocks the internal approval; nothing of version 2 is posted."""
    client, gated = clients
    h = bearer(login(client, world, "adadmin"))
    h2 = bearer(login(client, world, "adsecond"))
    gh = bearer(login(gated, world, "adadmin"))
    w = _weg(client, h, "914")
    v1 = _statement(client, h, w)
    res = _resolve(client, h, h2, w, v1)
    by1 = {u["unit_number"]: u for u in v1["snapshot"]["units"]}
    assert by1["01"]["result"] == "200.00"

    v2 = _ok(client.post(f"{H}/statements/{v1['id']}/new-version", headers=h), 201)
    assert (v2["version"], v2["supersedes_id"], v2["resolution_id"]) == (2, v1["id"], None)
    _ok(
        client.post(
            f"{H}/statements/{v2['id']}/costs",
            json={
                "label": "Nachtrag",
                "amount": "100.00",
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
                "account_id": w["acc"]["043000"],
            },
            headers=h,
        ),
        201,
    )
    v2 = _ok(client.post(f"{H}/statements/{v2['id']}/calculate", headers=h))
    by2 = {u["unit_number"]: u for u in v2["snapshot"]["units"]}
    assert (by2["01"]["cost_share"], by2["01"]["result"]) == ("3054.55", "254.55")
    assert (by2["02"]["cost_share"], by2["02"]["result"]) == ("2545.45", "-254.55")
    assert Decimal(by2["01"]["result"]) - Decimal(by1["01"]["result"]) == Decimal("54.55")
    assert v2["snapshot_hash"] != v1["snapshot_hash"]
    assert v2["resolution_id"] is None

    # The old resolution is not re-attached to the new numbers.
    moved = client.post(
        f"{H}/statements/{v2['id']}/transition",
        json={"target": "resolved", "resolution_id": res["id"]},
        headers=h,
    )
    assert moved.status_code == 409, moved.text
    package = _ok(client.get(f"{H}/statements/{v2['id']}/package", headers=h))
    assert package["resolution"] is None
    assert package["reconciliation"]["unexplained"] == "100.00"
    assert [f["code"] for f in package["blocking"]] == ["reconciliation_unexplained"]
    assert (
        client.post(
            f"{H}/statements/{v2['id']}/transition",
            json={"target": "internally_approved"},
            headers=h2,
        ).status_code
        == 409
    )
    assert gated.post(f"{H}/statements/{v2['id']}/post", headers=gh).status_code == 409
    old = _ok(client.get(f"{H}/statements/{v1['id']}", headers=h))
    assert (old["status"], old["resolution_id"], old["snapshot_hash"]) == (
        "resolved",
        res["id"],
        v1["snapshot_hash"],
    )
    listed = {
        s["version"]: s
        for s in _ok(client.get(f"{H}/statements", params={"ledger_id": w["ledger"]}, headers=h))
    }
    assert listed[1]["resolution_id"] == res["id"]
    assert listed[2]["resolution_id"] is None


def test_d15_owner_change_arrears_stay_with_seller_result_goes_to_owner_at_resolution(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D15 (ordinary purchase, no special liability; rule owner-at-resolution-v1, M24-01):
    seller owns unit 01 through 2025 with arrears 300,00 (2.800,00 - 2.500,00); title
    transfer to the buyer 01.04.2026; the statement 2025 is resolved on 10.05.2026.
    Expected: result 200,00 (3.000,00 - 2.800,00) is posted against the buyer's contract;
    the seller's contract keeps its open item 300,00 unchanged; the buyer's contract has
    exactly one open item 200,00; the snapshot shows the 2025 ownership period of the seller
    only (365 days). The purchase price settlement between buyer and seller is not a ledger
    entry (no entry with 200,00 or 300,00 on the seller after the transfer)."""
    client, gated = clients
    h = bearer(login(client, world, "adadmin"))
    h2 = bearer(login(client, world, "adsecond"))
    gh = bearer(login(gated, world, "adadmin"))
    w = _weg(client, h, "915")
    seller = w["contracts"]["01"]
    buyer_party, _ = _party(client, h, "KaeuferD15")
    buyer = _ok(
        client.post(
            f"/api/v1/contracts/{seller['id']}/ownership-transfer",
            json={
                "new_party_id": buyer_party,
                "title_transfer_date": "2026-04-01",
                "benefit_burden_date": "2026-04-01",
                "acquisition_kind": "purchase",
            },
            headers=h,
        ),
        201,
    )
    assert buyer["start_date"] == "2026-04-01"
    assert buyer["debtor_account"]["number"] != seller["debtor_account"]["number"]

    st = _statement(client, h, w)
    by = {u["unit_number"]: u for u in st["snapshot"]["units"]}
    assert (by["01"]["result"], by["01"]["arrears"]) == ("200.00", "300.00")
    periods = by["01"]["ownership_periods"]
    assert [(p["contract_id"], p["from"], p["to"], p["days"]) for p in periods] == [
        (seller["id"], "2025-01-01", "2025-12-31", 365)
    ]
    _resolve(client, h, h2, w, st, decided_on="2026-05-10")
    for target in ("issued", "due"):
        _ok(
            gated.post(f"{H}/statements/{st['id']}/transition", json={"target": target}, headers=gh)
        )
    # The buyer's debtor number reserved by the transfer is adopted into the existing ledger by
    # the statement posting itself (sync_debtor_accounts, like receivable runs); no explicit
    # sync-debtors call is needed (finding 26.09.2026, resolved).
    posted = _ok(gated.post(f"{H}/statements/{st['id']}/post", headers=gh))
    assert len(posted["posted_entry_ids"]) == 2

    entries = {
        e["contract_id"]: e
        for e in (
            _ok(client.get(f"{A}/ledgers/{w['ledger']}/entries/{eid}", headers=h))
            for eid in posted["posted_entry_ids"]
        )
    }
    assert buyer["id"] in entries
    assert seller["id"] not in entries
    assert entries[buyer["id"]]["booking_date"] == "2026-05-10"
    assert entries[buyer["id"]]["text"] == "Abrechnungsergebnis 2025 Einheit 01"
    open_ = _open_by_contract(client, h, w["ledger"], "2026-12-31")
    assert [(i["remaining"], i["due_date"]) for i in open_[seller["id"]]] == [
        ("300.00", "2025-01-03")
    ]
    assert [(i["remaining"], i["due_date"]) for i in open_[buyer["id"]]] == [
        ("200.00", "2026-05-10")
    ]
