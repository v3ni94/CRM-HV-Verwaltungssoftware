"""D34 (Anhang D, 11.3, A53): a portal read receipt is recorded as an indication with time and
account, kept apart from dispatch evidence ("Zustellung") and from any receipt date ("Zugang");
listing writes nothing; the expiry of a portal invitation triggers no legal consequence (no
acknowledgement, no waiver, no deadline, no receipt, no dispatch status)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import func, select, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _doc, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rr-{RUN}", name=f"Lese {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("rradmin"), display_name="admin", password=PASSWORD
        )
        world.users["rradmin"] = uid
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _db(database: Database, redis_url: str, world: World, fn: Any) -> Any:
    """Run ``fn(session)`` in a tenant transaction of the test tenant (RLS applies)."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def run() -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), world.tenant_a) as s:
                return await fn(s)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _dispatch_count(database: Database, redis_url: str, world: World, document: str) -> int:
    from mhvp.communication.models import Dispatch

    async def count(s: Any) -> int:
        return int(
            await s.scalar(
                select(func.count())
                .select_from(Dispatch)
                .where(Dispatch.document_id == uuid.UUID(document))
            )
            or 0
        )

    return int(_db(database, redis_url, world, count))


def test_d34_read_receipt_is_an_indication_apart_from_delivery(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "rradmin"))
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "831", "name": "Lese-Miethaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "LeseVermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    party, _ = _party(client, h, "LeseMieter")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": _unit(client, h, rental["id"], "A"),
                "party_id": party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    document = _doc(client, h, "Betriebskosten", "contract", contract["id"], ["tenant"])
    contact = _contact_of(client, h, party)
    tenant = _portal_user(client, h, world, "rrtenant", contact)

    # Listing writes nothing.
    assert {d["id"] for d in _ok(client.get(f"{P}/documents", headers=tenant))} == {document}
    receipts_path = f"/api/v1/documents/{document}/portal-read-receipts"
    empty = _ok(client.get(receipts_path, headers=h))
    assert empty["items"] == []
    assert "Keine Zustellung" in empty["note"]

    # Opening and downloading are recorded with time, account and kind; the answer to the
    # portal user carries the same legal note.
    before = datetime.now(UTC) - timedelta(seconds=5)
    opened = _ok(client.get(f"{P}/documents/{document}", headers=tenant))
    assert "Keine Zustellung" in opened["read_receipt_note"]
    assert client.get(f"{P}/documents/{document}/download", headers=tenant).content == (
        b"Betriebskosten"
    )
    out = _ok(client.get(receipts_path, headers=h))
    assert [r["kind"] for r in out["items"]] == ["downloaded", "opened"]
    for r in out["items"]:
        assert r["contact_id"] == contact
        assert datetime.fromisoformat(r["occurred_at"]) >= before
        assert set(r) == {"id", "account_id", "contact_id", "kind", "occurred_at"}
    assert "Keine Zustellung" in out["note"]
    assert "Zugang" in out["note"]

    # Apart from delivery: no dispatch row appears, the document itself is unchanged, and the
    # CRM endpoint needs documents:read (the portal user is refused).
    assert _dispatch_count(database, redis_url, world, document) == 0
    doc = _ok(client.get(f"/api/v1/documents/{document}", headers=h))
    assert doc["visibility"] == ["tenant"]
    assert client.get(receipts_path, headers=tenant).status_code == 403
    assert (
        client.get(f"/api/v1/documents/{uuid.uuid4()}/portal-read-receipts", headers=h).status_code
        == 404
    )


def test_d34_expired_invitation_triggers_no_legal_consequence(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "rradmin"))
    weg = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "832", "name": "Lese-WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    party, _ = _party(client, h, "LeseEig")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": _unit(client, h, weg["id"], "01"),
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    document = _doc(client, h, "Einladung ETV", "legal_entity", hoa, ["owner"])
    contact = _contact_of(client, h, party)
    inv = _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("rrowner"), "display_name": "o"},
            headers=h,
        ),
        201,
    )

    async def expire(s: Any) -> None:
        await s.execute(
            text("UPDATE portal_account SET invitation_expires_at = :at WHERE contact_id = :c"),
            {"at": datetime.now(UTC) - timedelta(days=1), "c": uuid.UUID(contact)},
        )

    _db(database, redis_url, world, expire)

    # The expired invitation cannot be accepted; the account stays "invited".
    assert (
        client.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        ).status_code
        == 422
    )

    async def state(s: Any) -> tuple[str, int, int]:
        from mhvp.core.events import DomainEvent
        from mhvp.portal.models import PortalAccount, PortalReadReceipt

        account = await s.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == uuid.UUID(contact))
        )
        receipts = await s.scalar(
            select(func.count())
            .select_from(PortalReadReceipt)
            .where(PortalReadReceipt.account_id == account.id)
        )
        events = await s.scalar(
            select(func.count())
            .select_from(DomainEvent)
            .where(
                DomainEvent.entity_id == account.id,
                DomainEvent.type.not_in(("portal_account.invited",)),
            )
        )
        return str(account.status), int(receipts or 0), int(events or 0)

    # No legal consequence: no read receipt, no dispatch, no acknowledgement or deadline
    # event for the account, the document stays untouched.
    assert _db(database, redis_url, world, state) == ("invited", 0, 0)
    assert (
        _ok(client.get(f"/api/v1/documents/{document}/portal-read-receipts", headers=h))["items"]
        == []
    )
    assert _dispatch_count(database, redis_url, world, document) == 0
    assert client.get(f"/api/v1/documents/{document}", headers=h).json()["visibility"] == ["owner"]
