"""AB03: real production of bank_transaction.imported, portal_account.activated,
contract.changed and contract_payment.changed through the domain paths (signature, minimum
payload, no names, IBAN or free text) and the delivery and read indications on message
(GA04-09). Own world (ab03-{RUN}), never shared with another module."""

import asyncio
import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.communication.models import Message
from mhvp.core.webhook_tasks import dispatch_once
from mhvp.core.webhooks import verify
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a69_webhooks import (
    _Receiver,
    _subscribe,
    receiver,  # noqa: F401
)
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _payment, _property, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m21_portal import _contact_of

pytestmark = pytest.mark.integration
# ruff: noqa: F811
IBAN_OWN = "DE02120300000000202051"
IBAN_PAYER = "DE75512108001245126199"


async def _world_ab03(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"ab03-{RUN}", name=f"AB03 Ereignisse {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("ab03admin"), display_name="ab03admin", password=PASSWORD
        )
        world.users["ab03admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world_ab03(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _deliver(database: Database, redis_url: str) -> None:
    asyncio.run(dispatch_once(_settings(database, redis_url)))


def _got(path: str, event_type: str) -> list[tuple[dict[str, str], bytes, dict[str, Any]]]:
    return [
        (h, raw, json.loads(raw))
        for p, h, raw in _Receiver.received
        if p == path and json.loads(raw)["type"] == event_type
    ]


def _check_signed(secret: str, headers: dict[str, str], raw: bytes, event_type: str) -> None:
    assert headers["X-MHVP-Event"] == event_type
    assert verify(secret, raw, headers["X-MHVP-Signature"], now=int(time.time()))
    assert not verify("wrong", raw, headers["X-MHVP-Signature"], now=int(time.time()))


def test_bank_import_event(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    h = bearer(login(client, world, "ab03admin"))
    secret = _subscribe(client, h, f"{receiver}/ab03-bank", ["bank_transaction.imported"])
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "931", "name": "AB03 Bank", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": IBAN_OWN,
                "holder": "GdWE AB03",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    purpose = f"Geheimzweck{RUN}"
    data = _camt(
        f"AB03-{RUN}",
        IBAN_OWN,
        "1000.00",
        "1300.00",
        [
            _ntry(f"AB03A{RUN}", "100.00", "CRDT", "2026-01-05", IBAN_PAYER, purpose),
            _ntry(f"AB03B{RUN}", "200.00", "CRDT", "2026-01-06", IBAN_PAYER, purpose),
        ],
    )
    doc = _upload(client, h, "ab03.xml", data)
    run = _ok(client.post("/api/v1/banking/imports", json={"document_id": doc}, headers=h), 201)
    assert run["counts"]["new"] == 2
    # Re-import adds nothing and must not produce a second event.
    _ok(client.post("/api/v1/banking/imports", json={"document_id": doc}, headers=h), 201)
    _deliver(database, redis_url)
    mine = [
        g for g in _got("/ab03-bank", "bank_transaction.imported") if g[2]["entity_id"] == account
    ]
    assert len(mine) == 1
    headers_in, raw, body = mine[0]
    _check_signed(secret, headers_in, raw, "bank_transaction.imported")
    assert body["tenant_id"] == str(world.tenant_a)
    assert body["entity_type"] == "bank_account"
    assert body["payload"]["count"] == 2
    assert body["payload"]["account_id"] == account
    assert set(body["payload"]) == {"account_id", "sync_run_id", "count"}
    text = raw.decode()
    for secret_value in (IBAN_OWN, IBAN_PAYER, purpose, "Zahler", "GdWE AB03"):
        assert secret_value not in text


def test_portal_account_activated_event(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    h = bearer(login(client, world, "ab03admin"))
    secret = _subscribe(client, h, f"{receiver}/ab03-portal", ["portal_account.activated"])
    party, _ = _party(client, h, "Portalab")
    contact = _contact_of(client, h, party)
    inv = _ok(
        client.post(
            "/api/v1/portal-admin/accounts",
            json={"contact_id": contact, "email": world.email("ab03res"), "display_name": "Res"},
            headers=h,
        ),
        201,
    )
    _deliver(database, redis_url)
    assert all(
        g[2]["entity_id"] != inv["id"] for g in _got("/ab03-portal", "portal_account.activated")
    )
    _ok(
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": inv["invitation_token"], "password": PASSWORD},
        )
    )
    # A second, invalid redemption must not produce another event.
    assert (
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": inv["invitation_token"], "password": PASSWORD},
        ).status_code
        == 422
    )
    _deliver(database, redis_url)
    mine = [
        g
        for g in _got("/ab03-portal", "portal_account.activated")
        if g[2]["entity_id"] == inv["id"]
    ]
    assert len(mine) == 1
    headers_in, raw, body = mine[0]
    _check_signed(secret, headers_in, raw, "portal_account.activated")
    assert body["entity_type"] == "portal_account"
    assert body["payload"] == {"account_id": inv["id"]}
    text = raw.decode()
    assert world.email("ab03res") not in text
    assert inv["invitation_token"] not in text
    assert f"Test{RUN}" not in text


def test_contract_changed_and_payment_changed_events(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    h = bearer(login(client, world, "ab03admin"))
    secret = _subscribe(
        client, h, f"{receiver}/ab03-contract", ["contract.changed", "contract_payment.changed"]
    )
    prop = _property(client, h, "932", "rental")
    unit = _unit(client, h, prop["id"], "01")
    tenant, _ = _party(client, h, "Mieterab")
    owner, _ = _party(client, h, "Eigentuemerab", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    cid = contract["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{cid}/payments",
            json=_payment("800.00", "800.00", "2026-01-01"),
            headers=h,
        ),
        201,
    )
    note = f"Vertraulich{RUN}"
    v2 = _ok(
        client.post(
            f"/api/v1/contracts/{cid}/versions",
            json={
                "effective_date": "2026-07-01",
                "dunning_block": True,
                "dunning_block_reason": note,
            },
            headers=h,
        ),
        201,
    )
    _deliver(database, redis_url)
    pay = [
        g for g in _got("/ab03-contract", "contract_payment.changed") if g[2]["entity_id"] == cid
    ]
    assert len(pay) == 1
    chg = [g for g in _got("/ab03-contract", "contract.changed") if g[2]["entity_id"] == v2["id"]]
    assert len(chg) == 1
    for headers_in, raw, body in pay + chg:
        _check_signed(secret, headers_in, raw, body["type"])
        assert body["tenant_id"] == str(world.tenant_a)
        assert body["entity_type"] == "contract"
        assert set(body["payload"]) == {"source_type", "contract_id"}
        assert body["payload"]["contract_id"] == body["entity_id"]
        text = raw.decode()
        for forbidden in (note, "800.00", f"Test{RUN}", "Mieterab"):
            assert forbidden not in text
    assert pay[0][2]["payload"]["source_type"] == "contract.payment_added"
    assert {g[2]["payload"]["source_type"] for g in chg} <= {
        "contract.updated",
        "contract.versioned",
        "contract.schedule_updated",
    }


def test_message_delivered_and_read_indications(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    h = bearer(login(client, world, "ab03admin"))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Lesab",
                "last_name": f"Test{RUN}",
                "emails": [{"email": f"lesab.{RUN}@example.org"}],
            },
            headers=h,
        ),
        201,
    )
    doc = str(
        _ok(
            client.post(
                "/api/v1/documents",
                files={"file": (f"ab03-{uuid.uuid4().hex[:6]}.txt", b"Schreiben", "text/plain")},
                headers=h,
            ),
            201,
        )["id"]
    )
    mail = _ok(
        client.post(
            "/api/v1/dispatches",
            json={"document_id": doc, "contact_id": contact["id"], "channel": "email"},
            headers=h,
        ),
        201,
    )
    portal_dispatch = _ok(
        client.post(
            "/api/v1/dispatches",
            json={"document_id": doc, "contact_id": contact["id"], "channel": "portal"},
            headers=h,
        ),
        201,
    )
    assert portal_dispatch["status"] == "sent"
    message_id = uuid.UUID(str(mail["message_id"]))

    async def _state(update_sent: bool = False) -> tuple[Any, Any, str]:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                row = await session.scalar(select(Message).where(Message.id == message_id))
                assert row is not None
                if update_sent:
                    row.status = "sent"
                return row.delivered_at, row.read_at, row.status
        finally:
            await engine.dispose()

    assert asyncio.run(_state()) == (None, None, "draft")
    # Portal opening before the mail was sent writes no read indication.
    inv = _ok(
        client.post(
            "/api/v1/portal-admin/accounts",
            json={
                "contact_id": contact["id"],
                "email": world.email("ab03read"),
                "display_name": "L",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": inv["invitation_token"], "password": PASSWORD},
        )
    )
    portal = bearer(login(client, world, "ab03read"))
    _ok(client.get(f"/api/v1/portal/documents/{doc}", headers=portal))
    assert asyncio.run(_state())[1] is None

    # Delivery evidence on the dispatch marks the linked message as delivered.
    _ok(
        client.post(
            f"/api/v1/dispatches/{mail['id']}/evidence",
            json={"status": "delivered", "evidence_kind": "other", "evidence_ref": f"AB03-{RUN}"},
            headers=h,
        )
    )
    delivered, read, _ = asyncio.run(_state(update_sent=True))
    assert delivered is not None
    assert read is None
    # Opening in the portal now sets read_at once (first event wins).
    _ok(client.get(f"/api/v1/portal/documents/{doc}", headers=portal))
    _, first_read, _ = asyncio.run(_state())
    assert first_read is not None
    _ok(client.get(f"/api/v1/portal/documents/{doc}", headers=portal))
    assert asyncio.run(_state())[1] == first_read
    shown = _ok(client.get(f"/api/v1/mail/messages/{message_id}", headers=h))
    assert shown["read_at"] is not None
    assert shown["delivered_at"] is not None
