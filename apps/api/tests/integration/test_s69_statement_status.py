"""S69-01 (6.9.3, E03): uniform status model for owner statements and reserve statements.

Owner statement (rental, empty ledger 2025): calculated, internally approved by a second
person, board_reviewed; resolved refused (WEG only); issued, due and posted behind G3;
posted only with a posted entry of the statement's ledger (100,00 bank to owner account).
Reserve statement (WEG 2025, reserve opening 1.000,00, no movements): taken from the
calculated Hausgeldabrechnung -> opening 1.000,00, closing 1.000,00; four eyes; issued only
after resolved; issued behind G4.
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
from tests.integration.test_m17_owner_statement import A, H, O, _account, _ok, _unit

pytestmark = pytest.mark.integration
R = "/api/v1/hoa/reserve-statements"


class OpenG3G4:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G3, ReleaseGate.G4)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"s69-{RUN}", name=f"S69 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"s69b-{RUN}", name=f"S69B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("s69admin", a, "tenant_admin"),
            ("s69acc", a, "accountant_no_banking"),
            ("s69clerk", a, "clerk_no_accounting"),
            ("s69badmin", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG3G4())) as open_,
    ):
        yield closed, open_


def _move(c: TestClient, h: dict[str, str], url: str, target: str, **kw: Any) -> Any:
    return c.post(f"{url}/transition", json={"target": target, **kw}, headers=h)


def test_owner_statement_status_model(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, gated = clients
    h = bearer(login(client, world, "s69admin"))
    acc = bearer(login(client, world, "s69acc"))
    clerk = bearer(login(client, world, "s69clerk"))
    other = bearer(login(client, world, "s69badmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "691", "name": "Miethaus S69", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(client, h, "VermieterS69", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    ledger = _ok(client.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)[
        "id"
    ]
    bank = _account(client, h, ledger, "001210", "Mietkonto", "bank", "asset")
    cost = _account(client, h, ledger, "040100", "Hausmeister", "cost", "expense")
    st = _ok(
        client.post(
            O,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    url = f"{O}/{st['id']}"
    _ok(client.post(f"{url}/calculate", headers=h))

    # Validation, rights, tenant separation.
    assert _move(client, acc, url, "unknown").status_code == 422
    assert _move(client, acc, url, "calculated").status_code == 422
    assert _move(client, clerk, url, "internally_approved").status_code == 403
    assert _move(client, other, url, "internally_approved").status_code == 404
    # Four eyes: the creator cannot approve; skipping the approval is refused.
    assert _move(client, h, url, "internally_approved").status_code == 403
    assert _move(client, acc, url, "board_reviewed").status_code == 409
    approved = _ok(_move(client, acc, url, "internally_approved", note="geprüft"))
    assert approved["status"] == "internally_approved"
    assert approved["status_log"][-1]["to"] == "internally_approved"
    assert approved["status_log"][-1]["note"] == "geprüft"
    assert client.post(f"{url}/calculate", headers=h).status_code == 409
    assert _ok(_move(client, h, url, "board_reviewed"))["status"] == "board_reviewed"
    # resolved is WEG only.
    assert _move(client, h, url, "resolved").status_code == 409
    # issued behind G3 (closed: 403 before anything else).
    closed = _move(client, h, url, "issued")
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    hg = bearer(login(gated, world, "s69admin"))
    assert _ok(_move(gated, hg, url, "issued"))["status"] == "issued"
    assert _move(gated, hg, url, "posted").status_code == 409  # only from due
    assert _ok(_move(gated, hg, url, "due"))["status"] == "due"
    # posted needs posted entries of this ledger.
    assert _move(gated, hg, url, "posted").status_code == 409
    body = {
        "kind": "custom",
        "booking_date": "2025-12-31",
        "text": "Test",
        "lines": [
            {"account_id": cost, "debit": "100.00"},
            {"account_id": bank, "credit": "100.00"},
        ],
    }
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    # A draft entry is no posting.
    assert _move(gated, hg, url, "posted", entry_ids=[draft["id"]]).status_code == 409
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    entry_ids = [draft["id"]]
    posted = _ok(_move(gated, hg, url, "posted", entry_ids=entry_ids[:1]))
    assert posted["status"] == "posted"
    assert posted["posted_entry_ids"] == entry_ids[:1]
    assert _ok(_move(gated, hg, url, "locked"))["status"] == "locked"
    assert _move(gated, hg, url, "due").status_code == 409
    # The PDF stays available after the approval (G3 open).
    assert gated.get(f"{url}/pdf", headers=hg).status_code == 200


def test_reserve_statement(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, gated = clients
    h = bearer(login(client, world, "s69admin"))
    acc = bearer(login(client, world, "s69acc"))
    clerk = bearer(login(client, world, "s69clerk"))
    other = bearer(login(client, world, "s69badmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "692", "name": "WEG S69", "management_type": "hoa"},
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
    hoa_st = _ok(
        client.post(
            f"{H}/statements",
            json={"ledger_id": ledger, "year": 2025, "reserve_opening": "1000.00"},
            headers=h,
        ),
        201,
    )
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    unit = _unit(client, h, prop["id"], "01")
    _ok(
        client.post(
            f"/api/v1/units/{unit}/allocation-values",
            json={"allocation_key_id": keys["MEA"], "value": "1000", "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    accounts = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    _ok(
        client.post(
            f"{H}/statements/{hoa_st['id']}/costs",
            json={
                "label": "Bewirtschaftungskosten",
                "amount": "300.00",
                "allocation_key_id": keys["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
                "account_id": accounts["043000"],
            },
            headers=h,
        ),
        201,
    )
    # Validation, rights, tenant separation.
    assert client.post(R, json={}, headers=h).status_code == 422
    assert client.post(R, json={"hoa_statement_id": hoa_st["id"]}, headers=clerk).status_code == 403
    assert client.post(R, json={"hoa_statement_id": hoa_st["id"]}, headers=other).status_code == 404
    rs = _ok(client.post(R, json={"hoa_statement_id": hoa_st["id"]}, headers=h), 201)
    url = f"{R}/{rs['id']}"
    assert rs["status"] == "draft"
    assert rs["year"] == 2025
    assert client.get(url, headers=other).status_code == 404
    assert _ok(client.get(R, headers=other)) == []
    # Not before the Hausgeldabrechnung is calculated.
    assert client.post(f"{url}/calculate", headers=h).status_code == 409
    hoa_calc = _ok(client.post(f"{H}/statements/{hoa_st['id']}/calculate", headers=h))
    calc = _ok(client.post(f"{url}/calculate", headers=h))
    assert calc["status"] == "calculated"
    assert calc["source_snapshot_hash"] == hoa_calc["snapshot_hash"]
    assert calc["snapshot"]["reserve"]["opening"] == "1000.00"
    assert calc["snapshot"]["reserve"]["closing"] == "1000.00"
    assert [x["id"] for x in _ok(client.get(R, params={"ledger_id": ledger}, headers=h))] == [
        rs["id"]
    ]
    # Four eyes and order.
    assert _move(client, h, url, "internally_approved").status_code == 403
    assert _move(client, acc, url, "resolved").status_code == 422  # no resolution
    assert _ok(_move(client, acc, url, "internally_approved"))["status"] == "internally_approved"
    assert client.post(f"{url}/calculate", headers=h).status_code == 409
    assert _ok(_move(client, h, url, "board_reviewed"))["status"] == "board_reviewed"
    # resolved needs a resolution; issued behind G4 and only after resolved (W06).
    assert _move(client, h, url, "resolved").status_code == 422
    closed = _move(client, h, url, "issued")
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    hg = bearer(login(gated, world, "s69admin"))
    assert _move(gated, hg, url, "issued").status_code == 409
    assert _ok(client.get(url, headers=h))["status"] == "board_reviewed"
