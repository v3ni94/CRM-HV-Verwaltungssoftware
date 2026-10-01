"""Package AE07 (wave 16, M24-01, V01-01): reserve plan per reserve and year and the opening
change switch. Expected values by hand:

* plan 2026 with reserve items 1.200,00 and 300,00 for reserve "Dach" -> derived draft
  1.500,00; resolved -> development 2026 Soll 1.500,00 from the reserve plan; opening
  10.000,00 -> closing 11.500,00 (no movements).
* a second resolved row 1.800,00 supersedes the first -> closing 11.800,00.
* opening switch: locked (default) 409; logged 200 with log row; four_eyes pending, self
  approval 409, approval by a second person applies 9.000,00.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m24_hoa import H, _hoa_ledger, _ok

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae07a-{RUN}", name=f"AE07A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae07b-{RUN}", name=f"AE07B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ae07admin", a, "tenant_admin"),
            ("ae07second", a, "tenant_admin"),
            ("ae07reader", a, "read_only"),
            ("ae07other", b, "tenant_admin"),
        ):
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
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as c:
        yield c


def _sql(engine: Engine, tenant: Any, statement: str, **params: Any) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        conn.execute(text(statement), params)


def _setup(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    w = _hoa_ledger(client, h, number)
    reserve = _ok(
        client.post(
            f"{H}/reserves",
            json={
                "ledger_id": w["ledger"],
                "name": "Dach",
                "opening_balance": "10000.00",
                "opening_year": 2026,
            },
            headers=h,
        ),
        201,
    )
    resolution = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2025-11-20",
                "subject": "Wirtschaftsplan 2026",
                "wording": "Der Wirtschaftsplan 2026 wird beschlossen.",
                "status": "positive",
            },
            headers=h,
        ),
        201,
    )
    return {**w, "reserve": reserve["id"], "resolution": resolution["id"]}


def test_reserve_plan_derive_resolve_and_development(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae07admin"))
    w = _setup(client, h, "771")
    rid = w["reserve"]
    plan = _ok(
        client.post(
            f"{H}/plans",
            json={"ledger_id": w["ledger"], "year": 2026, "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    for amount in ("1200.00", "300.00"):
        _ok(
            client.post(
                f"{H}/plans/{plan['id']}/items",
                json={
                    "label": "Rücklage Dach",
                    "component": "reserve",
                    "amount": amount,
                    "allocation_key_id": w["keys"]["MEA"],
                    "reserve_id": rid,
                },
                headers=h,
            ),
            201,
        )
    derived = _ok(client.post(f"{H}/plans/{plan['id']}/reserve-plans/derive", headers=h))
    assert [(d["planned_contribution"], d["status"], d["deviation"]) for d in derived] == [
        ("1500.00", "draft", "0.00")
    ]
    assert derived[0]["tax_classification_status"] == "not_released"
    # Derive again updates the same draft.
    again = _ok(client.post(f"{H}/plans/{plan['id']}/reserve-plans/derive", headers=h))
    assert again[0]["id"] == derived[0]["id"]
    pid = derived[0]["id"]

    # Resolve without resolution reference: 422.
    assert client.post(f"{H}/reserve-plans/{pid}/resolve", json={}, headers=h).status_code == 422
    done = _ok(
        client.post(
            f"{H}/reserve-plans/{pid}/resolve",
            json={"resolution_id": w["resolution"]},
            headers=h,
        )
    )
    assert done["status"] == "resolved"
    # A resolved row is frozen.
    r = client.patch(f"{H}/reserve-plans/{pid}", json={"planned_contribution": "1.00"}, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "MHVP-HOA-0035"

    dev = _ok(client.get(f"{H}/reserves/{rid}/development?year=2026", headers=h))
    y = dev["years"][-1]
    assert (y["contributions_planned"], y["planned_source"], y["closing"]) == (
        "1500.00",
        "reserve_plan",
        "11500.00",
    )

    second = _ok(
        client.post(
            f"{H}/reserves/{rid}/plans",
            json={"year": 2026, "planned_contribution": "1800.00"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/reserve-plans/{second['id']}/resolve",
            json={"resolution_id": w["resolution"]},
            headers=h,
        )
    )
    rows = _ok(client.get(f"{H}/reserves/{rid}/plans", headers=h))
    assert sorted(x["status"] for x in rows) == ["resolved", "superseded"]
    dev = _ok(client.get(f"{H}/reserves/{rid}/development?year=2026", headers=h))
    assert dev["years"][-1]["closing"] == "11800.00"

    # Validation, permission, tenant separation.
    bad = client.post(
        f"{H}/reserves/{rid}/plans",
        json={"year": 2026, "planned_contribution": "-1.00"},
        headers=h,
    )
    assert bad.status_code == 422
    assert client.get(f"{H}/reserves/{rid}/plans", params={"x": "1"}, headers=h).status_code == 422
    hr = bearer(login(client, world, "ae07reader"))
    assert _ok(client.get(f"{H}/reserves/{rid}/plans", headers=hr))
    assert (
        client.post(
            f"{H}/reserves/{rid}/plans",
            json={"year": 2026, "planned_contribution": "1.00"},
            headers=hr,
        ).status_code
        == 403
    )
    ho = bearer(login(client, world, "ae07other"))
    assert client.get(f"{H}/reserves/{rid}/plans", headers=ho).status_code == 404
    assert client.get(f"{H}/reserve-plans/{pid}", headers=ho).status_code == 404


def test_opening_switch_locked_logged_four_eyes(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    h = bearer(login(client, world, "ae07admin"))
    h2 = bearer(login(client, world, "ae07second"))
    w = _setup(client, h, "772")
    rid = w["reserve"]
    st = _ok(
        client.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2026}, headers=h),
        201,
    )
    _sql(
        migrator_engine,
        world.tenant_a,
        "UPDATE hoa_statement SET status = 'calculated' WHERE id = :i",
        i=st["id"],
    )
    assert _ok(client.get(f"{H}/reserve-policy", headers=h))["opening_lock_mode"] == "locked"
    r = client.patch(f"{H}/reserves/{rid}", json={"opening_balance": "9500.00"}, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "MHVP-HOA-0005"

    hr = bearer(login(client, world, "ae07reader"))
    assert (
        client.put(
            f"{H}/reserve-policy", json={"opening_lock_mode": "logged"}, headers=hr
        ).status_code
        == 403
    )
    assert (
        client.put(f"{H}/reserve-policy", json={"opening_lock_mode": "x"}, headers=h).status_code
        == 422
    )
    _ok(client.put(f"{H}/reserve-policy", json={"opening_lock_mode": "logged"}, headers=h))
    # Logged mode needs a reason.
    assert (
        client.patch(
            f"{H}/reserves/{rid}", json={"opening_balance": "9500.00"}, headers=h
        ).status_code
        == 422
    )
    out = _ok(
        client.patch(
            f"{H}/reserves/{rid}",
            json={"opening_balance": "9500.00", "change_reason": "Übernahmesaldo laut Bank"},
            headers=h,
        )
    )
    assert out["opening_balance"] == "9500.00"
    assert "opening_change" not in out
    log = _ok(client.get(f"{H}/reserves/{rid}/opening-changes", headers=h))
    assert log[0]["status"] == "applied"
    assert log[0]["changes"]["opening_balance"] == {"old": "10000.00", "new": "9500.00"}

    _ok(client.put(f"{H}/reserve-policy", json={"opening_lock_mode": "four_eyes"}, headers=h))
    out = _ok(
        client.patch(
            f"{H}/reserves/{rid}",
            json={"opening_balance": "9000.00", "change_reason": "Korrektur Kontoauszug"},
            headers=h,
        )
    )
    assert out["opening_balance"] == "9500.00"
    cid = out["opening_change"]["id"]
    assert out["opening_change"]["status"] == "pending"
    r = client.post(f"{H}/reserve-opening-changes/{cid}/approve", json={}, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "MHVP-HOA-0036"
    ho = bearer(login(client, world, "ae07other"))
    assert (
        client.post(f"{H}/reserve-opening-changes/{cid}/approve", json={}, headers=ho).status_code
        == 404
    )
    done = _ok(client.post(f"{H}/reserve-opening-changes/{cid}/approve", json={}, headers=h2))
    assert done["status"] == "applied"
    assert _ok(client.get(f"{H}/reserves/{rid}", headers=h))["opening_balance"] == "9000.00"
    assert (
        client.post(f"{H}/reserve-opening-changes/{cid}/reject", json={}, headers=h2).status_code
        == 409
    )
    _ok(client.put(f"{H}/reserve-policy", json={"opening_lock_mode": "locked"}, headers=h))
