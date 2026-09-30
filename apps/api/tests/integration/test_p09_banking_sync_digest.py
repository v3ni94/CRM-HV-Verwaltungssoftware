"""Lückenliste 30.09.2026, package P09: sync hour per tenant and manual full sync (M11-05),
proposal and automatic posting counters on the sync run (M11-06), weekly L3 digest with B09
coupling (M12-02) and payer IBAN into the four eyes release (M12-03). Tenant separation (other
tenant 404), permissions (403) and validation (422). Fixed expected values (rule 0.1.8);
nothing here opens a gate or posts automatically."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.banking import digest
from mhvp.banking.models import AutoPostingDigest, BankSyncRun
from mhvp.banking.tasks import record_run_metrics
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m11_banking import _ntry
from tests.integration.test_m12_posting_decisions import _hoa, _import, _ok, _settings

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
BANK = "DE02700202700010108669"
NEW_PAYER = "DE02701500000000594937"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p09-{RUN}", name=f"P09 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p09o-{RUN}", name=f"P09o {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("p9admin", a, "tenant_admin"),
            ("p9care", a, "caretaker"),
            ("p9other", b, "tenant_admin"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _db(settings: Any, tenant_id: uuid.UUID, fn: Callable[[Any], Awaitable[Any]]) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def run() -> Any:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_sync_settings_run_and_separation(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "p9admin"))
    care = bearer(login(client, world, "p9care"))
    other = bearer(login(client, world, "p9other"))

    assert _ok(client.get(f"{B}/sync/settings", headers=h)) == {
        "sync_hour": 6,
        "configured": False,
    }
    assert client.put(f"{B}/sync/settings", json={"sync_hour": 24}, headers=h).status_code == 422
    assert client.put(f"{B}/sync/settings", json={"sync_hour": 4}, headers=care).status_code == 403
    assert client.get(f"{B}/sync/settings", headers=care).status_code == 403
    assert _ok(client.put(f"{B}/sync/settings", json={"sync_hour": 4}, headers=h)) == {
        "sync_hour": 4,
        "configured": True,
    }
    # RLS: the other tenant still has the default.
    assert _ok(client.get(f"{B}/sync/settings", headers=other))["sync_hour"] == 6

    run = _ok(client.post(f"{B}/sync/run", headers=h), 202)
    assert run == {"connections": 0, "not_configured": 0, "queued": 0}
    assert client.post(f"{B}/sync/run", headers=care).status_code == 403


def test_run_metrics_digest_confirmation_and_l3_block(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "p9admin"))
    other = bearer(login(client, world, "p9other"))
    w = _hoa(client, h, "901", BANK)
    n1 = w["contracts"][0]["number"]
    imported = _import(
        client,
        h,
        "P9-0",
        BANK,
        [_ntry("P9T0", "250.00", "CRDT", "2026-01-05", NEW_PAYER, f"Hausgeld {n1}")],
    )
    run_id = uuid.UUID(imported["run"]["id"])

    async def metrics(session: Any) -> dict[str, int]:
        await record_run_metrics(session, run_id, proposals=3, auto_posted=1)
        await record_run_metrics(session, run_id, proposals=2, auto_posted=0)
        row = await session.get(BankSyncRun, run_id)
        return dict(row.counts)

    counts = _db(settings, world.tenant_a, metrics)
    assert counts["proposals"] == 2
    assert counts["auto_posted"] == 0
    assert counts["new"] == 1  # import counters untouched

    # Digest row seeded directly (the runner needs G1 and released levels, tested elsewhere).
    hoa = uuid.UUID(w["hoa"])

    async def seed(session: Any) -> str:
        row = AutoPostingDigest(
            tenant_id=world.tenant_a,
            legal_entity_id=hoa,
            week_start=date(2026, 9, 21),
            auto_posted=4,
            sampled=1,
            reviews_open=0,
            findings=0,
            reconciliation=[{"statements": []}],
            reconciliation_ok=False,
        )
        session.add(row)
        await session.flush()
        blocked = await digest.l3_blocked(session, today=date(2026, 9, 30))
        assert blocked is True
        assert await digest.l3_blocked(session, today=date(2026, 9, 23)) is False
        return str(row.id)

    digest_id = _db(settings, world.tenant_a, seed)
    listed = _ok(client.get(f"{B}/auto-posting/digests", headers=h))
    assert [d["id"] for d in listed] == [digest_id]
    assert _ok(client.get(f"{B}/auto-posting/digests", headers=other)) == []
    assert (
        client.post(f"{B}/auto-posting/digests/{digest_id}/confirm", headers=other).status_code
        == 404
    )
    refused = client.post(f"{B}/auto-posting/digests/{digest_id}/confirm", headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-BANK-0028"

    async def reconcile_ok(session: Any) -> None:
        row = await session.get(AutoPostingDigest, uuid.UUID(digest_id))
        row.reconciliation_ok = True

    _db(settings, world.tenant_a, reconcile_ok)
    confirmed = _ok(client.post(f"{B}/auto-posting/digests/{digest_id}/confirm", headers=h))
    assert confirmed["confirmed_by"] == str(world.users["p9admin"])

    async def unblocked(session: Any) -> bool:
        return await digest.l3_blocked(session, today=date(2026, 9, 30))

    assert _db(settings, world.tenant_a, unblocked) is False

    # build_week without automatic postings in the week writes nothing.
    built = _ok(
        client.post(f"{B}/auto-posting/digests/build", json={"week_start": "2026-09-14"}, headers=h)
    )
    assert built == []


def test_payer_iban_proposal_after_confirmed_booking(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "p9admin"))
    care = bearer(login(client, world, "p9care"))
    other = bearer(login(client, world, "p9other"))
    w = _hoa(client, h, "902", "DE02100100100006820101")
    n1 = w["contracts"][0]["number"]
    imported = _import(
        client,
        h,
        "P9-1",
        "DE02100100100006820101",
        [_ntry("P9T1", "250.00", "CRDT", "2026-01-06", NEW_PAYER, f"Hausgeld {n1}")],
    )
    tx = imported["txs"]["P9T1"]["id"]
    # Before the booking: nothing to propose.
    before = _ok(client.get(f"{B}/transactions/{tx}/payer-iban", headers=h))
    assert before["proposable"] is False
    assert client.get(f"{B}/transactions/{tx}/payer-iban", headers=other).status_code == 404

    proposals = _ok(client.get(f"{B}/transactions/{tx}/posting-proposals", headers=h))
    split = proposals["stage1"][0]["splits"][0]
    _ok(
        client.post(
            f"{B}/transactions/{tx}/book",
            json={"settlements": [{"open_item_id": split["open_item_id"], "amount": "250.00"}]},
            headers=h,
        ),
        201,
    )
    after = _ok(client.get(f"{B}/transactions/{tx}/payer-iban", headers=h))
    assert after["proposable"] is True
    assert after["iban_known"] is False
    assert after["iban_suffix"] == NEW_PAYER[-4:]
    assert len(after["contacts"]) == 1
    contact_id = after["contacts"][0]["contact_id"]

    assert (
        client.post(
            f"{B}/transactions/{tx}/payer-iban", json={"contact_id": contact_id}, headers=care
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{B}/transactions/{tx}/payer-iban", json={"contact_id": "x"}, headers=h
        ).status_code
        == 422
    )
    wrong = client.post(
        f"{B}/transactions/{tx}/payer-iban", json={"contact_id": str(uuid.uuid4())}, headers=h
    )
    assert wrong.status_code == 409
    created = _ok(
        client.post(
            f"{B}/transactions/{tx}/payer-iban", json={"contact_id": contact_id}, headers=h
        ),
        201,
    )
    assert created["approval_status"] == "pending"
    assert created["iban_suffix"] == NEW_PAYER[-4:]
    # A second proposal is refused (IBAN now pending on the contact).
    again = _ok(client.get(f"{B}/transactions/{tx}/payer-iban", headers=h))
    assert again["iban_known"] is True
    assert again["proposable"] is False
