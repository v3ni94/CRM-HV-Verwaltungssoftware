"""AL03 (GAI-307): domain events with old and new values on the remaining money routes
(statement and heating drafts, metering import, owner statement, chart template, debtor and
creditor sync, entry approval). Expected values by hand (rule 0.1.8): every write leaves
exactly one event of the listed type with the changed keys; reader 403, foreign tenant 404."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_ak02_money_events import _events
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _entry, _hoa_ledger, _line, _ok
from tests.integration.test_m17_heating import _setup

pytestmark = pytest.mark.integration

S = "/api/v1/statements"
P = "/api/v1/billing/heating-cost-imports"
OS = "/api/v1/billing/owner-statements"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"4-al03-{RUN}", name=f"AL03 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"4-al03b-{RUN}", name=f"AL03b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("al03admin", a, "tenant_admin"),
            ("al03admin2", a, "tenant_admin"),
            ("al03reader", a, "read_only"),
            ("al03other", b, "tenant_admin"),
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


def test_rental_statement_events(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "al03admin"))
    hr = bearer(login(client, world, "al03reader"))
    ho = bearer(login(client, world, "al03other"))
    t = world.tenant_a
    st_id, _contracts = _setup(client, h)
    st = _ok(client.get(f"{S}/{st_id}", headers=h))
    created = _events(database, t, "statement.created")
    assert [str(e["entity_id"]) for e in created] == [st_id]
    assert created[0]["changes"]["period_to"] == {"old": None, "new": "2025-12-31"}

    # Heating inputs: old and new total costs.
    hp = f"{S}/{st_id}/heating"
    body = {"total_costs": "3000.00", "settings": {}, "co2": {"building_kind": "unknown"}}
    assert client.put(hp, json=body, headers=hr).status_code == 403
    assert client.put(hp, json=body, headers=ho).status_code == 404
    _ok(client.put(hp, json=body, headers=h))
    heat = _events(database, t, "statement_heating.updated")
    assert len(heat) == 1
    assert heat[0]["changes"]["total_costs"]["new"] == "3000.00"

    # Metering import: create and header change.
    header = {
        "property_id": st["property_id"],
        "provider_name": "Messdienst AL03",
        "period_from": "2025-01-01",
        "period_to": "2025-12-31",
        "document_total": "2300.00",
    }
    assert client.post(P, json=header, headers=hr).status_code == 403
    imp = _ok(client.post(P, json=header, headers=h), 201)
    assert [str(e["entity_id"]) for e in _events(database, t, "heating_cost_import.created")] == [
        imp["id"]
    ]
    url = f"{P}/{imp['id']}"
    changed = {**header, "document_total": "2400.00"}
    assert client.put(url, json=changed, headers=ho).status_code == 404
    _ok(client.put(url, json=changed, headers=h))
    upd = _events(database, t, "heating_cost_import.updated")
    assert upd[0]["changes"]["document_total"] == {"old": "2300.00", "new": "2400.00"}

    # Owner statement: create and output options.
    ledger = st["ledger_id"]
    os_body = {"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"}
    assert client.post(OS, json=os_body, headers=hr).status_code == 403
    owner = _ok(client.post(OS, json=os_body, headers=h), 201)
    assert [str(e["entity_id"]) for e in _events(database, t, "owner_statement.created")] == [
        owner["id"]
    ]
    opt = f"{OS}/{owner['id']}/options"
    assert client.patch(opt, json={"attach_receipts": True}, headers=ho).status_code == 404
    _ok(client.patch(opt, json={"attach_receipts": True}, headers=h))
    opts = _events(database, t, "owner_statement.options_updated")
    assert opts[0]["changes"] == {"attach_receipts": {"old": False, "new": True}}

    # Debtor and creditor sync on the ledger.
    assert client.post(f"{A}/ledgers/{ledger}/sync-debtors", headers=ho).status_code == 404
    _ok(client.post(f"{A}/ledgers/{ledger}/sync-debtors", headers=h))
    assert len(_events(database, t, "ledger.debtors_synced")) == 1
    assert client.post(f"{A}/ledgers/{ledger}/sync-creditors", headers=hr).status_code == 403
    _ok(client.post(f"{A}/ledgers/{ledger}/sync-creditors", headers=h))
    assert len(_events(database, t, "ledger.creditors_synced")) == 1


def test_template_and_entry_approval_events(
    client: TestClient, world: World, database: Database
) -> None:
    h = bearer(login(client, world, "al03admin"))
    h2 = bearer(login(client, world, "al03admin2"))
    hr = bearer(login(client, world, "al03reader"))
    ho = bearer(login(client, world, "al03other"))
    t = world.tenant_a
    assert client.post(f"{A}/templates/default", headers=hr).status_code == 403
    tpl = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    saved = _events(database, t, "chart_template.default_saved")
    assert [str(e["entity_id"]) for e in saved] == [tpl["id"]]
    assert saved[0]["payload"]["account_count"] > 0

    ledger, acc, debtor = _hoa_ledger(client, h, "753")
    body = _entry("custom", "2026-01-05", [_line(debtor, "10"), _line(acc["060100"], "0", "10")])
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    url = f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve"
    assert client.post(url, headers=ho).status_code == 404
    assert client.post(url, headers=h).status_code == 403  # four eyes: creator refused
    assert _events(database, t, "journal_entry.approved") == []
    _ok(client.post(url, headers=h2))
    approved = _events(database, t, "journal_entry.approved")
    assert [str(e["entity_id"]) for e in approved] == [draft["id"]]
    assert approved[0]["changes"]["approved_by"] == {
        "old": None,
        "new": str(world.users["al03admin2"]),
    }
