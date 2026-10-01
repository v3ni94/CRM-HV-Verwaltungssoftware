"""AA08 (GA02-07): portal account with roles, invited_at and the statuses of 6.1. ``roles``
follow the access grants (owner from an ownership contract), ``invited_at`` is set on the
invitation, an invitation past its expiry reads ``expired`` (derived, the stored value stays
``invited``), an accepted one reads ``active``. A contact without contract has no roles."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.main import create_app
from mhvp.portal.routers import effective_account_status
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok
from tests.integration.test_m21_read_receipts import _db

pytestmark = pytest.mark.integration
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa08a-{RUN}", name=f"AA08 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa08b-{RUN}", name=f"AA08 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("aa08admin", a), ("aa08other", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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


def test_effective_status_is_derived() -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    past, future = now - timedelta(days=1), now + timedelta(days=1)
    free = SimpleNamespace(active=True, locked_until=None)
    locked = SimpleNamespace(active=True, locked_until=future)
    disabled = SimpleNamespace(active=False, locked_until=None)

    def account(status: str, expires: datetime | None) -> Any:
        return SimpleNamespace(status=status, invitation_expires_at=expires)

    assert effective_account_status(account("invited", future), free, now) == "invited"
    assert effective_account_status(account("invited", past), free, now) == "expired"
    assert effective_account_status(account("active", None), free, now) == "active"
    assert effective_account_status(account("active", None), locked, now) == "locked"
    assert effective_account_status(account("active", None), disabled, now) == "locked"
    assert effective_account_status(account("revoked", None), free, now) == "revoked"


def test_portal_account_roles_invited_at_and_expiry(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "aa08admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "814", "name": "AA08 WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    unit = _unit(client, h, prop["id"], "01")
    party, _ = _party(client, h, "AA08Eigentuemer")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    contact = _contact_of(client, h, party)
    before = datetime.now(UTC)
    _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("aa08owner"), "display_name": "o"},
            headers=h,
        ),
        201,
    )
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]
    assert row["roles"] == ["owner"]
    assert row["status"] == "invited"
    assert datetime.fromisoformat(row["invited_at"]) >= before - timedelta(seconds=5)

    async def expire(s: Any) -> None:
        await s.execute(
            text("UPDATE portal_account SET invitation_expires_at = :at WHERE contact_id = :c"),
            {"at": datetime.now(UTC) - timedelta(days=1), "c": uuid.UUID(contact)},
        )

    _db(database, redis_url, world, expire)
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]
    assert row["status"] == "expired"
    assert PASSWORD not in str(row)


def test_contact_without_contract_has_no_roles(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "aa08admin"))
    party, _ = _party(client, h, "AA08Ohne")
    contact = _contact_of(client, h, party)
    _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("aa08none"), "display_name": "n"},
            headers=h,
        ),
        201,
    )
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]
    assert row["roles"] == []
    other = bearer(login(client, world, "aa08other"))
    assert _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=other)) == []
