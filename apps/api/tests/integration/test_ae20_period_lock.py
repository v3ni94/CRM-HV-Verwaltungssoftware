"""AE20 / P06-02: period lock per property and period. Fixed expected values (rule 0.1.8):
a lock of 01.04.2026 to 30.06.2026 refuses postings of lines of the property in that period
(MHVP-ACC-0030) only when the tenant switch ``object_period`` is on; release needs the switch,
a request and a second person; the row stays. Nothing here opens a gate."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.accounting import period_lock
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
L = f"{A}/period-locks"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae20-{RUN}", name=f"AE20 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae20b-{RUN}", name=f"AE20b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae20admin", a, "tenant_admin"),
            ("ae20acc", a, "accountant_no_banking"),
            ("ae20reader", a, "read_only"),
            ("ae20other", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _setup(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": "Sperrhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(c, h, prop["id"], "01")
    owner, _ = _party(c, h, "AE20Eig")
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": owner,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )
    accounts = {
        a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger['id']}/accounts", headers=h))
    }
    debtor = next(n for n in accounts if n.startswith("09") and n not in ("009000", "009999"))
    return {
        "property": prop["id"],
        "unit": unit,
        "ledger": ledger["id"],
        "debtor": accounts[debtor],
        "revenue": accounts["060100"],
    }


def _draft(c: TestClient, h: dict[str, str], w: dict[str, Any], day: str) -> dict[str, Any]:
    body = {
        "kind": "custom",
        "booking_date": day,
        "text": f"AE20 {day}",
        "lines": [
            {"account_id": w["debtor"], "debit": "5", "credit": "0", "unit_id": w["unit"]},
            {"account_id": w["revenue"], "debit": "0", "credit": "5", "unit_id": w["unit"]},
        ],
    }
    return _ok(c.post(f"{A}/ledgers/{w['ledger']}/entries", json=body, headers=h), 201)  # type: ignore[no-any-return]


def _post(c: TestClient, h: dict[str, str], w: dict[str, Any], entry: str) -> Any:
    return c.post(f"{A}/ledgers/{w['ledger']}/entries/{entry}/post", headers=h)


def test_object_period_lock_flow(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "ae20admin"))
    acc = bearer(login(client, world, "ae20acc"))
    reader = bearer(login(client, world, "ae20reader"))
    w = _setup(client, admin, "920")
    body = {
        "ledger_id": w["ledger"],
        "property_id": w["property"],
        "period_from": "2026-04-01",
        "period_to": "2026-06-30",
        "reason": "Abschluss Q2",
    }

    # Defaults are conservative.
    st = _ok(client.get(f"{L}/settings", headers=admin))
    assert (st["lock_mode"], st["auto_lock_on_close"], st["reopen_enabled"]) == (
        "ledger_only",
        False,
        False,
    )
    assert st["decision_open"] is True

    # Validation, rights.
    assert (
        client.post(L, json={**body, "period_from": "2026-07-01"}, headers=admin).status_code == 422
    )
    assert client.post(L, json=body, headers=reader).status_code == 403
    assert client.get(f"{L}?unknown=1", headers=admin).status_code == 422
    lock = _ok(client.post(L, json=body, headers=admin), 201)
    assert lock["active"] is True
    assert client.post(L, json=body, headers=admin).status_code == 409  # overlap

    # Mode ledger_only: the object lock does not restrict (existing behaviour).
    early = _draft(client, admin, w, "2026-05-10")
    assert _post(client, admin, w, early["id"]).status_code == 200

    # Switch on: posting into the locked period is refused, other periods are not.
    assert (
        client.put(f"{L}/settings", json={"lock_mode": "object_period"}, headers=reader).status_code
        == 403
    )
    assert client.put(f"{L}/settings", json={"lock_mode": "x"}, headers=admin).status_code == 422
    _ok(client.put(f"{L}/settings", json={"lock_mode": "object_period"}, headers=admin))
    blocked = _draft(client, admin, w, "2026-06-30")
    refused = _post(client, admin, w, blocked["id"])
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-ACC-0030"
    outside = _draft(client, admin, w, "2026-07-01")
    assert _post(client, admin, w, outside["id"]).status_code == 200

    # Reversal dated into the locked period is refused as well.
    rev = client.post(
        f"{A}/ledgers/{w['ledger']}/entries/{early['id']}/reverse",
        json={"reason": "Korrektur", "booking_date": "2026-05-20"},
        headers=admin,
    )
    assert rev.status_code == 409
    assert rev.json()["code"] == "MHVP-ACC-0030"

    # Release: needs the switch, a request and a second person.
    assert (
        client.post(
            f"{L}/{lock['id']}/release-request", json={"reason": "Fehler"}, headers=acc
        ).status_code
        == 409
    )
    _ok(client.put(f"{L}/settings", json={"reopen_enabled": True}, headers=admin))
    assert (
        client.post(
            f"{L}/{lock['id']}/release", json={"reason": "ok ok"}, headers=admin
        ).status_code
        == 409
    )
    _ok(
        client.post(
            f"{L}/{lock['id']}/release-request", json={"reason": "Erfassungsfehler"}, headers=acc
        )
    )
    same = client.post(f"{L}/{lock['id']}/release", json={"reason": "selbst"}, headers=acc)
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    released = _ok(
        client.post(f"{L}/{lock['id']}/release", json={"reason": "Freigabe"}, headers=admin)
    )
    assert released["active"] is False
    assert released["released_by"] == str(world.users["ae20admin"])
    assert _post(client, admin, w, blocked["id"]).status_code == 200
    listed = _ok(client.get(f"{L}?property_id={w['property']}&active=false", headers=admin))
    assert [r["id"] for r in listed] == [lock["id"]]  # the row stays

    # Tenant separation: foreign tenant sees nothing (404 on read).
    other = bearer(login(client, world, "ae20other"))
    assert client.get(f"{L}/{lock['id']}", headers=other).status_code == 404
    assert _ok(client.get(L, headers=other)) == []


def test_close_statement_sets_lock_only_with_switch(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    admin = bearer(login(client, world, "ae20admin"))
    w = _setup(client, admin, "921")
    settings = _settings(database, redis_url)
    sid = uuid.uuid4()
    args: dict[str, Any] = {
        "tenant_id": world.tenant_a,
        "user_id": world.users["ae20admin"],
        "source": "statement",
        "statement_id": sid,
        "ledger_id": uuid.UUID(w["ledger"]),
        "property_id": uuid.UUID(w["property"]),
        "period_from": date(2025, 1, 1),
        "period_to": date(2025, 12, 31),
    }

    async def run(auto: bool) -> list[dict[str, Any]]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            out = []
            async with tenant_transaction(factory, world.tenant_a) as session:
                await period_lock.update_setting(
                    session,
                    world.tenant_a,
                    None,
                    period_lock.PeriodLockSettingIn(auto_lock_on_close=auto),
                )
                out.append(await period_lock.lock_for_closed_statement(session, **args))
                out.append(await period_lock.lock_for_closed_statement(session, **args))
            return out
        finally:
            await engine.dispose()

    off = asyncio.run(run(False))
    assert off[0] == {"period_lock_proposed": True, "period_lock_id": None}
    on = asyncio.run(run(True))
    assert on[0]["period_lock_proposed"] is False
    assert on[0]["period_lock_id"] == on[1]["period_lock_id"]  # idempotent
    rows = _ok(client.get(f"{L}?property_id={w['property']}&active=true", headers=admin))
    assert [(r["source"], r["period_from"], r["period_to"]) for r in rows] == [
        ("statement", "2025-01-01", "2025-12-31")
    ]
