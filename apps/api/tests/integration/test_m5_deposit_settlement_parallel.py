"""GAM-606 (rule 0.1.9): deposit settlement released in parallel, aborted and repeated.

Fixed expectations: deposit 2.000,00 EUR paid on 01.01.2025, no interest (mode none), one
deduction Nachforderung 312,40 EUR, so the payout of the settlement is
2.000,00 - 312,40 = 1.687,60 EUR. The payout (release, behind G3) may happen exactly once per
deposit: a parallel second release of the same draft gets 409, an aborted release leaves the
draft unchanged, and a second draft of the same deposit is no second payout."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import IBAN, _ok, _party, _property, _unit
from tests.integration.test_m5_deposit_settlement import _settings

pytestmark = pytest.mark.integration


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"kp-{RUN}", name=f"KautPar {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("kpmaker", "kpchecker"):
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
    return asyncio.run(_world(_settings(database, redis_url)))


def _deposit(client: TestClient, h: dict[str, str], number: str = "966") -> str:
    prop = _property(client, h, number, "rental")
    unit = _unit(client, h, prop["id"], "01")
    owner, _ = _party(client, h, "Vermieter", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
    )["legal_entity_id"]
    tenant, _ = _party(client, h, "Mieter")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2025-01-01",
                "end_date": "2026-06-30",
            },
            headers=h,
        )
    )
    account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "deposit",
                "iban": IBAN,
                "holder": "Kaution",
                "valid_from": "2025-01-01",
            },
            headers=h,
        )
    )
    deposit = _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/deposits",
            json={
                "kind": "cash",
                "amount_due": "2000.00",
                "valid_from": "2025-01-01",
                "property_bank_account_id": account["id"],
            },
            headers=h,
        )
    )
    _ok(
        client.post(
            f"/api/v1/deposits/{deposit['id']}/movements",
            json={"date": "2025-01-01", "amount": "2000.00", "kind": "payment"},
            headers=h,
        )
    )
    return str(deposit["id"])


BODY = {
    "settlement_date": "2026-06-30",
    "interest_mode": "none",
    "deductions": [{"label": "Nachforderung Betriebskosten", "amount": "312.40"}],
}


def test_deposit_settlement_parallel_payout(
    world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    with TestClient(create_app(settings, release_gate_resolver=OpenG3())) as client:
        maker = bearer(login(client, world, "kpmaker"))
        checker = bearer(login(client, world, "kpchecker"))
        deposit = _deposit(client, maker)
        settlements = f"/api/v1/deposits/{deposit}/settlements"
        first = _ok(client.post(settlements, json=BODY, headers=maker), 201)
        assert first["payout_amount"] == "1687.60"
        assert first["deductions_total"] == "312.40"
        release = f"/api/v1/deposit-settlements/{first['id']}/release"

        # Abort: the release fails after the status change (event write raises); the
        # transaction rolls back and the draft stays a draft.
        async def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("synthetic abort")

        with (
            patch("mhvp.contracts.deposit_settlement_routers.emit", boom),
            TestClient(
                create_app(settings, release_gate_resolver=OpenG3()),
                raise_server_exceptions=False,
            ) as broken,
        ):
            assert broken.post(release, headers=checker).status_code == 500
        assert [s["status"] for s in _ok(client.get(settlements, headers=maker), 200)] == ["draft"]

        # Same draft released twice at the same time: exactly one payout, second call 409.
        def release_in_own_client(path: str) -> Any:
            with TestClient(create_app(settings, release_gate_resolver=OpenG3())) as own:
                return own.post(path, headers=checker)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(release_in_own_client, [release, release]))
        assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
        winner = next(r.json() for r in results if r.status_code == 200)
        assert (winner["status"], winner["payout_amount"]) == ("released", "1687.60")


def test_deposit_settlement_second_draft_no_second_payout(
    world: World, database: Database, redis_url: str
) -> None:
    """After one released settlement (payout 1.687,60 EUR) a second draft of the same deposit
    must not lead to a second payout (sequential, independent of the race above)."""
    settings = _settings(database, redis_url)
    with TestClient(create_app(settings, release_gate_resolver=OpenG3())) as client:
        maker = bearer(login(client, world, "kpmaker"))
        checker = bearer(login(client, world, "kpchecker"))
        deposit = _deposit(client, maker, "967")
        settlements = f"/api/v1/deposits/{deposit}/settlements"
        first = _ok(client.post(settlements, json=BODY, headers=maker), 201)
        released = _ok(
            client.post(f"/api/v1/deposit-settlements/{first['id']}/release", headers=checker),
            200,
        )
        assert (released["status"], released["payout_amount"]) == ("released", "1687.60")
        second = client.post(settlements, json=BODY, headers=maker)
        if second.status_code == 201:
            again = client.post(
                f"/api/v1/deposit-settlements/{second.json()['id']}/release", headers=checker
            )
            assert again.status_code == 409, again.text
        else:
            assert second.status_code == 409, second.text
        released_rows = [
            s for s in _ok(client.get(settlements, headers=maker), 200) if s["status"] == "released"
        ]
        assert [s["payout_amount"] for s in released_rows] == ["1687.60"]
