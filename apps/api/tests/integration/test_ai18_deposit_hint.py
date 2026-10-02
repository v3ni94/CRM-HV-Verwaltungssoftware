"""AI18 (GAH-111): non blocking deposit hint behind the tenant switch (default off).

Rent 800,00 without operating costs (advance 150,00 is not counted), factor 3 -> comparison
value 2.400,00. Deposit 2.500,00 in 4 instalments gives two hints when the switch is on;
2.400,00 in 3 instalments gives none. Saving is never blocked. Permissions, validation and
tenant separation of the setting.
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
from tests.integration.test_m5_contracts import _party, _payment, _property, _unit

pytestmark = pytest.mark.integration
S = "/api/v1/deposit-hint-settings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ai18a-{RUN}", name=f"AI18 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ai18b-{RUN}", name=f"AI18b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ai18admin", a, "tenant_admin"),
            ("ai18read", a, "read_only"),
            ("ai18foreign", b, "tenant_admin"),
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
    return response.json()


BODY = {
    "deposit_limit_hint_enabled": True,
    "factor_months": "3",
    "max_installments": 3,
    "rent_payment_codes": ["rent"],
}


def test_deposit_hint_switch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ai18admin"))
    read = bearer(login(client, world, "ai18read"))
    foreign = bearer(login(client, world, "ai18foreign"))
    default = _ok(client.get(S, headers=h))
    assert default["deposit_limit_hint_enabled"] is False
    assert default["max_installments"] == 3
    assert default["rent_payment_codes"] == ["rent"]
    assert client.get(S, params={"x": "1"}, headers=h).status_code == 422

    prop = _property(client, h, "918", "rental")
    unit = _unit(client, h, prop["id"], "01")
    owner, _ = _party(client, h, "Vermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenant, _ = _party(client, h, "Mieter")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    pay = f"/api/v1/contracts/{contract['id']}/payments"
    _ok(client.post(pay, json=_payment("800.00", "800.00", "2026-01-01"), headers=h), 201)
    _ok(
        client.post(
            pay,
            json=_payment("150.00", "150.00", "2026-01-01", "operating_cost_advance"),
            headers=h,
        ),
        201,
    )
    deposits = f"/api/v1/contracts/{contract['id']}/deposits"
    high = {"kind": "cash", "amount_due": "2500.00", "installments": 4, "valid_from": "2026-01-01"}
    # Switch off: saved without hint.
    created = _ok(client.post(deposits, json=high, headers=h), 201)
    assert created["limit_hints"] == []

    assert client.put(S, json=BODY, headers=read).status_code == 403
    assert client.put(S, json={**BODY, "factor_months": "0"}, headers=h).status_code == 422
    assert client.put(S, json={**BODY, "max_installments": 13}, headers=h).status_code == 422
    assert client.put(S, json={**BODY, "rent_payment_codes": []}, headers=h).status_code == 422
    saved = _ok(client.put(S, json=BODY, headers=h))
    assert saved["deposit_limit_hint_enabled"] is True
    assert _ok(client.get(S, headers=read))["deposit_limit_hint_enabled"] is True
    # Tenant separation: the other tenant still sees its own default.
    assert _ok(client.get(S, headers=foreign))["deposit_limit_hint_enabled"] is False

    listed = _ok(client.get(deposits, headers=h))
    hints = next(d for d in listed if d["id"] == created["id"])["limit_hints"]
    assert len(hints) == 2
    assert "2.500,00 EUR" in hints[0]
    assert "2.400,00 EUR" in hints[0]
    assert "4 Raten" in hints[1]
    assert all("§" not in text and "BGB" not in text for text in hints)
    # Never blocking: a second high deposit is still saved, with the hint.
    again = _ok(client.post(deposits, json=high, headers=h), 201)
    assert len(again["limit_hints"]) == 2
    fine = _ok(
        client.post(
            deposits,
            json={**high, "amount_due": "2400.00", "installments": 3},
            headers=h,
        ),
        201,
    )
    assert fine["limit_hints"] == []
    _ok(client.put(S, json={**BODY, "deposit_limit_hint_enabled": False}, headers=h))
    assert all(d["limit_hints"] == [] for d in _ok(client.get(deposits, headers=h)))
