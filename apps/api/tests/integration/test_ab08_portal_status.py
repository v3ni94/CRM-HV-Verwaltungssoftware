"""AB08 (GA02-07): the status model 6.2 of the portal account is stored, not only derived:
not_invited, invited, active, locked, expired (beat job, idempotent, time travel), revoked, and
last_login_at on login. Own test world with prefix ab08."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok
from tests.integration.test_m21_read_receipts import _db

pytestmark = pytest.mark.integration
PA = "/api/v1/portal-admin"
ALLOWED = {"not_invited", "invited", "active", "locked", "expired", "revoked"}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ab08a-{RUN}", name=f"AB08 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ab08b-{RUN}", name=f"AB08 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("ab08admin"), display_name="ab08", password=PASSWORD
        )
        world.users["ab08admin"] = uid
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


def _row(client: TestClient, h: dict[str, str], contact: str) -> dict[str, Any]:
    return _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]


def _stored(database: Database, redis_url: str, world: World, contact: str) -> str:
    async def get(s: Any) -> str:
        return str(
            await s.scalar(
                text("SELECT status FROM portal_account WHERE contact_id = :c"),
                {"c": uuid.UUID(contact)},
            )
        )

    return str(_db(database, redis_url, world, get))


def _sync(database: Database, redis_url: str, world: World, now: datetime) -> dict[str, int]:
    from mhvp.portal.status import sync_statuses

    async def run(s: Any) -> dict[str, int]:
        return await sync_statuses(s, world.tenant_a, now)

    return dict(_db(database, redis_url, world, run))


def _set(database: Database, redis_url: str, world: World, sql: str, **params: Any) -> None:
    async def run(s: Any) -> None:
        await s.execute(text(sql), params)

    _db(database, redis_url, world, run)


def _user_lock(
    database: Database, redis_url: str, world: World, email: str, until: datetime
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import platform_transaction

    async def run() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with platform_transaction(create_session_factory(engine)) as s:
                await s.execute(
                    text("UPDATE app_user SET locked_until = :u WHERE email = :e"),
                    {"u": until, "e": email},
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_status_lifecycle_is_stored(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "ab08admin"))
    party, _ = _party(client, h, "AB08Zugang")
    contact = _contact_of(client, h, party)
    c = uuid.UUID(contact)

    # not_invited: created without invitation, no token, no invited_at
    created = _ok(
        client.post(
            f"{PA}/accounts",
            json={
                "contact_id": contact,
                "email": world.email("ab08user"),
                "display_name": "u",
                "send_invitation": False,
            },
            headers=h,
        ),
        201,
    )
    assert created["invitation_token"] is None
    assert _stored(database, redis_url, world, contact) == "not_invited"
    # Activation without invitation is impossible
    assert (
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": f"{world.tenant_a.hex}.nothing-valid", "password": PASSWORD},
        ).status_code
        == 422
    )

    # invited: the invitation is sent (second POST for the same contact)
    inv = _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("ab08user"), "display_name": "u"},
            headers=h,
        ),
        201,
    )
    assert _stored(database, redis_url, world, contact) == "invited"
    assert _row(client, h, contact)["invited_at"]

    # expired by job (time travel): not before the expiry, once after, idempotent
    expires = datetime.now(UTC) + timedelta(days=7)
    assert _sync(database, redis_url, world, expires - timedelta(hours=1))["expired"] == 0
    assert _stored(database, redis_url, world, contact) == "invited"
    later = expires + timedelta(days=30)
    assert _sync(database, redis_url, world, later)["expired"] == 1
    assert _stored(database, redis_url, world, contact) == "expired"
    assert _sync(database, redis_url, world, later) == {"expired": 0, "locked": 0, "unlocked": 0}
    assert _stored(database, redis_url, world, contact) in ALLOWED
    # an expired code is refused, a reissue returns the account to invited
    _set(
        database,
        redis_url,
        world,
        "UPDATE portal_account SET invitation_expires_at = :at WHERE contact_id = :c",
        at=datetime.now(UTC) - timedelta(days=1),
        c=c,
    )
    assert (
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": inv["invitation_token"], "password": PASSWORD},
        ).status_code
        == 422
    )
    again = _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("ab08user"), "display_name": "u"},
            headers=h,
        ),
        201,
    )
    assert again["reissued"] is True
    assert _stored(database, redis_url, world, contact) == "invited"

    # active on acceptance; last_login_at on login
    assert _row(client, h, contact)["last_login_at"] is None
    _ok(
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": again["invitation_token"], "password": PASSWORD},
        )
    )
    assert _stored(database, redis_url, world, contact) == "active"
    before = datetime.now(UTC) - timedelta(seconds=5)
    bearer(login(client, world, "ab08user"))
    assert datetime.fromisoformat(_row(client, h, contact)["last_login_at"]) >= before

    # locked while the platform user is locked, active again when the lock lapses
    now = datetime.now(UTC)
    _user_lock(database, redis_url, world, world.email("ab08user"), now + timedelta(hours=1))
    assert _sync(database, redis_url, world, now)["locked"] == 1
    assert _stored(database, redis_url, world, contact) == "locked"
    assert _sync(database, redis_url, world, now)["locked"] == 0
    assert _sync(database, redis_url, world, now + timedelta(hours=2))["unlocked"] == 1
    assert _stored(database, redis_url, world, contact) == "active"

    # revoked is final for the job
    _set(
        database,
        redis_url,
        world,
        "UPDATE portal_account SET status = 'revoked' WHERE contact_id = :c",
        c=c,
    )
    assert _sync(database, redis_url, world, now + timedelta(days=400)) == {
        "expired": 0,
        "locked": 0,
        "unlocked": 0,
    }
    assert _row(client, h, contact)["status"] == "revoked"
