"""AK02 (GAI-307): domain events with old and new values on the remaining money routes
(ledger accounts, journal entry drafts, advance rule, dunning blocks). Expected values by hand
(rule 0.1.8): every write leaves exactly one event of the listed type, the audit row holds the
changed key with old and new value; reader 403, foreign tenant 404."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _entry, _hoa_ledger, _line, _ok

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"4-ak02-{RUN}", name=f"AK02 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"4-ak02b-{RUN}", name=f"AK02b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ak02admin", a, "tenant_admin"),
            ("ak02reader", a, "read_only"),
            ("ak02other", b, "tenant_admin"),
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


def _events(database: Database, tenant: uuid.UUID, type_: str) -> list[dict[str, Any]]:
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            rows = conn.execute(
                text(
                    "SELECT e.entity_id, e.payload, a.changes FROM domain_event e "
                    "LEFT JOIN audit_log a ON a.event_id = e.id "
                    "WHERE e.tenant_id = :t AND e.type = :ty ORDER BY e.occurred_at"
                ),
                {"t": str(tenant), "ty": type_},
            ).all()
            return [{"entity_id": r[0], "payload": r[1], "changes": r[2]} for r in rows]
    finally:
        engine.dispose()


def test_ledger_account_events(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "ak02admin"))
    hr = bearer(login(client, world, "ak02reader"))
    ho = bearer(login(client, world, "ak02other"))
    t = world.tenant_a
    ledger, _acc, _debtor = _hoa_ledger(client, h, "751")
    body = {"number": "048751", "name": "Konto 751", "category": "tax", "type": "asset"}
    assert client.post(f"{A}/ledgers/{ledger}/accounts", json=body, headers=hr).status_code == 403
    assert client.post(f"{A}/ledgers/{ledger}/accounts", json=body, headers=ho).status_code == 404
    acc = _ok(client.post(f"{A}/ledgers/{ledger}/accounts", json=body, headers=h), 201)
    created = _events(database, t, "ledger_account.created")
    assert [str(e["entity_id"]) for e in created] == [acc["id"]]
    assert created[0]["changes"]["name"] == {"old": None, "new": "Konto 751"}

    url = f"{A}/ledgers/{ledger}/accounts/{acc['id']}"
    assert client.patch(url, json={"name": "X"}, headers=ho).status_code == 404
    assert client.patch(url, json={"name": ""}, headers=h).status_code == 422
    _ok(client.patch(url, json={"name": "Konto 751 neu"}, headers=h))
    updated = _events(database, t, "ledger_account.updated")
    assert updated[0]["changes"] == {"name": {"old": "Konto 751", "new": "Konto 751 neu"}}

    assert client.delete(url, headers=ho).status_code == 404
    assert client.delete(url, headers=h).status_code == 204
    deleted = _events(database, t, "ledger_account.deleted")
    assert [str(e["entity_id"]) for e in deleted] == [acc["id"]]
    assert deleted[0]["changes"]["name"]["old"] == "Konto 751 neu"


def test_journal_draft_events(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "ak02admin"))
    ho = bearer(login(client, world, "ak02other"))
    t = world.tenant_a
    ledger, acc, debtor = _hoa_ledger(client, h, "752")
    body = _entry("custom", "2026-01-05", [_line(debtor, "10"), _line(acc["060100"], "0", "10")])
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    assert [str(e["entity_id"]) for e in _events(database, t, "journal_entry.draft_created")] == [
        draft["id"]
    ]
    url = f"{A}/ledgers/{ledger}/entries/{draft['id']}"
    changed = {**body, "text": "Entwurf geändert"}
    assert client.put(url, json=changed, headers=ho).status_code == 404
    _ok(client.put(url, json=changed, headers=h))
    upd = _events(database, t, "journal_entry.draft_updated")
    assert len(upd) == 1
    assert upd[0]["changes"]["text"] == {"old": body["text"], "new": "Entwurf geändert"}
    assert client.delete(url, headers=ho).status_code == 404
    assert client.delete(url, headers=h).status_code == 204
    gone = _events(database, t, "journal_entry.draft_deleted")
    assert [str(e["entity_id"]) for e in gone] == [draft["id"]]
    assert gone[0]["changes"]["text"]["old"] == "Entwurf geändert"


def test_advance_rule_event(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "ak02admin"))
    hr = bearer(login(client, world, "ak02reader"))
    url = "/api/v1/billing/advance-rule"
    current = _ok(client.get(url, headers=h))
    other = next(m for m in current["open_advance_modes"] if m != current["open_advance_mode"])
    assert client.put(url, json={"open_advance_mode": other}, headers=hr).status_code == 403
    assert client.put(url, json={"open_advance_mode": "nope"}, headers=h).status_code == 422
    _ok(client.put(url, json={"open_advance_mode": other}, headers=h))
    ev = _events(database, world.tenant_a, "advance_rule.updated")
    assert len(ev) == 1
    assert ev[0]["changes"]["open_advance_mode"] == {
        "old": current["open_advance_mode"],
        "new": other,
    }


def test_dunning_block_routes_tenant_bound(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ak02admin"))
    hr = bearer(login(client, world, "ak02reader"))
    unknown = uuid.uuid4()
    body = {"reason_code": "disputed"}
    assert (
        client.post(f"{A}/open-items/{unknown}/dunning-blocks", json=body, headers=hr).status_code
        == 403
    )
    assert (
        client.post(f"{A}/open-items/{unknown}/dunning-blocks", json=body, headers=h).status_code
        == 404
    )
    assert client.post(f"{A}/dunning-blocks/{unknown}/release", headers=h).status_code == 404
