"""AE08 (P07-02): variant switch and Soll/Ist per earmarked reserve. Expected by hand: two
reserves without resolved plan and statement -> planned 0,00, paid 0,00, source none."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

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
        a, _ = await services.provision_tenant(factory, slug=f"ae08a-{RUN}", name=f"AE08A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae08b-{RUN}", name=f"AE08B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ae08admin", a, "tenant_admin"),
            ("ae08reader", a, "read_only"),
            ("ae08other", b, "tenant_admin"),
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


def test_switch_and_reserve_payments(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae08admin"))
    reader = bearer(login(client, world, "ae08reader"))
    other = bearer(login(client, world, "ae08other"))

    setting = _ok(client.get(f"{H}/reserve-payment-settings", headers=h))
    assert setting["mode"] == "bound_only"
    assert (
        client.put(f"{H}/reserve-payment-settings", json={"mode": "auto"}, headers=h).status_code
        == 422
    )
    assert (
        client.put(
            f"{H}/reserve-payment-settings", json={"mode": "plan_ratio_proposal"}, headers=reader
        ).status_code
        == 403
    )

    w = _hoa_ledger(client, h, "798")
    ledger = w["ledger"]
    for name in ("Dach", "Fassade"):
        _ok(client.post(f"{H}/reserves", json={"ledger_id": ledger, "name": name}, headers=h), 201)

    out = _ok(client.get(f"{H}/ledgers/{ledger}/reserve-payments?year=2025", headers=h))
    assert out["mode"] == "bound_only"
    assert out["source"] == "none"
    assert [r["name"] for r in out["reserves"]] == ["Dach", "Fassade"]
    assert out["reserves"][0]["planned"] == "0.00"
    assert "paid_proposal" not in out["reserves"][0]

    _ok(
        client.put(f"{H}/reserve-payment-settings", json={"mode": "plan_ratio_proposal"}, headers=h)
    )
    out = _ok(client.get(f"{H}/ledgers/{ledger}/reserve-payments?year=2025", headers=reader))
    assert out["mode"] == "plan_ratio_proposal"
    assert out["reserves"][0]["paid_proposal"] == "0.00"

    assert (
        client.get(f"{H}/ledgers/{ledger}/reserve-payments?year=2025&x=1", headers=h).status_code
        == 422
    )
    assert (
        client.get(f"{H}/ledgers/{ledger}/reserve-payments?year=1800", headers=h).status_code == 422
    )
    assert (
        client.get(f"{H}/ledgers/{ledger}/reserve-payments?year=2025", headers=other).status_code
        == 404
    )
    assert _ok(client.get(f"{H}/reserve-payment-settings", headers=other))["mode"] == "bound_only"
