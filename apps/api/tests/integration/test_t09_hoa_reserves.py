"""Package T09 (wave 5, M24-01): earmarked reserve per position with bank investment of the
legal entity, opening balance and development per year. Expected values by hand:

* reserve "Dach", opening balance 10.000,00 EUR at the start of 2024, no plan, no statement
  in 2024 -> 2024 closing 10.000,00.
* 2025 draft statement: withdrawal 1.500,00 (Dachrinne, receipt pending), fee 5,00, interest
  20,00 -> 2025 opening 10.000,00, closing 10.000,00 - 1.500,00 - 5,00 + 20,00 = 8.515,00.
* deleting the fee -> closing 8.520,00.
"""

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
        a, _ = await services.provision_tenant(factory, slug=f"t09a-{RUN}", name=f"T09A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t09b-{RUN}", name=f"T09B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("t09admin", a, "tenant_admin"),
            ("t09reader", a, "read_only"),
            ("t09other", b, "tenant_admin"),
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


def test_reserve_position_development_and_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "t09admin"))
    w = _hoa_ledger(client, h, "791")
    ledger = w["ledger"]
    reserve = _ok(
        client.post(
            f"{H}/reserves",
            json={
                "ledger_id": ledger,
                "name": "Dach",
                "purpose": "Erneuerung Dacheindeckung",
                "account_id": w["acc"]["001201"],
                "opening_balance": "10000.00",
                "opening_year": 2024,
            },
            headers=h,
        ),
        201,
    )
    assert (reserve["opening_balance"], reserve["opening_year"]) == ("10000.00", 2024)
    detail = _ok(client.get(f"{H}/reserves/{reserve['id']}", headers=h))
    assert detail["legal_entity_id"] == w["hoa"]

    st = _ok(
        client.post(f"{H}/statements", json={"ledger_id": ledger, "year": 2025}, headers=h), 201
    )
    ids = []
    for kind, amount, purpose in (
        ("withdrawal", "1500.00", "Dachrinne erneuert"),
        ("fee", "5.00", "Kontoführung Rücklagenkonto"),
        ("interest", "20.00", "Zinsen Festgeld"),
    ):
        ids.append(
            _ok(
                client.post(
                    f"{H}/statements/{st['id']}/reserve-movements",
                    json={
                        "reserve_id": reserve["id"],
                        "kind": kind,
                        "amount": amount,
                        "purpose": purpose,
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )
    movements = _ok(client.get(f"{H}/statements/{st['id']}/reserve-movements", headers=h))
    assert len(movements) == 3
    assert movements[0]["receipt_linked"] is False

    dev = _ok(client.get(f"{H}/reserves/{reserve['id']}/development?year=2025", headers=h))
    y2024, y2025 = dev["years"]
    assert (y2024["opening"], y2024["closing"], y2024["opening_entered"]) == (
        "10000.00",
        "10000.00",
        True,
    )
    assert (y2025["opening"], y2025["withdrawals"], y2025["fees"], y2025["interest"]) == (
        "10000.00",
        "1500.00",
        "5.00",
        "20.00",
    )
    assert y2025["closing"] == "8515.00"

    assert (
        client.delete(
            f"{H}/statements/{st['id']}/reserve-movements/{ids[1]}", headers=h
        ).status_code
        == 204
    )
    dev = _ok(client.get(f"{H}/reserves/{reserve['id']}/development?year=2025", headers=h))
    assert dev["years"][-1]["closing"] == "8520.00"

    # Patch: rename and new opening balance; a foreign ledger account is refused.
    patched = _ok(
        client.patch(
            f"{H}/reserves/{reserve['id']}",
            json={"name": "Dach und Rinnen", "opening_balance": "9000.00"},
            headers=h,
        )
    )
    assert (patched["name"], patched["opening_balance"]) == ("Dach und Rinnen", "9000.00")
    other = _hoa_ledger(client, h, "792")
    bad = client.patch(
        f"{H}/reserves/{reserve['id']}", json={"account_id": other["acc"]["001201"]}, headers=h
    )
    assert bad.status_code == 422
    bad = client.patch(
        f"{H}/reserves/{reserve['id']}",
        json={"bank_account_id": "00000000-0000-7000-8000-000000000000"},
        headers=h,
    )
    assert bad.status_code == 422
    assert (
        client.patch(f"{H}/reserves/{reserve['id']}", json={"name": None}, headers=h).status_code
        == 422
    )
    assert (
        client.patch(f"{H}/reserves/{reserve['id']}", json={"unknown": 1}, headers=h).status_code
        == 422
    )
    assert (
        client.get(f"{H}/reserves/{reserve['id']}/development?year=1800", headers=h).status_code
        == 422
    )

    # Read only: may read, may not change.
    r = bearer(login(client, world, "t09reader"))
    assert (
        client.get(f"{H}/reserves/{reserve['id']}/development?year=2025", headers=r).status_code
        == 200
    )
    assert (
        client.patch(f"{H}/reserves/{reserve['id']}", json={"name": "Neu"}, headers=r).status_code
        == 403
    )
    assert (
        client.delete(
            f"{H}/statements/{st['id']}/reserve-movements/{ids[0]}", headers=r
        ).status_code
        == 403
    )

    # Other tenant: 404 (RLS).
    o = bearer(login(client, world, "t09other"))
    assert client.get(f"{H}/reserves/{reserve['id']}", headers=o).status_code == 404
    assert (
        client.patch(f"{H}/reserves/{reserve['id']}", json={"name": "Xy"}, headers=o).status_code
        == 404
    )
    assert (
        client.get(f"{H}/reserves/{reserve['id']}/development?year=2025", headers=o).status_code
        == 404
    )
    assert client.get(f"{H}/statements/{st['id']}/reserve-movements", headers=o).status_code == 404
    assert (
        client.delete(
            f"{H}/statements/{st['id']}/reserve-movements/{ids[0]}", headers=o
        ).status_code
        == 404
    )
