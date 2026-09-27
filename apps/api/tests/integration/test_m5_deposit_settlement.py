"""Rule M5-02 (operator decision 26.09.2026): deposit settlement drafts via the API.

Reference rate table per tenant, settlement preview and draft in the three interest modes,
tenant separation of rates and settlements, release behind gate G3 (always closed here).
Expected values are hand computed (rule 0.1.8), see tests/unit/test_m5_deposit_settlement.py.
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
from tests.integration.test_m5_contracts import IBAN, _ok, _party, _property, _unit

pytestmark = pytest.mark.integration
RATES = "/api/v1/deposit-interest-rates"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ks-{RUN}", name=f"Kaution {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"kt-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ksadmin", a, "tenant_admin"),
            ("ksother", b, "tenant_admin"),
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


def _deposit_with_movements(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    """Tenancy from 01.01.2025 with a segregated deposit account; payment 1.200,00 on
    01.01.2025, offset 200,00 on 01.04.2026, interest movement 12,00 on 31.12.2025."""
    prop = _property(client, h, "952", "rental")
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
                "amount_due": "1200.00",
                "valid_from": "2025-01-01",
                "property_bank_account_id": account["id"],
            },
            headers=h,
        )
    )
    moves = f"/api/v1/deposits/{deposit['id']}/movements"
    _ok(
        client.post(
            moves, json={"date": "2025-01-01", "amount": "1200.00", "kind": "payment"}, headers=h
        )
    )
    _ok(
        client.post(
            moves, json={"date": "2025-12-31", "amount": "12.00", "kind": "interest"}, headers=h
        )
    )
    _ok(
        client.post(
            moves,
            json={"date": "2026-04-01", "amount": "200.00", "kind": "offset", "reason": "Schaden"},
            headers=h,
        )
    )
    return str(deposit["id"]), str(contract["id"])


def test_reference_rates_per_tenant(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ksadmin"))
    other = bearer(login(client, world, "ksother", tenant_id=world.tenant_b))
    assert client.put(f"{RATES}/2025", json={"rate": "101"}, headers=h).status_code == 422
    row = _ok(
        client.put(f"{RATES}/2025", json={"rate": "1.0", "note": "zu prüfen"}, headers=h), 200
    )
    assert row["rate"] == "1.00000"
    again = _ok(client.put(f"{RATES}/2025", json={"rate": "1.25"}, headers=h), 200)
    assert again["id"] == row["id"]
    assert again["rate"] == "1.25000"
    assert [r["year"] for r in _ok(client.get(RATES, headers=h), 200)] == [2025]
    # Tenant separation: the other tenant sees no rates and cannot delete this one.
    assert _ok(client.get(RATES, headers=other), 200) == []
    assert client.delete(f"{RATES}/2025", headers=other).status_code == 404
    assert client.delete(f"{RATES}/2025", headers=h).status_code == 204
    assert _ok(client.get(RATES, headers=h), 200) == []


def test_settlement_modes_and_g3_lock(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ksadmin"))
    other = bearer(login(client, world, "ksother", tenant_id=world.tenant_b))
    deposit, contract = _deposit_with_movements(client, h)
    preview = f"/api/v1/deposits/{deposit}/settlements/preview"
    settlements = f"/api/v1/deposits/{deposit}/settlements"

    # (c) no interest: 1.200,00 - 200,00 - 80,00 = 920,00; recorded interest only shown.
    none = _ok(
        client.post(
            preview,
            json={
                "settlement_date": "2026-06-30",
                "interest_mode": "none",
                "deductions": [{"label": "Endreinigung", "amount": "80.00"}],
            },
            headers=h,
        ),
        200,
    )
    assert none["balance_before_interest"] == "1000.00"
    assert none["interest_recorded"] == "12.00"
    assert none["interest_total"] == "0.00"
    assert none["payout_amount"] == "920.00"
    assert none["interest_years"] == []
    assert none["id"] is None
    assert none["draft_only"] is True

    # (b) reference rate: missing year refused, then 12,00 (2025) + 2,73 (2026) = 14,73.
    _ok(client.put(f"{RATES}/2025", json={"rate": "1.0"}, headers=h), 200)
    body = {"settlement_date": "2026-06-30", "interest_mode": "reference_rate"}
    missing = client.post(preview, json=body, headers=h)
    assert missing.status_code == 422
    assert "2026" in missing.json()["detail"]
    _ok(client.put(f"{RATES}/2026", json={"rate": "0.5"}, headers=h), 200)
    ref = _ok(
        client.post(
            settlements,
            json={**body, "deductions": [{"label": "Schaden Bad", "amount": "150.00"}]},
            headers=h,
        )
    )
    assert [(y["year"], y["rate"], y["days"], y["amount"]) for y in ref["interest_years"]] == [
        (2025, "1.00000", 365, "12.00"),
        (2026, "0.50000", 181, "2.73"),
    ]
    assert ref["interest_total"] == "14.73"
    assert ref["payout_amount"] == "864.73"
    assert ref["status"] == "draft"
    assert ref["draft_only"] is True

    # (a) individual interest per year, entered from the bank statement.
    ind = _ok(
        client.post(
            settlements,
            json={
                "settlement_date": "2026-06-30",
                "interest_mode": "individual",
                "interest_years": [
                    {"year": 2025, "amount": "12.00"},
                    {"year": 2026, "amount": "1.05"},
                ],
            },
            headers=h,
        )
    )
    assert ind["interest_total"] == "13.05"
    assert ind["payout_amount"] == "1013.05"
    # Validation: years only with mode individual, no year twice, before contract end.
    assert (
        client.post(
            settlements,
            json={**body, "interest_years": [{"year": 2025, "amount": "1.00"}]},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.post(
            settlements, json={"settlement_date": "2026-05-31", "interest_mode": "none"}, headers=h
        ).status_code
        == 422
    )
    # Deductions above the balance are no draft (a claim is not part of it).
    assert (
        client.post(
            preview,
            json={**body, "deductions": [{"label": "Schaden", "amount": "1100.00"}]},
            headers=h,
        ).status_code
        == 422
    )
    listed = _ok(client.get(settlements, headers=h), 200)
    assert [s["id"] for s in listed] == [ref["id"], ind["id"]]
    # Deposit balance unchanged: the draft records nothing (1.200 + 12 - 200 = 1.012,00).
    balance = _ok(client.get(f"/api/v1/contracts/{contract}/deposits", headers=h), 200)[0]
    assert balance["balance"] == "1012.00"
    assert len(balance["movements"]) == 3

    # Tenant separation: foreign tenant sees neither the deposit nor its settlements.
    assert client.get(settlements, headers=other).status_code == 404
    assert client.post(preview, json=body, headers=other).status_code == 404

    # G3 lock: the release stays closed for every tenant; the draft is not changed.
    release = client.post(f"/api/v1/deposit-settlements/{ref['id']}/release", headers=h)
    assert release.status_code == 403, release.text
    assert release.json()["code"] == "MHVP-GATE-0001"
    assert release.json()["gate"] == "G3"
    still = _ok(client.get(settlements, headers=h), 200)[0]
    assert still["status"] == "draft"
    client.delete(f"{RATES}/2025", headers=h)
    client.delete(f"{RATES}/2026", headers=h)
