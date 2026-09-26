"""M24 WEG plan and statement. Expected values by hand (annex D), year 2025:
MEA 3.000 / 2.500, costs 5.500,00 -> 3.000,00 / 2.500,00. Both units: resolved hoa_fee
advances 2.800,00, paid 2.500,00.
D01 unit 01: result 200,00, arrears 300,00, information 500,00 (no new 500,00 claim).
D02 unit 02: result -300,00, arrears 300,00 separate.
D03 reserve: opening 20.000,00 + paid 4.500,00 - withdrawals 3.000,00 + interest 100,00 =
21.600,00; open contributions 1.500,00 (resolved 6.000,00) not added."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
H = "/api/v1/hoa"


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
        a, _ = await services.provision_tenant(factory, slug=f"weg24-{RUN}", name=f"WEG {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("m24admin", "m24second"):
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


def _book_cost(
    c: TestClient, h: dict[str, str], ledger: str, bank: str, cost: str, amount: str, day: str
) -> None:
    """Posted cost payment bank -> cost account, so that the W04 reconciliation of the
    statement year closes (costs distributed must be costs booked, A60)."""
    draft = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "custom",
                "booking_date": day,
                "text": "Bewirtschaftungskosten",
                "lines": [
                    {"account_id": cost, "debit": amount},
                    {"account_id": bank, "credit": amount},
                ],
            },
            headers=h,
        ),
        201,
    )
    _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))


def _owner(
    c: TestClient, h: dict[str, str], prop: str, no: str, mea: str, key: str, pays: dict[str, str]
) -> tuple[str, dict[str, Any]]:
    unit = _unit(c, h, prop, no)
    _ok(
        c.post(
            f"/api/v1/units/{unit}/allocation-values",
            json={"allocation_key_id": key, "value": mea, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    party, _ = _party(c, h, f"Eigentuemer{no}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    for code, amount in pays.items():
        _ok(
            c.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": code,
                    "net": amount,
                    "gross": amount,
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": "2020-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    return unit, contract


def test_hoa_statement_d01_d03(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, gated = clients
    h = bearer(login(client, world, "m24admin"))
    h2 = bearer(login(client, world, "m24second"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "741", "name": "WEG Test", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    _, c1 = _owner(
        client,
        h,
        prop["id"],
        "01",
        "3000",
        keys["MEA"],
        {"hoa_fee": "2800.00", "reserve": "6000.00"},
    )
    _, c2 = _owner(client, h, prop["id"], "02", "2500", keys["MEA"], {"hoa_fee": "2800.00"})
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
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    # One posted month carries the whole resolved advance (test simplification, values from D).
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
    assert len(items) == 3
    for item in items:
        pay = {"2800.00": "2500.00", "6000.00": "4500.00"}[item["remaining"]]
        bank = acc["001201"] if item["remaining"] == "6000.00" else acc["001200"]
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "debtor_payment",
                    "booking_date": "2025-01-05",
                    "text": "Zahlung",
                    "lines": [
                        {"account_id": bank, "debit": pay},
                        {"account_id": item["account_id"], "credit": pay},
                    ],
                    "settlements": [{"open_item_id": item["id"], "amount": pay}],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    _book_cost(client, h, ledger, acc["001200"], acc["043000"], "5500.00", "2025-03-01")

    st = _ok(
        client.post(
            f"{H}/statements",
            json={
                "ledger_id": ledger,
                "year": 2025,
                "reserve_opening": "20000.00",
                "reserve_withdrawals": "3000.00",
                "reserve_interest": "100.00",
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
                "amount": "5500.00",
                "allocation_key_id": keys["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
                "account_id": acc["043000"],
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(client.post(f"{H}/statements/{st['id']}/calculate", headers=h))
    snap = calc["snapshot"]
    by = {u["unit_number"]: u for u in snap["units"]}
    d01, d02 = by["01"], by["02"]
    assert (d01["cost_share"], d01["advances_resolved"], d01["advances_paid"]) == (
        "3000.00",
        "2800.00",
        "2500.00",
    )
    assert (d01["result"], d01["arrears"], d01["information_total"]) == (
        "200.00",
        "300.00",
        "500.00",
    )
    assert (d02["cost_share"], d02["result"], d02["arrears"]) == ("2500.00", "-300.00", "300.00")
    assert d02["information_total"] == "0.00"
    periods = d01["ownership_periods"]
    assert [(p["from"], p["to"], p["days"]) for p in periods] == [("2025-01-01", "2025-12-31", 365)]
    reserve = snap["reserve"]
    assert reserve["closing"] == "21600.00"  # not 23.100,00
    assert reserve["contributions_open"] == "1500.00"
    assert reserve["contributions_resolved"] == "6000.00"

    # Resolution binding (W06): only a positive resolution on this exact snapshot.
    sid = st["id"]
    assert (
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h
        ).status_code
        == 403
    )
    package = _ok(client.get(f"{H}/statements/{sid}/package", headers=h))
    assert (package["blocking"], package["releasable"]) == ([], True)
    assert package["cost_items"][0]["key"]["code"] == "MEA"
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    wrong = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": hoa,
                "decided_on": "2026-05-10",
                "subject": "Abrechnung 2025",
                "wording": "Die Abrechnung 2025 wird genehmigt.",
                "status": "positive",
                "subject_type": "hoa_statement",
                "subject_id": sid,
                "snapshot_hash": "0" * 64,
            },
            headers=h,
        ),
        201,
    )
    assert (
        client.post(
            f"{H}/statements/{sid}/transition",
            json={"target": "resolved", "resolution_id": wrong["id"]},
            headers=h,
        ).status_code
        == 409
    )
    res = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": hoa,
                "decided_on": "2026-05-10",
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
    assert res["number"] == 2
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition",
            json={"target": "resolved", "resolution_id": res["id"]},
            headers=h,
        )
    )
    issue = {"target": "issued"}
    assert client.post(f"{H}/statements/{sid}/transition", json=issue, headers=h).status_code == 403
    gh = bearer(login(gated, world, "m24admin"))
    for target in ("issued", "due"):
        _ok(gated.post(f"{H}/statements/{sid}/transition", json={"target": target}, headers=gh))
    collection = _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))
    assert [r["number"] for r in collection] == [1, 2]

    # Posting needs G4 and only books the result, never the arrears again.
    assert client.post(f"{H}/statements/{sid}/post", headers=h).status_code == 403
    assert gated.post(f"{H}/statements/{sid}/post", headers=gh).status_code == 409  # no mapping
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "statement_result", "account_id": acc["060100"]},
            headers=h,
        )
    )
    posted = _ok(gated.post(f"{H}/statements/{sid}/post", headers=gh))
    assert posted["status"] == "posted"
    assert len(posted["posted_entry_ids"]) == 2
    again = _ok(gated.post(f"{H}/statements/{sid}/post", headers=gh))
    assert again["posted_entry_ids"] == posted["posted_entry_ids"]
    open_ = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-05-31"}, headers=h)
    )
    by_contract: dict[str, list[str]] = {}
    for i in open_:
        by_contract.setdefault(i["contract_id"], []).append(i["remaining"])
    assert sorted(by_contract[c1["id"]]) == ["1500.00", "200.00", "300.00"]  # not a new 500,00
    auditor = _party(client, h, "Beirat")[1]["id"]
    audit = _ok(
        client.post(
            f"{H}/audits",
            json={
                "legal_entity_id": hoa,
                "statement_id": sid,
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
                "purpose": "Prüfung Jahresabrechnung 2025",
                "auditor_contact_ids": [auditor],
            },
            headers=h,
        ),
        201,
    )
    assert audit["snapshot_hash"] == calc["snapshot_hash"]
    # 3 receivables + 3 payments + 1 cost payment (W04) in 2025, not the 2026 results
    assert audit["population"]["entries"] == 7
    aitem = _ok(
        client.post(
            f"{H}/audits/{audit['id']}/items",
            json={"journal_entry_id": posted["posted_entry_ids"][0], "amount": "200.00"},
            headers=h,
        ),
        201,
    )
    v2 = _ok(client.post(f"{H}/statements/{sid}/new-version", headers=h), 201)
    stale = client.patch(f"{H}/audit-items/{aitem['id']}", json={"status": "checked"}, headers=h)
    assert stale.status_code == 409  # new version outdates the audit item (6.9.12)
    assert v2["version"] == 2
    assert v2["resolution_id"] is None  # resolution stays with the resolved version

    # Economic plan 2026 (expected by hand): hoa_fee 5.500,00 -> 3.000,00 / 2.500,00, monthly
    # 250,00 / 208,33 (rounding difference 0,04 shown); reserve 1.200,00 -> 654,55 / 545,45
    # (remaining cent by largest remainder). Advances only after a resolution (W02, W06).
    plan = _ok(
        client.post(
            f"{H}/plans",
            json={"ledger_id": ledger, "year": 2026, "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    for component, amount in [("hoa_fee", "5500.00"), ("reserve", "1200.00")]:
        _ok(
            client.post(
                f"{H}/plans/{plan['id']}/items",
                json={
                    "label": component,
                    "component": component,
                    "amount": amount,
                    "allocation_key_id": keys["MEA"],
                },
                headers=h,
            ),
            201,
        )
    pc = _ok(client.post(f"{H}/plans/{plan['id']}/calculate", headers=h))
    pu = {u["unit_number"]: u for u in pc["snapshot"]["units"]}
    assert pu["01"]["annual"] == {"hoa_fee": "3000.00", "reserve": "654.55"}
    assert pu["02"]["annual"] == {"hoa_fee": "2500.00", "reserve": "545.45"}
    assert pu["02"]["monthly"]["hoa_fee"] == "208.33"
    assert pu["02"]["rounding_difference"]["hoa_fee"] == "0.04"
    assert plan["id"] in {
        x["id"] for x in _ok(client.get(f"{H}/plans", params={"ledger_id": ledger}, headers=h))
    }
    assert len(_ok(client.get(f"{H}/plans/{plan['id']}", headers=h))["items"]) == 2
    sts = _ok(client.get(f"{H}/statements", params={"ledger_id": ledger}, headers=h))
    assert {sid, v2["id"]} <= {x["id"] for x in sts}
    assert len(_ok(client.get(f"{H}/statements/{v2['id']}", headers=h))["cost_items"]) == 1
    assert client.post(f"{H}/plans/{plan['id']}/apply", headers=h).status_code == 409


# D18, D19, D54 (task list A18 to A20, 26.09.2026) ---------------------------------------------


def _hoa_ledger(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    """Own HOA property with default chart for one test; keys by code, accounts by number."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG {number}", "management_type": "hoa"},
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


def test_d18_sub_community_without_basis_blocks_release(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D18 (W03): a cost item allocated by a key that reaches only units 01 and 02 of three is a
    sub community. With a free filter as basis the package shows the finding and the internal
    approval is refused; with a resolution named as source the same split is releasable."""
    client, _ = clients
    h = bearer(login(client, world, "m24admin"))
    h2 = bearer(login(client, world, "m24second"))
    w = _hoa_ledger(client, h, "742")
    units = {
        no: _owner(client, h, w["property"], no, "1000", w["keys"]["MEA"], {})[0]
        for no in ("01", "02", "03")
    }
    haus_a = _ok(
        client.post(
            f"/api/v1/properties/{w['property']}/allocation-keys",
            json={"code": "HAUS_A", "name": "Haus A", "unit_of_measure": "MEA", "kind": "static"},
            headers=h,
        ),
        201,
    )["id"]
    for no in ("01", "02"):  # unit 03 is not part of Haus A
        _ok(
            client.post(
                f"/api/v1/units/{units[no]}/allocation-values",
                json={"allocation_key_id": haus_a, "value": "500", "valid_from": "2020-01-01"},
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
            "2000.00",
            f"{year}-02-01",
        )
        st = _ok(
            client.post(
                f"{H}/statements", json={"ledger_id": w["ledger"], "year": year}, headers=h
            ),
            201,
        )["id"]
        for label, key, item_basis in [
            ("Versicherung", w["keys"]["MEA"], "Gemeinschaftsordnung, Verteilung nach MEA"),
            ("Aufzug Haus A", haus_a, basis),
        ]:
            _ok(
                client.post(
                    f"{H}/statements/{st}/costs",
                    json={
                        "label": label,
                        "amount": "1000.00",
                        "allocation_key_id": key,
                        "basis": item_basis,
                        "account_id": w["acc"]["043000"],
                    },
                    headers=h,
                ),
                201,
            )
        calc = _ok(client.post(f"{H}/statements/{st}/calculate", headers=h))
        return st, calc["snapshot"]

    # Free filter: the split reaches two units, the basis names no source.
    sid, snap = statement(2025, "Filter Haus A")
    split = next(p for p in snap["positions"] if p["label"] == "Aufzug Haus A")["split"]
    assert sorted(split.values()) == ["500.00", "500.00"]
    assert units["03"] not in split
    package = _ok(client.get(f"{H}/statements/{sid}/package", headers=h))
    assert [f["code"] for f in package["blocking"]] == ["scope_unfounded"]
    assert "Aufzug Haus A" in package["blocking"][0]["detail"]
    assert "W03" in package["blocking"][0]["detail"]
    assert package["releasable"] is False
    blocked = client.post(
        f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
    )
    assert blocked.status_code == 409
    assert "belegte Grundlage" in blocked.json()["detail"]
    assert _ok(client.get(f"{H}/statements/{sid}", headers=h))["status"] == "calculated"

    # Same split with a documented source: no finding, approval possible.
    sid2, _ = statement(2024, "Beschluss Nr. 4 vom 12.05.2024: Aufzugskosten nur Haus A")
    package2 = _ok(client.get(f"{H}/statements/{sid2}/package", headers=h))
    assert (package2["blocking"], package2["releasable"]) == ([], True)
    approved = _ok(
        client.post(
            f"{H}/statements/{sid2}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    assert approved["status"] == "internally_approved"


def test_d19_reserve_contribution_unpaid_no_settlement_entry(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D19 (W08): resolved reserve contribution 6.000,00, paid 4.500,00 onto the reserve bank
    account, opening 10.000,00. Expected by hand: Soll 6.000,00, Ist 4.500,00, arrears 1.500,00,
    accounting closing 14.500,00, bank balance 4.500,00, difference -10.000,00 explained; the
    calculation writes no journal entry."""
    client, _ = clients
    h = bearer(login(client, world, "m24admin"))
    w = _hoa_ledger(client, h, "743")
    _, c1 = _owner(client, h, w["property"], "01", "1000", w["keys"]["MEA"], {"reserve": "6000.00"})
    _ok(
        client.put(
            f"{A}/ledgers/{w['ledger']}/payment-type-accounts",
            json={"payment_type_code": "reserve", "account_id": w["acc"]["060200"]},
            headers=h,
        )
    )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2025-01-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    item = _ok(
        client.get(
            f"{A}/ledgers/{w['ledger']}/open-items", params={"as_of": "2025-01-31"}, headers=h
        )
    )[0]
    assert item["remaining"] == "6000.00"
    draft = _ok(
        client.post(
            f"{A}/ledgers/{w['ledger']}/entries",
            json={
                "kind": "debtor_payment",
                "booking_date": "2025-02-05",
                "text": "Rücklage Teilzahlung",
                "lines": [
                    {"account_id": w["acc"]["001201"], "debit": "4500.00"},
                    {"account_id": item["account_id"], "credit": "4500.00"},
                ],
                "settlements": [{"open_item_id": item["id"], "amount": "4500.00"}],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{w['ledger']}/entries/{draft['id']}/post", headers=h))
    _book_cost(
        client, h, w["ledger"], w["acc"]["001200"], w["acc"]["043000"], "100.00", "2025-02-01"
    )
    before = _ok(client.get(f"{A}/ledgers/{w['ledger']}/entries", headers=h))
    st = _ok(
        client.post(
            f"{H}/statements",
            json={"ledger_id": w["ledger"], "year": 2025, "reserve_opening": "10000.00"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"{H}/statements/{st}/costs",
            json={
                "label": "Versicherung",
                "amount": "100.00",
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Gemeinschaftsordnung",
                "account_id": w["acc"]["043000"],
            },
            headers=h,
        ),
        201,
    )
    snap = _ok(client.post(f"{H}/statements/{st}/calculate", headers=h))["snapshot"]
    reserve = snap["reserve"]
    assert (
        reserve["contributions_resolved"],
        reserve["contributions_paid"],
        reserve["contributions_open"],
    ) == ("6000.00", "4500.00", "1500.00")
    assert (reserve["closing"], reserve["bank_balance"], reserve["bank_difference"]) == (
        "14500.00",
        "4500.00",
        "-10000.00",
    )
    assert "keine Ausgleichsbuchung" in reserve["bank_difference_note"]
    assert snap["asset_report"]["legal_minimum"]["reserve_closing"] == "14500.00"
    unit = snap["units"][0]
    assert (unit["reserve_due"], unit["reserve_paid"]) == ("6000.00", "4500.00")
    after = _ok(client.get(f"{A}/ledgers/{w['ledger']}/entries", headers=h))
    assert len(after) == len(before)  # the difference is explained, never posted away
    package = _ok(client.get(f"{H}/statements/{st}/package", headers=h))
    assert package["reserve"]["bank_balance"] == "4500.00"


def test_d54_contested_resolution_blocks_posting_and_reverses_nothing(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D54: a contest recorded on the resolution locks the result posting until the resolution
    is final; validity state and follow up steps are shown apart; a contest recorded after the
    posting leaves the posted entries and the statement untouched."""
    client, gated = clients
    h = bearer(login(client, world, "m24admin"))
    h2 = bearer(login(client, world, "m24second"))
    gh = bearer(login(gated, world, "m24admin"))
    w = _hoa_ledger(client, h, "744")
    _, c1 = _owner(client, h, w["property"], "01", "1000", w["keys"]["MEA"], {"hoa_fee": "1200.00"})
    for code in ("hoa_fee", "statement_result"):
        _ok(
            client.put(
                f"{A}/ledgers/{w['ledger']}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": w["acc"]["060100"]},
                headers=h,
            )
        )
    run = _ok(  # one posted month carries the resolved advance and creates the debtor account
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2025-01-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    _book_cost(
        client, h, w["ledger"], w["acc"]["001200"], w["acc"]["043000"], "1500.00", "2025-02-01"
    )
    sid = _ok(
        client.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2025}, headers=h),
        201,
    )["id"]
    _ok(
        client.post(
            f"{H}/statements/{sid}/costs",
            json={
                "label": "Bewirtschaftung",
                "amount": "1500.00",
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Gemeinschaftsordnung",
                "account_id": w["acc"]["043000"],
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(client.post(f"{H}/statements/{sid}/calculate", headers=h))
    unit = calc["snapshot"]["units"][0]
    assert (unit["result"], unit["arrears"]) == ("300.00", "1200.00")  # 1.500,00 - 1.200,00
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    rid = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2026-05-10",
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
    )["id"]
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition",
            json={"target": "resolved", "resolution_id": rid},
            headers=h,
        )
    )
    for target in ("issued", "due"):
        _ok(gated.post(f"{H}/statements/{sid}/transition", json={"target": target}, headers=gh))

    # Contest recorded: nothing is deleted, the posting is locked, state and steps are apart.
    _ok(client.patch(f"{H}/resolutions/{rid}", json={"status": "contested"}, headers=h))
    package = _ok(client.get(f"{H}/statements/{sid}/package", headers=h))
    validity = package["resolution"]["validity"]
    assert package["resolution"]["status"] == "contested"
    assert validity["state"].startswith("angefochten")
    assert validity["posting_allowed"] is False
    assert "keine automatische Stornierung" in validity["follow_up"]
    locked = gated.post(f"{H}/statements/{sid}/post", headers=gh)
    assert locked.status_code == 409
    assert "D54" in locked.json()["detail"]
    st = _ok(client.get(f"{H}/statements/{sid}", headers=h))
    assert (st["status"], st["resolution_id"], st["posted_entry_ids"]) == ("due", rid, [])
    collection = _ok(
        client.get(f"{H}/resolutions", params={"legal_entity_id": w["hoa"]}, headers=h)
    )
    assert [(r["id"], r["status"]) for r in collection] == [(rid, "contested")]

    # Final resolution: posting possible; a later contest reverses nothing automatically.
    _ok(client.patch(f"{H}/resolutions/{rid}", json={"status": "final"}, headers=h))
    posted = _ok(gated.post(f"{H}/statements/{sid}/post", headers=gh))
    assert posted["status"] == "posted"
    assert len(posted["posted_entry_ids"]) == 1
    _ok(client.patch(f"{H}/resolutions/{rid}", json={"status": "contested"}, headers=h))
    again = _ok(gated.post(f"{H}/statements/{sid}/post", headers=gh))
    assert (again["status"], again["posted_entry_ids"]) == ("posted", posted["posted_entry_ids"])
    entries = _ok(client.get(f"{A}/ledgers/{w['ledger']}/entries", headers=h))
    result_entries = [e for e in entries if e["id"] in posted["posted_entry_ids"]]
    assert [e["status"] for e in result_entries] == ["posted"]
    assert len(entries) == len(
        _ok(client.get(f"{A}/ledgers/{w['ledger']}/entries", headers=h))
    )  # no reversal entry appeared
    package = _ok(client.get(f"{H}/statements/{sid}/package", headers=h))
    assert package["resolution"]["validity"]["posting_allowed"] is False
    assert package["statement"]["status"] == "posted"


def test_check_transition_messages_carry_the_rule_id() -> None:
    """Refusals of check_transition name the violated rule; behaviour is unchanged (D13, 6.9.3)."""
    from mhvp.billing.status import StatementStatus as S
    from mhvp.billing.status import TransitionError, check_transition

    for current in (S.CALCULATED, S.INTERNALLY_APPROVED, S.RESOLVED, S.ISSUED):
        with pytest.raises(TransitionError, match=r"not allowed \(D13, 6.9.3\)"):
            check_transition(current, S.POSTED, is_hoa=True)
    with pytest.raises(TransitionError, match=r"not allowed \(6.9.3\)"):
        check_transition(S.ISSUED, S.POSTED, is_hoa=False)
    with pytest.raises(TransitionError, match=r"not allowed \(6.9.3\)"):
        check_transition(S.CALCULATED, S.DRAFT, is_hoa=True)
    with pytest.raises(TransitionError, match=r"\(W06\)"):
        check_transition(S.INTERNALLY_APPROVED, S.ISSUED, is_hoa=True)
    with pytest.raises(TransitionError, match=r"\(D14\)"):
        check_transition(S.BOARD_REVIEWED, S.RESOLVED, is_hoa=True)
    with pytest.raises(TransitionError, match=r"\(D13\)"):
        check_transition(S.DUE, S.POSTED, is_hoa=True, resolution_status="contested")
    with pytest.raises(TransitionError, match=r"\(6.9.3\)"):
        check_transition(S.INTERNALLY_APPROVED, S.RESOLVED, is_hoa=False)
    check_transition(S.DUE, S.POSTED, is_hoa=True, resolution_status="final")


def test_d14_statement_version_diff(clients: tuple[TestClient, TestClient], world: World) -> None:
    """D14 version comparison: version 1 costs 5.500,00 (3.000,00 / 2.500,00 by MEA 3.000 /
    2.500), version 2 adds 100,00 -> 5.600,00: unit 01 = 3.054,55, unit 02 = 2.545,45; the
    difference per unit is +54,55 / +45,45 on cost share and result (advances unchanged).
    The endpoint compares only versions of the same community and year (422 otherwise)."""
    client, _ = clients
    h = bearer(login(client, world, "m24admin"))
    w = _hoa_ledger(client, h, "745")
    for no, mea in (("01", "3000"), ("02", "2500")):
        _owner(client, h, w["property"], no, mea, w["keys"]["MEA"], {})
    other = _hoa_ledger(client, h, "746")
    _owner(client, h, other["property"], "01", "1000", other["keys"]["MEA"], {})

    def statement(ledger: str, year: int, amount: str) -> dict[str, Any]:
        sid = _ok(
            client.post(f"{H}/statements", json={"ledger_id": ledger, "year": year}, headers=h),
            201,
        )["id"]
        _ok(
            client.post(
                f"{H}/statements/{sid}/costs",
                json={
                    "label": "Bewirtschaftung",
                    "amount": amount,
                    "allocation_key_id": w["keys"]["MEA"]
                    if ledger == w["ledger"]
                    else other["keys"]["MEA"],
                    "basis": "Gemeinschaftsordnung",
                },
                headers=h,
            ),
            201,
        )
        return cast(dict[str, Any], _ok(client.post(f"{H}/statements/{sid}/calculate", headers=h)))

    v1 = statement(w["ledger"], 2025, "5500.00")
    v2 = _ok(client.post(f"{H}/statements/{v1['id']}/new-version", headers=h), 201)
    _ok(
        client.post(
            f"{H}/statements/{v2['id']}/costs",
            json={
                "label": "Nachtrag",
                "amount": "100.00",
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
            },
            headers=h,
        ),
        201,
    )
    v2 = _ok(client.post(f"{H}/statements/{v2['id']}/calculate", headers=h))
    diff = _ok(
        client.get(f"{H}/statements/{v2['id']}/diff", params={"against": v1["id"]}, headers=h)
    )
    assert (diff["old"]["version"], diff["new"]["version"]) == (1, 2)
    assert diff["total_costs"] == {"old": "5500.00", "new": "5600.00", "difference": "100.00"}
    units = {u["unit_number"]: u for u in diff["units"]}
    assert units["01"]["cost_share"] == {"old": "3000.00", "new": "3054.55", "difference": "54.55"}
    assert units["02"]["cost_share"] == {"old": "2500.00", "new": "2545.45", "difference": "45.45"}
    assert units["01"]["result"]["difference"] == "54.55"
    assert units["02"]["result"]["difference"] == "45.45"
    assert units["01"]["advances_resolved"]["difference"] == "0.00"
    assert Decimal(units["01"]["cost_share"]["difference"]) + Decimal(
        units["02"]["cost_share"]["difference"]
    ) == Decimal("100.00")
    positions = {p["label"]: p for p in diff["positions"]}
    assert (positions["Bewirtschaftung"]["in_old"], positions["Bewirtschaftung"]["in_new"]) == (
        True,
        True,
    )
    assert positions["Bewirtschaftung"]["amount"]["difference"] == "0.00"
    assert (positions["Nachtrag"]["in_old"], positions["Nachtrag"]["in_new"]) == (False, True)
    assert positions["Nachtrag"]["amount"] == {"old": "0", "new": "100.00", "difference": "100.00"}
    assert positions["Nachtrag"]["split"]["01"]["new"] == "54.55"

    # Other community or other year: refused with 422; self comparison too.
    foreign = statement(other["ledger"], 2025, "1000.00")
    assert (
        client.get(
            f"{H}/statements/{v2['id']}/diff", params={"against": foreign["id"]}, headers=h
        ).status_code
        == 422
    )
    v_2024 = statement(w["ledger"], 2024, "5500.00")
    assert (
        client.get(
            f"{H}/statements/{v2['id']}/diff", params={"against": v_2024["id"]}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{H}/statements/{v2['id']}/diff", params={"against": v2["id"]}, headers=h
        ).status_code
        == 422
    )
