"""U04-02: pure portal accounts (all active memberships only with role portal_user) may use
passkeys only as second factor; passwordless registration and sign in answer 403
MHVP-AUTH-0014. Staff accounts stay unaffected."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    _settings,
    bearer,
    login_password_only,
)
from tests.integration.test_s16_webauthn_login import _options, _register
from tests.webauthn_fake import FakeAuthenticator

pytestmark = pytest.mark.integration
A = "/api/v1/auth"
RP, ORIGIN = "testserver", "http://testserver"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"v02-{RUN}", name=f"V02 A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in (
            ("v02portal", "portal_user"),
            ("v02staff", "standard"),
            ("v02mixed", "portal_user"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


def _cfg(database: Database, redis_url: str) -> Any:
    return _settings(
        database, redis_url, webauthn_enabled=True, webauthn_rp_id=RP, webauthn_origins=[ORIGIN]
    )


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_cfg(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_cfg(database, redis_url))) as c:
        yield c


def test_portal_account_cannot_register_passwordless(client: TestClient, world: World) -> None:
    h = bearer(login_password_only(client, world, "v02portal"))
    for path in ("register/options",):
        refused = client.post(f"{A}/webauthn/{path}", json={"passwordless": True}, headers=h)
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "MHVP-AUTH-0014"
    # Second factor registration stays possible.
    fake = FakeAuthenticator(RP, ORIGIN)
    _register(client, h, fake, passwordless=False)
    # Validation: no token is 401.
    assert (
        client.post(f"{A}/webauthn/register/options", json={"passwordless": True}).status_code
        == 401
    )


def test_register_verify_blocks_bypass_by_stale_challenge(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """A passwordless challenge issued before the account became portal only cannot be used."""
    h = bearer(login_password_only(client, world, "v02mixed"))
    # Issued while the user is not yet restricted: switch roles to standard first.
    asyncio.run(_set_roles(_cfg(database, redis_url), world, "v02mixed", ["standard"]))
    opts = client.post(f"{A}/webauthn/register/options", json={"passwordless": True}, headers=h)
    assert opts.status_code == 200, opts.text
    asyncio.run(_set_roles(_cfg(database, redis_url), world, "v02mixed", ["portal_user"]))
    fake = FakeAuthenticator(RP, ORIGIN)
    body = fake.create(opts.json()["public_key"]) | {
        "challenge_id": opts.json()["challenge_id"],
        "label": "x",
    }
    done = client.post(f"{A}/webauthn/register/verify", json=body, headers=h)
    assert done.status_code == 403, done.text
    assert done.json()["code"] == "MHVP-AUTH-0014"


async def _set_roles(settings: Any, world: World, name: str, codes: list[str]) -> None:
    from sqlalchemy import select

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import platform_transaction
    from mhvp.platform.models import Membership

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            mid = await session.scalar(
                select(Membership.id).where(Membership.user_id == world.users[name])
            )
        await services.set_member_roles(
            factory,
            tenant_id=world.tenant_a,
            membership_id=mid,
            role_codes=codes,
            actor_user_id=None,
        )
    finally:
        await engine.dispose()


def test_staff_passwordless_unaffected_and_portal_login_blocked(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    h = bearer(login_password_only(client, world, "v02staff"))
    _register(client, h, fake, passwordless=True)
    # Account is later reduced to portal only: passwordless sign in is refused with 403.
    asyncio.run(_set_roles(_cfg(database, redis_url), world, "v02staff", ["portal_user"]))
    opts = _options(client, None)
    body = fake.get(opts["public_key"]) | {"challenge_id": opts["challenge_id"]}
    refused = client.post(f"{A}/login/webauthn/verify", json=body)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "MHVP-AUTH-0014"
