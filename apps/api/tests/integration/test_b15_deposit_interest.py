# ruff: noqa: F811
"""Rule B15: rate history per deposit, yearly interest drafts, settlement mode deposit_rates;
B20: tenant policy for the second factor of the portal. Expected values are hand computed:
payment 1.200,00 on 01.01.2025, rate 1,00 % from 01.01.2025: 1.200 x 0,01 = 12,00 for 2025.
"""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _ok
from tests.integration.test_m5_deposit_settlement import (  # noqa: F401
    _deposit_with_address,
    _deposit_with_movements,
    _settings,
    client,
    s3,
)

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bz-{RUN}", name=f"Zins {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"by-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("bzadmin", a, "tenant_admin"),
            ("bzread", a, "read_only"),
            ("bzother", b, "tenant_admin"),
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


def test_rate_history_drafts_and_settlement(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "bzadmin"))
    reader = bearer(login(client, world, "bzread"))
    other = bearer(login(client, world, "bzother", tenant_id=world.tenant_b))
    deposit, _contract = _deposit_with_movements(client, h)
    rates = f"/api/v1/deposits/{deposit}/interest-rates"
    drafts = f"/api/v1/deposits/{deposit}/interest-drafts"

    # No rate yet: no draft (nothing is invented). Current year is refused as not completed.
    assert client.post(drafts, json={"year": 2025}, headers=h).status_code == 422
    # Authorization and tenant separation.
    assert client.put(f"{rates}/2025-01-01", json={"rate": "1"}, headers=reader).status_code == 403
    assert client.get(rates, headers=reader).status_code == 200
    assert client.get(rates, headers=other).status_code == 404
    assert client.put(f"{rates}/2025-01-01", json={"rate": "1"}, headers=other).status_code == 404
    # Validation.
    assert client.put(f"{rates}/2025-01-01", json={"rate": "101"}, headers=h).status_code == 422

    row = _ok(client.put(f"{rates}/2025-01-01", json={"rate": "1.0"}, headers=h), 200)
    assert row["rate"] == "1.00000"
    again = _ok(
        client.put(f"{rates}/2025-01-01", json={"rate": "1.0", "note": "Bank"}, headers=h), 200
    )
    assert again["id"] == row["id"]
    assert [r["valid_from"] for r in _ok(client.get(rates, headers=h), 200)] == ["2025-01-01"]

    # Draft 2025: 12,00, nothing booked yet (3 movements as before).
    draft = _ok(client.post(drafts, json={"year": 2025}, headers=h))
    assert (draft["year"], draft["amount"], draft["rate"], draft["days"]) == (
        2025,
        "12.00",
        "1.00000000",  # NUMERIC(20,8) since 0461 (GAL-102)
        365,
    )
    assert draft["status"] == "draft"
    assert (
        client.post(
            f"/api/v1/deposit-interest-drafts/{draft['id']}/confirm", headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/deposit-interest-drafts/{draft['id']}/confirm", headers=reader
        ).status_code
        == 403
    )
    # Recompute replaces the draft (same row); a rate change is picked up.
    _ok(client.put(f"{rates}/2025-07-01", json={"rate": "2.0"}, headers=h), 200)
    redo = _ok(client.post(drafts, json={"year": 2025}, headers=h))
    assert redo["id"] == draft["id"]
    assert (redo["amount"], redo["rate"]) == ("18.05", None)
    client.delete(f"{rates}/2025-07-01", headers=h)

    # Discard, recompute, confirm: creates exactly one interest movement of the year.
    discarded = _ok(
        client.post(f"/api/v1/deposit-interest-drafts/{draft['id']}/discard", headers=h), 200
    )
    assert discarded["status"] == "discarded"
    assert (
        client.post(f"/api/v1/deposit-interest-drafts/{draft['id']}/confirm", headers=h).status_code
        == 409
    )
    fresh = _ok(client.post(drafts, json={"year": 2025}, headers=h))
    assert fresh["amount"] == "12.00"
    done = _ok(
        client.post(f"/api/v1/deposit-interest-drafts/{fresh['id']}/confirm", headers=h), 200
    )
    assert done["status"] == "confirmed"
    assert done["movement_id"] is not None
    assert client.post(drafts, json={"year": 2025}, headers=h).status_code == 409
    assert [d["status"] for d in _ok(client.get(drafts, headers=h), 200)] == ["confirmed"]

    # Settlement mode deposit_rates uses the history: 12,00 (2025) + 2026 (rate in force 1 %):
    # 90 days at 1.200 and 91 days at 1.000 until 30.06.2026: 2,9589... + 2,4932... = 5,45.
    body = {"settlement_date": "2026-06-30", "interest_mode": "deposit_rates"}
    preview = f"/api/v1/deposits/{deposit}/settlements/preview"
    result = _ok(client.post(preview, json=body, headers=h), 200)
    assert [(y["year"], y["amount"]) for y in result["interest_years"]] == [
        (2025, "12.00"),
        (2026, "5.45"),
    ]
    assert result["interest_recorded"] == "24.00"  # 12,00 recorded earlier + confirmed 12,00
    assert result["interest_total"] == "17.45"
    # Without history the mode is refused.
    deposit2, _ = _deposit_with_address(client, h)
    refused = client.post(f"/api/v1/deposits/{deposit2}/settlements/preview", json=body, headers=h)
    assert refused.status_code == 422

    # Yearly run over all deposits with a rate: deposit 1 is confirmed (skipped), deposit 2 has
    # no rate and is not part of the run.
    run = _ok(
        client.post("/api/v1/deposit-interest-drafts/run", json={"year": 2025}, headers=h), 200
    )
    assert run["created"] == 0
    assert len(run["skipped"]) == 1
    _ok(
        client.put(
            f"/api/v1/deposits/{deposit2}/interest-rates/2025-01-01",
            json={"rate": "0.5"},
            headers=h,
        ),
        200,
    )
    run2 = _ok(
        client.post("/api/v1/deposit-interest-drafts/run", json={"year": 2025}, headers=h), 200
    )
    assert run2["created"] == 1


def test_portal_second_factor_policy(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "bzadmin"))
    reader = bearer(login(client, world, "bzread"))
    current = _ok(client.get("/api/v1/tenant/settings", headers=h), 200)
    assert current["portal_second_factor"] == "account_choice"
    assert (
        client.patch(
            "/api/v1/tenant/settings", json={"portal_second_factor": "required"}, headers=reader
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/v1/tenant/settings", json={"portal_second_factor": "never"}, headers=h
        ).status_code
        == 422
    )
    changed = _ok(
        client.patch(
            "/api/v1/tenant/settings", json={"portal_second_factor": "required"}, headers=h
        ),
        200,
    )
    assert changed["portal_second_factor"] == "required"
    back = _ok(
        client.patch(
            "/api/v1/tenant/settings", json={"portal_second_factor": "account_choice"}, headers=h
        ),
        200,
    )
    assert back["portal_second_factor"] == "account_choice"
