"""GAG-06 (GAE-02, P06-02): the bank matching respects the object period lock. Fixed expected
values (rule 0.1.8): a lock of the property for 01.01.2026 to 31.01.2026 marks the posting
proposal of a payment of 05.01.2026 as locked (MHVP-ACC-0030) only in mode ``object_period``,
and the booking of that payment is refused with 409 MHVP-ACC-0030; nothing is posted."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m12_matching import (
    BANK,
    PAYERS,
    A,
    B,
    _ok,
    client,  # noqa: F401 - fixture
)
from tests.integration.test_m12_posting_proposals import _hoa_with_open_items

pytestmark = pytest.mark.integration
L = f"{A}/period-locks"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ah03-{RUN}", name=f"AH03 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ah03b-{RUN}", name=f"AH03b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ah03admin", a, "tenant_admin"),
            ("ah03reader", a, "read_only"),
            ("ah03other", b, "tenant_admin"),
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


def test_bank_proposal_and_booking_respect_object_lock(
    client: TestClient,  # noqa: F811
    world: World,
) -> None:
    h = bearer(login(client, world, "ah03admin"))
    reader = bearer(login(client, world, "ah03reader"))
    other = bearer(login(client, world, "ah03other"))
    _hoa, contracts = _hoa_with_open_items(client, h, "731")
    n1 = contracts[0]["number"]
    statement = _camt(
        "AH03-1",
        BANK,
        "0.00",
        "250.00",
        [_ntry("AH1", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"Hausgeld {n1}")],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "ah.xml", statement)}, headers=h
        ),
        201,
    )
    (tx,) = [
        t for t in _ok(client.get(f"{B}/transactions", headers=h)) if t["bank_reference"] == "AH1"
    ]
    url = f"{B}/transactions/{tx['id']}/posting-proposals"
    first = _ok(client.get(url, headers=h))
    assert first["object_period_lock"] == {"locked": False, "code": None}
    (match,) = first["stage1"]
    item = match["splits"][0]["open_item_id"]
    ledger = first["ledger_id"]
    unit = _ok(client.get(f"/api/v1/units/{contracts[0]['unit_id']}", headers=h))
    lock = _ok(
        client.post(
            L,
            json={
                "ledger_id": ledger,
                "property_id": unit["property_id"],
                "period_from": "2026-01-01",
                "period_to": "2026-01-31",
                "reason": "Abschluss Januar",
            },
            headers=h,
        ),
        201,
    )
    assert lock["active"] is True
    # Mode ledger_only (default): the object lock does not restrict.
    assert _ok(client.get(url, headers=h))["object_period_lock"]["locked"] is False
    _ok(client.put(f"{L}/settings", json={"lock_mode": "object_period"}, headers=h))
    locked = _ok(client.get(url, headers=h))
    assert locked["object_period_lock"] == {"locked": True, "code": "MHVP-ACC-0030"}
    # Reading stays possible for read rights; other tenant sees nothing.
    assert _ok(client.get(url, headers=reader))["object_period_lock"]["locked"] is True
    assert client.get(url, headers=other).status_code == 404
    # Booking into the locked period is refused, nothing is posted.
    refused = client.post(
        f"{B}/transactions/{tx['id']}/book",
        json={"settlements": [{"open_item_id": item, "amount": "250.00"}]},
        headers=h,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "MHVP-ACC-0030"
    assert _ok(client.get(f"{B}/transactions", params={"status": "booked"}, headers=h)) == []
    bad = client.post(f"{B}/transactions/{tx['id']}/book", json={"settlements": "x"}, headers=h)
    assert bad.status_code == 422
