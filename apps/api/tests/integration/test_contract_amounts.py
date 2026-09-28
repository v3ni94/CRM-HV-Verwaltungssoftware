"""Sollbeträge im CRM (Paket D, 28.09.2026): the contract screens record standing amounts via
``POST /contracts/{id}/payments`` and read the history via ``GET /contracts/{id}/payments``.
Fixed expected values: a new amount of a kind closes the open predecessor the day before, the
past is never overwritten, overlapping periods are rejected, the caretaker role has no access
and a second tenant sees nothing (RLS)."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _ok, _party, _payment, _property, _unit

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"amt-{RUN}", name=f"Beträge {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"amo-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("amtadmin", a, "tenant_admin"),
            ("amtcaretaker", a, "caretaker"),
            ("amtother", b, "tenant_admin"),
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
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _tenancy(client: TestClient, h: dict[str, str], number: str) -> str:
    prop = _property(client, h, number, "rental")
    unit = _unit(client, h, prop["id"], "01")
    owner, _ = _party(client, h, "Eigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
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
                "end_date": "2027-12-31",
            },
            headers=h,
        )
    )
    return str(contract["id"])


def test_new_amount_from_date_closes_predecessor_and_keeps_history(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "amtadmin"))
    cid = _tenancy(client, h, "601")
    pay = f"/api/v1/contracts/{cid}/payments"

    rent = _ok(client.post(pay, json=_payment("800.00", "800.00", "2026-01-01"), headers=h))
    assert rent["reason"] == "initial"
    advance = _ok(
        client.post(
            pay,
            json={**_payment("150.00", "178.50", "2026-01-01", "operating_cost_advance", "19")},
            headers=h,
        )
    )
    assert (advance["net"], advance["vat_percent"], advance["gross"]) == (
        "150.00",
        "19",
        "178.50",
    )
    # Rent increase from 01.07.2026 as a new version of the kind (reason increase).
    increase = _ok(
        client.post(
            pay,
            json={**_payment("850.00", "850.00", "2026-07-01"), "reason": "increase"},
            headers=h,
        )
    )
    assert increase["valid_to"] is None

    history = _ok(client.get(pay, headers=h), 200)
    rows = {(r["payment_type_code"], r["valid_from"]): r for r in history}
    assert len(history) == 3
    # The first rent ends the day before the increase; its amount is untouched.
    assert rows[("rent", "2026-01-01")]["valid_to"] == "2026-06-30"
    assert rows[("rent", "2026-01-01")]["gross"] == "800.00"
    assert rows[("rent", "2026-07-01")]["valid_to"] is None
    assert rows[("operating_cost_advance", "2026-01-01")]["valid_to"] is None

    # Monthly totals the screen shows: 800,00 + 178,50 before, 850,00 + 178,50 after.
    def total(as_of: str) -> Decimal:
        return sum(
            (
                Decimal(r["gross"])
                for r in history
                if r["valid_from"] <= as_of and (r["valid_to"] is None or r["valid_to"] >= as_of)
            ),
            Decimal("0.00"),
        )

    assert total("2026-06-30") == Decimal("978.50")
    assert total("2026-07-01") == Decimal("1028.50")
    # The contract itself carries the same rows (detail page fallback).
    detail = _ok(client.get(f"/api/v1/contracts/{cid}", headers=h), 200)
    assert len(detail["payments"]) == 3


def test_overlapping_periods_and_bad_amounts_are_rejected(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "amtadmin"))
    cid = _tenancy(client, h, "602")
    pay = f"/api/v1/contracts/{cid}/payments"
    limited = {**_payment("800.00", "800.00", "2026-01-01"), "valid_to": "2026-12-31"}
    _ok(client.post(pay, json=limited, headers=h))

    # A limited amount is not closed automatically: a new rent inside its period overlaps.
    inside = client.post(pay, json=_payment("850.00", "850.00", "2026-06-01"), headers=h)
    assert inside.status_code == 409, inside.text
    # Same start twice of the same kind overlaps as well.
    same = client.post(pay, json=_payment("900.00", "900.00", "2026-01-01"), headers=h)
    assert same.status_code == 409, same.text
    # After the limited period the new amount fits.
    _ok(client.post(pay, json=_payment("850.00", "850.00", "2027-01-01"), headers=h))
    # Outside the term (end 31.12.2027) and gross not matching net and VAT: 422.
    late = client.post(pay, json=_payment("1.00", "1.00", "2028-01-01"), headers=h)
    assert late.status_code == 422
    mismatch = client.post(
        pay, json=_payment("100.00", "118.00", "2027-06-01", vat="19"), headers=h
    )
    assert mismatch.status_code == 422
    negative = client.post(pay, json=_payment("-10.00", "-10.00", "2027-06-01"), headers=h)
    assert negative.status_code == 422
    history = _ok(client.get(pay, headers=h), 200)
    assert [(r["valid_from"], r["valid_to"], r["gross"]) for r in history] == [
        ("2026-01-01", "2026-12-31", "800.00"),
        ("2027-01-01", None, "850.00"),
    ]


def test_caretaker_has_no_access_and_other_tenant_sees_nothing(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "amtadmin"))
    cid = _tenancy(client, h, "603")
    pay = f"/api/v1/contracts/{cid}/payments"
    _ok(client.post(pay, json=_payment("500.00", "500.00", "2026-01-01"), headers=h))

    caretaker = bearer(login(client, world, "amtcaretaker"))
    assert client.get(pay, headers=caretaker).status_code == 403
    assert (
        client.post(pay, json=_payment("1.00", "1.00", "2026-02-01"), headers=caretaker).status_code
        == 403
    )

    other = bearer(login(client, world, "amtother", tenant_id=world.tenant_b))
    assert client.get(pay, headers=other).status_code == 404
    assert (
        client.post(pay, json=_payment("1.00", "1.00", "2026-02-01"), headers=other).status_code
        == 404
    )
    # Nothing changed for the owning tenant.
    history = _ok(client.get(pay, headers=h), 200)
    assert [(r["valid_from"], r["gross"]) for r in history] == [("2026-01-01", "500.00")]
