"""M24 WEG plan and statement. Expected values by hand (annex D), year 2025:
MEA 3.000 / 2.500, costs 5.500,00 -> 3.000,00 / 2.500,00. Both units: resolved hoa_fee
advances 2.800,00, paid 2.500,00.
D01 unit 01: result 200,00, arrears 300,00, information 500,00 (no new 500,00 claim).
D02 unit 02: result -300,00, arrears 300,00 separate.
D03 reserve: opening 20.000,00 + paid 4.500,00 - withdrawals 3.000,00 + interest 100,00 =
21.600,00; open contributions 1.500,00 (resolved 6.000,00) not added."""

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
    assert audit["population"]["entries"] == 6  # 3 receivables + 3 payments 2025, not 2026 results
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
    assert client.post(f"{H}/plans/{plan['id']}/apply", headers=h).status_code == 409
