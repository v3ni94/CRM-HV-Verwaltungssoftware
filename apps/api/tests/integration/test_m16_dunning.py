"""M16 dunning: preview with overdue receivables per debtor, dunning block, threshold, level
timing and non leading ledger excluded with reasons; fees and interest stay zero (V7);
approval needs a second person and the leading system (G1)."""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.accounting.tasks import dunning_previews
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m13_receivables import _contract

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


class OpenG1:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dn-{RUN}", name=f"Mahn {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m16admin", "tenant_admin"), ("m16acc", "accountant_no_banking")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_dunning_preview_and_locks(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "m16admin"))
    acc_user = bearer(login(client, world, "m16acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "761", "name": "Mahnhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(client, h, prop["id"], "01", "2020-01-01")
    c2 = _contract(client, h, prop["id"], "02", "2020-01-01")
    blocked = _contract(client, h, prop["id"], "03", "2020-01-01")
    _ok(
        client.post(
            f"/api/v1/contracts/{blocked['id']}/versions",
            json={
                "effective_date": "2026-01-01",
                "dunning_block": True,
                "dunning_block_reason": "Ratenzahlung vereinbart",
            },
            headers=h,
        ),
        201,
    )
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
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    run = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))

    # Fees in settings are refused: a configured value is no legal basis (V7).
    bad = client.put(
        f"{A}/dunning-settings",
        json={"levels": [{"level": 1, "min_days_overdue": 10, "fee": "5.00"}]},
        headers=h,
    )
    assert bad.status_code == 422
    _ok(
        client.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 30, "text": "Mahnung"},
                ],
                "threshold_amount": "20.00",
            },
            headers=h,
        )
    )

    early = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-08"}, headers=h), 201)
    assert {c["status"] for c in early["cases"]} == {"excluded"}
    reasons = sorted(c["reason"].split(":")[0] for c in early["cases"])
    assert reasons == [
        "Mahnsperre",
        "Noch nicht 10 Tage überfällig",
        "Noch nicht 10 Tage überfällig",
    ]
    prev = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    assert prev["fees_and_interest"] == "locked_until_v7"
    assert len(prev["cases"]) == 3
    assert all(c["fee_amount"] == "0.00" and c["interest_amount"] == "0.00" for c in prev["cases"])
    assert all(c["total"] == "350.00" for c in prev["cases"])  # 300,00 hoa_fee + 50,00 reserve
    open_cases = [c for c in prev["cases"] if not c["reason"].startswith("Mahnsperre")]
    assert len(open_cases) == 2
    assert all("nicht führend" in c["reason"] for c in open_cases)  # comparison ledger
    assert (
        client.post(f"{A}/dunning-runs/{prev['id']}/approve", headers=acc_user).status_code == 200
    )  # nothing proposed

    # With G1 the ledger becomes leading; approval needs a second person.
    gh = bearer(login(gated, world, "m16acc"))
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    lead = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    assert sorted(c["status"] for c in lead["cases"]) == ["excluded", "proposed", "proposed"]
    assert {c["level"] for c in lead["cases"]} == {1}
    assert client.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=h).status_code == 403
    approved = _ok(client.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user))
    assert approved["status"] == "approved"
    listed = _ok(client.get(f"{A}/dunning-runs", headers=acc_user))
    assert lead["id"] in {r["id"] for r in listed}
    again = _ok(client.get(f"{A}/dunning-runs/{lead['id']}", headers=acc_user))
    assert (again["status"], len(again["cases"])) == ("approved", 3)
    assert (
        client.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user).status_code == 409
    )
    proposed = {c["contract_id"] for c in lead["cases"] if c["status"] == "proposed"}
    assert proposed == {c1["id"], c2["id"]}

    # Scheduled job creates previews only.
    assert asyncio.run(dunning_previews(_settings(database, redis_url)))["runs"] >= 1
