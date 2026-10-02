"""AJ04 (GAI-105, GAI-307, GAI-601): domain events with old and new values for tax profiles,
section 35a markers, creditor ids, payment configuration and WEG financing; scope check on the
old liquidity route. Expected values by hand (rule 0.1.8): every write leaves exactly one event
of the listed type, the audit row holds the changed key with old and new value."""

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
from tests.integration.test_m10_ledger import A, _hoa_ledger, _ok

pytestmark = pytest.mark.integration

H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"4-aj04-{RUN}", name=f"AJ04 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"4-aj04b-{RUN}", name=f"AJ04b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aj04admin", a, "tenant_admin"),
            ("aj04reader", a, "read_only"),
            ("aj04other", b, "tenant_admin"),
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


def test_payment_config_and_creditor_events(
    client: TestClient, world: World, database: Database
) -> None:
    h = bearer(login(client, world, "aj04admin"))
    hr = bearer(login(client, world, "aj04reader"))
    t = world.tenant_a
    assert (
        client.put(
            f"{A}/payment-runs/settings", json={"weekly_preview_enabled": True}, headers=hr
        ).status_code
        == 403
    )
    _ok(client.put(f"{A}/payment-runs/settings", json={"weekly_preview_enabled": True}, headers=h))
    ev = _events(database, t, "payment_run_setting.updated")
    assert len(ev) == 1
    assert ev[0]["changes"]["weekly_preview_enabled"] == {"old": False, "new": True}

    cid = "DE98ZZZ09999999999"
    _ok(
        client.put(
            f"{A}/direct-debits/creditor-ids/tenant", json={"sepa_creditor_id": cid}, headers=h
        )
    )
    ev = _events(database, t, "creditor_id.tenant_updated")
    assert len(ev) == 1
    assert ev[0]["changes"]["sepa_creditor_id"] == {"old": None, "new": cid}

    ledger, _acc, _debtor = _hoa_ledger(client, h, "741")
    le = _ok(client.get(f"{A}/ledgers/{ledger}", headers=h))["legal_entity_id"]
    _ok(
        client.put(
            f"{A}/direct-debits/creditor-ids/legal-entities/{le}",
            json={"sepa_creditor_id": cid},
            headers=h,
        )
    )
    ev = _events(database, t, "creditor_id.updated")
    assert [str(e["entity_id"]) for e in ev] == [le]

    # GAI-601: the old liquidity route answers and stays tenant bound.
    _ok(client.get(f"{A}/ledgers/{ledger}/liquidity", headers=h))
    ho = bearer(login(client, world, "aj04other"))
    assert client.get(f"{A}/ledgers/{ledger}/liquidity", headers=ho).status_code == 404


def test_tax_profile_events(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "aj04admin"))
    t = world.tenant_a
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "742", "name": "Steuerhaus 742", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    url = f"{A}/tax/properties/{prop['id']}/profile"
    _ok(client.put(url, json={"vat_opted": True, "revenue_key_percent": "40.00"}, headers=h))
    _ok(client.put(url, json={"vat_opted": False, "revenue_key_percent": "40.00"}, headers=h))
    ev = _events(database, t, "property_tax_profile.updated")
    assert len(ev) == 2
    assert ev[0]["changes"]["vat_opted"] == {"old": None, "new": True}
    assert ev[1]["changes"] == {"vat_opted": {"old": True, "new": False}}


def test_hoa_finance_events(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "aj04admin"))
    t = world.tenant_a
    ledger, _acc, _debtor = _hoa_ledger(client, h, "743")
    measure = _ok(
        client.post(
            f"{H}/measures",
            json={"ledger_id": ledger, "title": "Dach", "cost_frame": "1000.00"},
            headers=h,
        ),
        201,
    )
    _ok(client.patch(f"{H}/measures/{measure['id']}", json={"cost_frame": "1200.00"}, headers=h))
    created = _events(database, t, "hoa.measure.created")
    assert [str(e["entity_id"]) for e in created] == [measure["id"]]
    updated = _events(database, t, "hoa.measure.updated")
    change = updated[0]["changes"]["cost_frame"]
    assert "1000" in str(change["old"])
    assert "1200" in str(change["new"])
    claim = _ok(
        client.post(
            f"{H}/insurance-claims",
            json={"ledger_id": ledger, "title": "Wasserschaden", "damage_date": "2025-03-02"},
            headers=h,
        ),
        201,
    )
    assert [str(e["entity_id"]) for e in _events(database, t, "hoa.insurance_claim.created")] == [
        claim["id"]
    ]
