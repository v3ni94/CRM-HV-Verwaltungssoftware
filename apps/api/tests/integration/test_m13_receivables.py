"""M13: receivable run with preview, posting once per contract, component and month (B08),
changed basis invalidates the preview, proration and non monthly intervals stay manual (7.5),
reversal, management fee draft. Expected values: 2 contracts x 300,00 hoa_fee + 50,00 reserve
= 700,00 posted; a contract starting on 15.03. is manual, not prorated."""

import asyncio
import time
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rc-{RUN}", name=f"Soll {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m13admin"), display_name="m13", password=PASSWORD
        )
        world.users["m13admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _contract(
    c: TestClient, h: dict[str, str], prop: str, unit_no: str, start: str
) -> dict[str, Any]:
    unit = _unit(c, h, prop, unit_no)
    party, _ = _party(c, h, f"E{unit_no}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": start,
                "title_transfer_date": start,
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    for code, amount in [("hoa_fee", "300.00"), ("reserve", "50.00")]:
        _ok(
            c.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": code,
                    "net": amount,
                    "gross": amount,
                    "valid_from": start,
                },
                headers=h,
            ),
            201,
        )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": start, "due_day": 3},
            headers=h,
        ),
        201,
    )
    return contract  # type: ignore[no-any-return]


def test_receivable_run(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m13admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "731", "name": "Sollhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(client, h, prop["id"], "01", "2020-01-01")
    _contract(client, h, prop["id"], "02", "2020-01-01")
    late = _contract(client, h, prop["id"], "03", "2026-03-15")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }

    blocked = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    assert (
        blocked["totals"]["blocked"]["count"] == 4
    )  # no revenue account mapped yet; contract 03 is manual
    assert (
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": acc["001200"]},
            headers=h,
        ).status_code
        == 422
    )
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    assert (
        client.post(f"{A}/receivable-runs/{blocked['id']}/post", headers=h).status_code == 409
    )  # stale preview

    started = time.monotonic()
    run = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    assert time.monotonic() - started < 120
    assert run["totals"]["ready"] == {"count": 4, "amount": "700.00"}
    manual = [i for i in run["items"] if i["status"] == "manual"]
    assert {i["contract_id"] for i in manual} == {late["id"]}
    assert "zeitanteilige" in manual[0]["message"]
    assert {i["due_date"] for i in run["items"] if i["status"] == "ready"} == {"2026-03-03"}

    posted = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert posted["status"] == "posted"
    again = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert again["items"] == posted["items"]  # repeated click: no second effect
    second = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    assert "ready" not in second["totals"]  # already posted for March
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )
    assert sum(Decimal(i["remaining"]) for i in items) == Decimal("700.00")
    assert {i["contract_id"] for i in items} == {
        c1["id"],
        posted["items"][2]["contract_id"],
    } or len(items) == 4

    # Reversal of the run reopens the period for a new run.
    rev = _ok(
        client.post(
            f"{A}/receivable-runs/{run['id']}/reverse",
            json={"reason": "Beschluss geändert", "booking_date": "2026-03-20"},
            headers=h,
        )
    )
    assert rev == {"reversed": 4, "status": "reversed"}
    assert (
        _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h
            )
        )
        == []
    )
    rerun = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    assert rerun["totals"]["ready"]["count"] == 2
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True

    # Management fee: 3 apartments x 25,00 = 75,00, minimum 100,00 applies; 19 % -> 19,00.
    fee = _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "19",
                "min_amount": "100.00",
                "amounts_per_unit_type": {"apartment": "25.00"},
            },
            headers=h,
        ),
        201,
    )
    preview = _ok(client.get(f"{A}/admin-fees/{fee['id']}/invoice-preview", headers=h))
    assert preview["lines"][0]["amount"] == "75.00"
    assert preview["net"] == "100.00"
    assert preview["vat"] == "19.00"
    assert preview["gross"] == "119.00"
    assert preview["status"] == "draft"
