"""R14 money path review (7.1 B03, B08): regressions for the corrections of 01.10.2026.

Expected values are set by hand: a cost of 500,00 reversed in the same year contributes
nothing to the statement; a kept cost of 300,00 is taken once."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m24_hoa import (
    A,
    H,
    _hoa_ledger,
    _ok,
    _settings,
    clients,  # noqa: F401 (fixture)
)

pytestmark = pytest.mark.integration


async def _world_r14(settings: Any) -> World:
    # Own tenant and users: the module level world of test_m24_hoa cannot be provisioned twice
    # in one process (slug and e-mail addresses derive from the constant RUN).
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services
    from tests.integration.test_m2_platform import PASSWORD, RUN

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r14-{RUN}", name=f"R14 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("r14admin", "r14second"):
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
    return asyncio.run(_world_r14(_settings(database, redis_url)))


def _posted_cost(
    c: TestClient, h: dict[str, str], ledger: str, bank: str, cost: str, amount: str, day: str
) -> str:
    draft: dict[str, Any] = _ok(
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
    return str(draft["id"])


def test_costs_from_ledger_skips_reversed_pairs(
    clients: tuple[TestClient, TestClient],  # noqa: F811
    world: World,
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "r14admin"))
    w = _hoa_ledger(client, h, "781")
    bank, cost = w["acc"]["001200"], w["acc"]["043000"]
    kept = _posted_cost(client, h, w["ledger"], bank, cost, "300.00", "2025-02-01")
    wrong = _posted_cost(client, h, w["ledger"], bank, cost, "500.00", "2025-03-01")
    st = _ok(
        client.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2025}, headers=h),
        201,
    )["id"]
    body = {
        "account_id": cost,
        "allocation_key_id": w["keys"]["MEA"],
        "basis": "Gemeinschaftsordnung, MEA",
    }
    first = _ok(client.post(f"{H}/statements/{st}/costs/from-ledger", json=body, headers=h), 201)
    assert sorted(c["amount"] for c in first["created"]) == ["300.00", "500.00"]

    reversal = _ok(
        client.post(
            f"{A}/ledgers/{w['ledger']}/entries/{wrong}/reverse",
            json={"reason": "Doppelt erfasst", "booking_date": "2025-03-05"},
            headers=h,
        ),
        201,
    )
    again = _ok(client.post(f"{H}/statements/{st}/costs/from-ledger", json=body, headers=h), 201)
    assert again["created"] == []
    reasons = {str(s["journal_entry_id"]): s["reason"] for s in again["skipped"]}
    assert reasons[kept] == "already_taken"
    assert reasons[str(reversal["id"])] == "reverses_taken_entry"

    st2 = _ok(
        client.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2025}, headers=h),
        201,
    )["id"]
    fresh = _ok(client.post(f"{H}/statements/{st2}/costs/from-ledger", json=body, headers=h), 201)
    assert [c["amount"] for c in fresh["created"]] == ["300.00"]
    reasons = {str(s["journal_entry_id"]): s["reason"] for s in fresh["skipped"]}
    assert reasons[wrong] == "reversed"
    assert reasons[str(reversal["id"])] == "reversed"
