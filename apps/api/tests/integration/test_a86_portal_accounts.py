"""A86 (M21, 14): the CRM reads the portal accounts of a contact via
GET /portal-admin/accounts?contact_id=... (contacts:read). The answer carries e-mail, status of
the model (invited, active), lock indication, invitation and login times and never a secret,
hash or invitation code. Tenant separation by RLS: a foreign contact yields an empty list."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
PA = "/api/v1/portal-admin"
FORBIDDEN_KEYS = {"invitation_hash", "invitation_token", "password_hash", "totp_secret"}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pa-{RUN}", name=f"Zugang A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pb-{RUN}", name=f"Zugang B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("a86admin", a), ("a86other", b)):
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


def test_a86_contact_portal_accounts(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a86admin"))
    party, _ = _party(client, h, "Zugang")
    contact = _contact_of(client, h, party)

    # Happy path: no account yet, then invited, then active after accepting the invitation.
    assert _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h)) == []
    inv = _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("a86res"), "display_name": "R"},
            headers=h,
        ),
        201,
    )
    rows = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == inv["id"]
    assert row["contact_id"] == contact
    assert row["email"] == world.email("a86res")
    assert row["status"] == "invited"
    assert row["locked"] is False
    assert row["invited_at"]
    assert row["invitation_expires_at"]
    assert row["activated_at"] is None
    assert row["last_login_at"] is None
    assert not FORBIDDEN_KEYS & set(row)
    assert inv["invitation_token"] not in str(row)

    _ok(
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": inv["invitation_token"], "password": PASSWORD},
        )
    )
    portal = bearer(login(client, world, "a86res"))
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]
    assert row["status"] == "active"
    assert row["activated_at"] is not None
    # last_login_at is written by the platform only on a TOTP verified login
    # (mhvp.core.auth.service.verify_totp); a password only login leaves it empty (open point).
    assert "last_login_at" in row

    # Permission: a portal user has no CRM right contacts:read.
    assert (
        client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=portal).status_code
        == 403
    )
    assert client.get(f"{PA}/accounts", params={"contact_id": contact}).status_code == 401
    # Validation: contact_id is mandatory and must be a UUID.
    assert client.get(f"{PA}/accounts", headers=h).status_code == 422
    assert client.get(f"{PA}/accounts", params={"contact_id": "x"}, headers=h).status_code == 422

    # Tenant separation: the other tenant sees nothing for the contact of tenant A.
    other = bearer(login(client, world, "a86other"))
    assert _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=other)) == []


def test_a86_second_contact_isolated(client: TestClient, world: World) -> None:
    """A contact with an account and one without: the list is per contact, not per tenant."""
    h = bearer(login(client, world, "a86admin"))
    with_party, _ = _party(client, h, "Mit")
    without_party, _ = _party(client, h, "Ohne")
    with_contact = _contact_of(client, h, with_party)
    without_contact = _contact_of(client, h, without_party)
    _portal_user(client, h, world, "a86mit", with_contact)
    assert (
        len(_ok(client.get(f"{PA}/accounts", params={"contact_id": with_contact}, headers=h))) == 1
    )
    assert (
        _ok(client.get(f"{PA}/accounts", params={"contact_id": without_contact}, headers=h)) == []
    )
