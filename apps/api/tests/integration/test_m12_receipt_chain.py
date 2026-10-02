"""B05 evidence chain (rule B05, MASTER-PROMPT 7.1): a person reports a bank movement as
unreceipted, the row carries a responsible ticket and its age, booking from the bank line is
locked (MHVP-BANK-0027) until the document is linked or a person decides "no document
required" with a reason; 403 without rights, 404 for a foreign tenant. Fixed expected values."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.clock import local_today
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m11_banking import _ntry, _upload
from tests.integration.test_m12_posting_decisions import STRANGER, _hoa, _import, _ok, _settings

pytestmark = pytest.mark.integration
B = "/api/v1/banking"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rcc-{RUN}", name=f"Beleg {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rco-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("rchadmin", a, "tenant_admin"),
            ("rchcare", a, "caretaker"),
            ("rchother", b, "tenant_admin"),
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


def test_receipt_chain_lock_and_release(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rchadmin"))
    care = bearer(login(client, world, "rchcare"))
    other = bearer(login(client, world, "rchother"))
    w = _hoa(client, h, "871", "DE02500105170137075030")
    txs = _import(
        client,
        h,
        "RC-1",
        w["iban"],
        [
            _ntry("R1", "80.00", "DBIT", "2026-01-12", STRANGER, "Reparatur Tor"),
            _ntry("R2", "45.50", "DBIT", "2026-01-13", STRANGER, "Hausmeister Material"),
        ],
    )["txs"]
    t1, t2 = txs["R1"]["id"], txs["R2"]["id"]
    body = {"reason": "Rechnung fehlt"}
    book = {"settlements": [], "counter_account_id": w["income"]}

    # Authorization and tenant separation.
    assert (
        client.post(f"{B}/transactions/{t1}/clarification", json=body, headers=care).status_code
        == 403
    )
    assert (
        client.post(f"{B}/transactions/{t1}/clarification", json=body, headers=other).status_code
        == 404
    )
    assert (
        client.post(
            f"{B}/transactions/{t1}/clarification", json={"reason": ""}, headers=h
        ).status_code
        == 422
    )

    # Happy path: open with ticket and age; a second call returns the same row.
    opened = _ok(client.post(f"{B}/transactions/{t1}/clarification", json=body, headers=h), 201)
    again = _ok(client.post(f"{B}/transactions/{t1}/clarification", json=body, headers=h), 201)
    assert again["id"] == opened["id"]
    assert opened["status"] == "open"
    assert opened["ticket_id"] is not None
    assert opened["reasons"] == ["Rechnung fehlt"]
    assert opened["age_days"] == (local_today() - date(2026, 1, 12)).days

    # Lock without document or flag.
    refused = client.post(f"{B}/transactions/{t1}/book", json=book, headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-BANK-0027"
    _ok(
        client.post(
            f"{B}/clarifications/{opened['id']}", json={"status": "receipt_requested"}, headers=h
        )
    )
    listed = _ok(client.get(f"{B}/clarifications", params={"legal_entity_id": w["hoa"]}, headers=h))
    assert [(r["id"], r["status"]) for r in listed] == [(opened["id"], "receipt_requested")]
    assert client.get(f"{B}/clarifications", headers=other).json() == []
    assert client.post(f"{B}/transactions/{t1}/book", json=book, headers=h).status_code == 409

    # Release by a person's reasoned flag "no document required".
    flagged = _ok(
        client.post(
            f"{B}/clarifications/{opened['id']}",
            json={"status": "no_document_required", "reason": "Barauslage, Eigenbeleg in Akte"},
            headers=h,
        )
    )
    assert flagged["decided_by"] == str(world.users["rchadmin"])
    assert flagged["decided_at"] is not None
    _ok(client.post(f"{B}/transactions/{t1}/book", json=book, headers=h), 201)

    # Release by the linked document.
    second = _ok(client.post(f"{B}/transactions/{t2}/clarification", json=body, headers=h), 201)
    assert client.post(f"{B}/transactions/{t2}/book", json=book, headers=h).status_code == 409
    doc = _upload(client, h, "rechnung.xml", b"<rechnung/>")
    _ok(
        client.post(
            f"{B}/clarifications/{second['id']}",
            json={"status": "resolved", "document_id": doc},
            headers=h,
        )
    )
    _ok(client.post(f"{B}/transactions/{t2}/book", json=book, headers=h), 201)
    assert _ok(client.get(f"{B}/clarifications", headers=h)) == []
    # Nothing is deleted: both decided rows stay visible.
    assert (
        len(_ok(client.get(f"{B}/clarifications", params={"open_only": "false"}, headers=h))) == 2
    )
