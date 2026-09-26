"""Approval of imported contracts (Betreiberauftrag 26.09.2026, migration 0133): pending
contracts create no receivables and are counted as skipped, approval one by one and all at
once with ``contract.approved`` events, rejection ends the contract at its start, only roles
with ``contracts:approve`` decide. Expected: 3 contracts x 300,00 hoa_fee; with two pending
the run has 1 ready item (300,00) and ``skipped_pending_approval`` 2."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from mhvp.contracts.models import Contract
from mhvp.core.events import DomainEvent
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
SOURCE = "immoware24:zuordnung"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap-{RUN}", name=f"Freigabe {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for key, role in (("apadmin", "tenant_admin"), ("apclerk", "standard")):
            uid = await services.create_user(
                factory, email=world.email(key), display_name=key, password=PASSWORD
            )
            world.users[key] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


async def _db(settings: Any, tenant_id: uuid.UUID, fn: Any) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            return await fn(session)
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


def _contract(c: TestClient, h: dict[str, str], prop: str, unit_no: str) -> dict[str, Any]:
    unit = _unit(c, h, prop, unit_no)
    party, _ = _party(c, h, f"F{unit_no}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2026-01-01",
                "title_transfer_date": "2026-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/payments",
            json={
                "payment_type_code": "hoa_fee",
                "net": "300.00",
                "gross": "300.00",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": "2026-01-01", "due_day": 1},
            headers=h,
        ),
        201,
    )
    return contract  # type: ignore[no-any-return]


def test_import_approval(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "apadmin"))
    clerk = bearer(login(client, world, "apclerk"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "733", "name": "Freigabehaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    manual = _contract(client, h, prop["id"], "01")
    assert manual["approval_status"] == "approved"
    assert manual["source"] is None
    imported = [_contract(client, h, prop["id"], n) for n in ("02", "03")]
    ids = [uuid.UUID(c["id"]) for c in imported]

    async def mark(session: Any) -> None:
        await session.execute(
            update(Contract)
            .where(Contract.id.in_(ids))
            .values(source=SOURCE, approval_status="pending")
        )

    asyncio.run(_db(settings, world.tenant_a, mark))

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
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": acc["060100"]},
            headers=h,
        )
    )

    # Receivable run skips the pending contracts and counts them.
    scope = {"period_month": "2026-03-01", "scope": "property", "scope_id": prop["id"]}
    run = _ok(client.post(f"{A}/receivable-runs", json=scope, headers=h), 201)
    assert run["totals"]["ready"] == {"count": 1, "amount": "300.00"}
    assert run["totals"]["skipped_pending_approval"] == 2
    assert {i["contract_id"] for i in run["items"]} == {manual["id"]}

    # Listing: object, unit, party, kind, start, monthly amount, source.
    pending = _ok(client.get("/api/v1/contracts/pending-approval", headers=h))
    assert {p["id"] for p in pending} == {c["id"] for c in imported}
    row = next(p for p in pending if p["id"] == imported[0]["id"])
    assert row["property_number"] == "733"
    assert row["unit_number"] == "02"
    assert row["kind"] == "ownership"
    assert row["start_date"] == "2026-01-01"
    assert row["monthly_amount"] == "300.00"
    assert row["source"] == SOURCE
    assert _ok(client.get("/api/v1/contracts/pending-approval?source=other", headers=h)) == []

    # Permission: contracts:approve (standard role has contracts:update only).
    assert _ok(client.get("/api/v1/contracts/pending-approval", headers=clerk))
    body = {"ids": [imported[0]["id"]]}
    assert client.post("/api/v1/contracts/approve", json=body, headers=clerk).status_code == 403
    assert (
        client.post(
            f"/api/v1/contracts/{imported[1]['id']}/reject-import", json={}, headers=clerk
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/contracts/approve", json={"ids": [], "all": False}, headers=h)
    ).status_code == 422

    # Single approval, repeated click without effect.
    one = _ok(client.post("/api/v1/contracts/approve", json=body, headers=h))
    assert one == {"approved": 1, "ids": [imported[0]["id"]]}
    assert _ok(client.post("/api/v1/contracts/approve", json=body, headers=h))["approved"] == 0
    got = _ok(client.get(f"/api/v1/contracts/{imported[0]['id']}", headers=h))
    assert got["approval_status"] == "approved"
    assert got["approved_by"] == str(world.users["apadmin"])
    assert got["approved_at"] is not None

    # Rejection ends the second contract at its start and marks it rejected.
    rejected = _ok(
        client.post(
            f"/api/v1/contracts/{imported[1]['id']}/reject-import",
            json={"reason": "Falsche Einheit"},
            headers=h,
        )
    )
    assert rejected["end_date"] == "2026-01-01"
    got = _ok(client.get(f"/api/v1/contracts/{imported[1]['id']}", headers=h))
    assert (got["approval_status"], got["end_date"]) == ("rejected", "2026-01-01")
    assert all(p["valid_to"] == "2026-01-01" for p in got["payments"])
    assert (
        client.post(
            f"/api/v1/contracts/{imported[1]['id']}/reject-import", json={}, headers=h
        ).status_code
        == 409
    )
    assert _ok(client.get("/api/v1/contracts/pending-approval", headers=h)) == []

    # A fresh preview (new basis) now contains the approved contract, rejected stays out.
    run = _ok(client.post(f"{A}/receivable-runs", json=scope, headers=h), 201)
    assert run["totals"]["ready"] == {"count": 2, "amount": "600.00"}
    assert run["totals"]["skipped_pending_approval"] == 0

    # Approve all by source.
    third = _contract(client, h, prop["id"], "04")

    async def mark_third(session: Any) -> None:
        await session.execute(
            update(Contract)
            .where(Contract.id == uuid.UUID(third["id"]))
            .values(source=SOURCE, approval_status="pending")
        )

    asyncio.run(_db(settings, world.tenant_a, mark_third))
    every = _ok(
        client.post("/api/v1/contracts/approve", json={"all": True, "source": SOURCE}, headers=h)
    )
    assert every == {"approved": 1, "ids": [third["id"]]}

    async def events(session: Any) -> list[Any]:
        return list(
            (
                await session.scalars(
                    select(DomainEvent).where(DomainEvent.type == "contract.approved")
                )
            ).all()
        )

    approved = asyncio.run(_db(settings, world.tenant_a, events))
    assert {str(e.entity_id) for e in approved} == {imported[0]["id"], third["id"]}
    assert all(e.actor_user_id == world.users["apadmin"] for e in approved)
    assert all(e.payload["approved_at"] for e in approved)
