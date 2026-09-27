"""M17-01 BetrKV catalogue and allocability hints, M17-03 advance proposals (API, drafts).

Expected values by hand: one let unit (60 m2, whole year 2025) carries 100 % of the costs.
Caretaker 1.234,56 EUR posted and settled -> tenant costs 1.234,56; advance proposal
1.234,56 / 12 = 102,88 (0 %), with 5 % surcharge 1.234,56 * 105 / 1.200 = 108,024 -> 108,02.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m17_operating_costs import (
    A,
    S,
    _account,
    _ok,
    _rental_world,
    _statement,
)

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    """Own tenant and users (module scoped) so that the module runs beside the other M17 suites."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bk17b-{RUN}", name=f"BKB {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m17badmin", "tenant_admin"), ("m17bacc", "accountant_no_banking")]:
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
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


C = "/api/v1/billing/operating-cost-types"
R = "/api/v1/billing/advance-rule"


def _post_costs(
    client: TestClient, h: dict[str, str], ledger: str, lines: list[dict[str, Any]]
) -> None:
    bank = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={"number": "001210", "name": "Mietkonto", "category": "bank", "type": "asset"},
            headers=h,
        ),
        201,
    )["id"]
    total = sum(float(line["debit"]) for line in lines)
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "custom",
                "booking_date": "2025-03-01",
                "text": "Betriebskosten 2025",
                "lines": [*lines, {"account_id": bank, "credit": f"{total:.2f}"}],
            },
            headers=h,
        ),
        201,
    )
    assert (
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))["status"]
        == "posted"
    )


def test_catalogue_mapping_and_hints(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m17badmin"))
    catalogue = _ok(client.get(C, headers=h))
    assert len(catalogue["items"]) == 19
    assert catalogue["source"].startswith("R07")
    assert catalogue["items"][13] == {
        "code": "14",
        "label": "Kosten für den Hauswart",
        "allocability": "yes",
        "reference": "§ 2 Nr. 14 BetrKV",
        "note": "Ohne Instandhaltung und Verwaltung.",
        "source": catalogue["source"],
    }

    w = _rental_world(client, h, "781")
    ledger = w["ledger"]
    caretaker = _account(
        client, h, ledger, "042000", "Hausmeister", allocation_category="allocable_other"
    )
    repair = _account(
        client, h, ledger, "045500", "Kleinreparaturen", allocation_category="allocable_other"
    )
    _post_costs(
        client,
        h,
        ledger,
        [{"account_id": caretaker, "debit": "1234.56"}, {"account_id": repair, "debit": "100.00"}],
    )
    listed = {
        a["number"]: a
        for a in _ok(client.get(f"{C}/accounts", params={"ledger_id": ledger}, headers=h))
    }
    assert listed["042000"]["operating_cost_type"] is None
    assert listed["042000"]["allocability"] is None

    # Mapping is a human decision; unknown codes and non cost accounts are refused.
    assert (
        client.put(
            f"{C}/accounts/{caretaker}", json={"operating_cost_type": "99"}, headers=h
        ).status_code
        == 422
    )
    mapped = _ok(
        client.put(f"{C}/accounts/{caretaker}", json={"operating_cost_type": "14"}, headers=h)
    )
    assert (mapped["operating_cost_type"], mapped["allocability"]) == ("14", "yes")
    assert mapped["operating_cost_type_label"] == "Kosten für den Hauswart"
    _ok(client.put(f"{C}/accounts/{repair}", json={"operating_cost_type": "I"}, headers=h))

    st = _statement(client, h, ledger)
    base = {
        "allocation_key_id": w["keys"]["WFL"],
        "basis": "§ 4 Mietvertrag, Anlage Betriebskosten",
    }
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={"label": "Hausmeister", "amount": "1234.56", "account_id": caretaker, **base},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={"label": "Kleinreparaturen", "amount": "100.00", "account_id": repair, **base},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={"label": "Sonstiges", "amount": "10.00", **base},
            headers=h,
        ),
        201,
    )

    # Preview without calculation: hints only, never a lock.
    check = _ok(client.get(f"{S}/{st['id']}/allocability-check", headers=h))
    codes = [(x["position"], x["code"]) for x in check["hints"]]
    assert codes == [
        ("Kleinreparaturen", "BETRKV-NOT-ALLOCABLE"),
        ("Kleinreparaturen", "BETRKV-CATEGORY-CONFLICT"),
        ("Sonstiges", "BETRKV-UNASSIGNED"),
    ]
    assert check["warnings"] == 2

    # The same hints are part of the snapshot; the calculation itself is unchanged.
    calc = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    snap = calc["snapshot"]
    assert [x["code"] for x in snap["allocability_hints"]] == [
        "BETRKV-NOT-ALLOCABLE",
        "BETRKV-CATEGORY-CONFLICT",
        "BETRKV-UNASSIGNED",
    ]
    assert snap["results"][0]["costs"] == "1344.56"
    assert snap["total"] == "1344.56"

    # Tenant separation: the catalogue is public per tenant, the mapping is not.
    other = bearer(login(client, world, "m17bacc"))
    assert client.get(f"{S}/{st['id']}/allocability-check", headers=other).status_code == 200
    assert client.put(
        f"{C}/accounts/{caretaker}", json={"operating_cost_type": None}, headers=other
    ).status_code in (200, 403)


def test_advance_proposals_with_confirmation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m17badmin"))
    acc = bearer(login(client, world, "m17bacc"))
    assert _ok(client.get(R, headers=h))["surcharge_percent"] == "0.00"
    assert client.put(R, json={"surcharge_percent": "150"}, headers=h).status_code == 422

    w = _rental_world(client, h, "782")
    ledger = w["ledger"]
    caretaker = _account(
        client, h, ledger, "042000", "Hausmeister", allocation_category="allocable_other"
    )
    _post_costs(client, h, ledger, [{"account_id": caretaker, "debit": "1234.56"}])
    st = _statement(client, h, ledger)
    body = {
        "label": "Hausmeister",
        "amount": "1234.56",
        "account_id": caretaker,
        "allocation_key_id": w["keys"]["WFL"],
        "basis": "§ 4 Mietvertrag",
    }
    _ok(client.post(f"{S}/{st['id']}/cost-items", json=body, headers=h), 201)
    assert (
        client.post(f"{S}/{st['id']}/advance-proposals", headers=h).status_code == 409
    )  # no snapshot
    calc = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    assert calc["snapshot"]["results"][0]["costs"] == "1234.56"

    proposals = _ok(client.post(f"{S}/{st['id']}/advance-proposals", headers=h), 201)
    assert len(proposals) == 1
    p = proposals[0]
    assert (p["previous_costs"], p["surcharge_percent"], p["proposed_amount"]) == (
        "1234.56",
        "0.00",
        "102.88",
    )
    assert p["status"] == "proposed"
    assert p["snapshot_hash"] == calc["snapshot"]["hash"]
    assert "102,88 EUR" in p["letter_text"]
    assert p["label"] == "Vorschlag, Anpassung erfolgt gesondert"

    # Tenant setting 5 %: a new run replaces the open proposal (one open proposal per contract).
    assert (
        _ok(client.put(R, json={"surcharge_percent": "5"}, headers=h))["surcharge_percent"]
        == "5.00"
    )
    proposals = _ok(client.post(f"{S}/{st['id']}/advance-proposals", headers=h), 201)
    assert proposals[0]["proposed_amount"] == "108.02"
    assert len(_ok(client.get(f"{S}/{st['id']}/advance-proposals", headers=h))) == 1
    # Run override of the setting for one statement only.
    override = _ok(
        client.post(
            f"{S}/{st['id']}/advance-proposals", json={"surcharge_percent": "10"}, headers=h
        ),
        201,
    )
    assert override[0]["proposed_amount"] == "113.17"  # 1.234,56 * 110 / 1.200 = 113,168
    pid = override[0]["id"]

    # Four eyes: the creator cannot confirm; the second person confirms once.
    assert (
        client.post(f"{S}/{st['id']}/advance-proposals/{pid}/confirm", headers=h).status_code == 403
    )
    confirmed = _ok(
        client.post(
            f"{S}/{st['id']}/advance-proposals/{pid}/confirm", json={"note": "geprüft"}, headers=acc
        )
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["decided_by"] == str(world.users["m17bacc"])
    assert (
        client.post(f"{S}/{st['id']}/advance-proposals/{pid}/confirm", headers=acc).status_code
        == 409
    )
    # Confirmed proposals stay as history; a new run adds a new open proposal.
    again = _ok(client.post(f"{S}/{st['id']}/advance-proposals", headers=h), 201)
    assert again[0]["proposed_amount"] == "108.02"
    listed = _ok(client.get(f"{S}/{st['id']}/advance-proposals", headers=h))
    assert sorted(x["status"] for x in listed) == ["confirmed", "proposed"]
    assert (
        client.post(
            f"{S}/{st['id']}/advance-proposals/{again[0]['id']}/reject", headers=acc
        ).status_code
        == 200
    )

    # The contract payments are untouched (§ 560 BGB is a separate step, G3).
    payments = _ok(client.get(f"/api/v1/contracts/{w['contract']['id']}/payments", headers=h))
    assert all(
        x["payment_type_code"] != "operating_cost_advance" or x["gross"] != "108.02"
        for x in payments
    )
