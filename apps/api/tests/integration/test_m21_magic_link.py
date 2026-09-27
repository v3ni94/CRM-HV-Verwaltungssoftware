"""M21-01: magic link login for the tenant and owner portal (docs/rules/M21-01.md).

Covers expiry, single use (expiry after use) and tenant separation of the login link and of
the optional e-mail code second factor, plus that the request endpoint never reveals whether an
address has a portal account. The link and the code are exercised at the service layer
(``mhvp.portal.magic_link``) because the API never returns the raw token or code (rule 0.1.13);
the existing password login is unaffected (checked in ``test_m21_portal``)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from mhvp.core.auth import tokens
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.problems import ProblemError
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.portal import magic_link
from mhvp.portal.models import MagicLoginLink
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> tuple[World, uuid.UUID]:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ml-a-{RUN}", name=f"ML A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ml-b-{RUN}", name=f"ML B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("mladmin"), display_name="admin", password=PASSWORD
        )
        world.users["mladmin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        await services.add_member(
            factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world, a
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world_and_tenant(database: Database, redis_url: str) -> tuple[World, uuid.UUID]:
    import asyncio

    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Any:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _activated_account(
    client: TestClient, h: dict[str, str], world: World, name: str
) -> tuple[str, str]:
    """A portal account of the current tenant, invited and activated (returns account_id and
    e-mail); the invitation code itself is not needed for the magic link (a separate login)."""
    contact = _ok(
        client.post("/api/v1/contacts", json={"kind": "company", "company_name": name}, headers=h),
        201,
    )
    email = world.email(name.lower().replace(" ", "-"))
    inv = _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact["id"], "email": email, "display_name": name},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    return inv["id"], email


@pytest.fixture
def app_settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


def _factory(settings: Any) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    return create_session_factory(engine), engine


async def _insert_link(
    factory: Any,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    secret: str,
    expires_at: datetime,
    used_at: datetime | None = None,
) -> uuid.UUID:
    async with tenant_transaction(factory, tenant_id) as session:
        row = MagicLoginLink(
            tenant_id=tenant_id,
            account_id=account_id,
            token_hash=tokens.sha256_hex(secret),
            expires_at=expires_at,
            used_at=used_at,
        )
        session.add(row)
        await session.flush()
        return row.id


def test_magic_link_login_then_expiry_after_use(
    client: TestClient, world_and_tenant: tuple[World, uuid.UUID], app_settings: Any
) -> None:
    world, tenant_id = world_and_tenant
    h = bearer(login(client, world, "mladmin", tenant_id=tenant_id))
    account_id, _email = _activated_account(client, h, world, f"Magic {RUN}")

    async def run() -> None:
        factory, engine = _factory(app_settings)
        redis = Redis.from_url(app_settings.redis_url.get_secret_value())
        try:
            secret = tokens.new_opaque_secret()
            await _insert_link(
                factory,
                tenant_id=tenant_id,
                account_id=uuid.UUID(account_id),
                secret=secret,
                expires_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            token = f"{tenant_id.hex}.{secret}"
            result = await magic_link.consume_link(
                factory, app_settings, redis, token=token, user_agent=None, portal_url=None
            )
            assert result.status == "ok"
            assert result.issued is not None
            assert result.issued.access_token

            # Single use: the same link cannot be redeemed twice (expiry after use).
            with pytest.raises(ProblemError):
                await magic_link.consume_link(
                    factory, app_settings, redis, token=token, user_agent=None, portal_url=None
                )
        finally:
            await redis.aclose()
            await engine.dispose()

    import asyncio

    asyncio.run(run())


def test_magic_link_expired(
    client: TestClient, world_and_tenant: tuple[World, uuid.UUID], app_settings: Any
) -> None:
    world, tenant_id = world_and_tenant
    h = bearer(login(client, world, "mladmin", tenant_id=tenant_id))
    account_id, _email = _activated_account(client, h, world, f"Magic Exp {RUN}")

    async def run() -> None:
        factory, engine = _factory(app_settings)
        redis = Redis.from_url(app_settings.redis_url.get_secret_value())
        try:
            secret = tokens.new_opaque_secret()
            await _insert_link(
                factory,
                tenant_id=tenant_id,
                account_id=uuid.UUID(account_id),
                secret=secret,
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
            token = f"{tenant_id.hex}.{secret}"
            with pytest.raises(ProblemError):
                await magic_link.consume_link(
                    factory, app_settings, redis, token=token, user_agent=None, portal_url=None
                )
        finally:
            await redis.aclose()
            await engine.dispose()

    import asyncio

    asyncio.run(run())


def test_magic_link_tenant_separation(
    client: TestClient, world_and_tenant: tuple[World, uuid.UUID], app_settings: Any
) -> None:
    """A link minted for tenant A cannot be redeemed by pointing the token at tenant B: RLS
    scopes the lookup to the tenant named in the token, so a forged tenant prefix finds nothing
    rather than another tenant's row (6.9.6, tenant separation)."""
    world, tenant_a = world_and_tenant
    tenant_b = world.tenant_b
    h = bearer(login(client, world, "mladmin", tenant_id=tenant_a))
    account_id, _email = _activated_account(client, h, world, f"Magic Tenant {RUN}")

    async def run() -> None:
        factory, engine = _factory(app_settings)
        redis = Redis.from_url(app_settings.redis_url.get_secret_value())
        try:
            secret = tokens.new_opaque_secret()
            await _insert_link(
                factory,
                tenant_id=tenant_a,
                account_id=uuid.UUID(account_id),
                secret=secret,
                expires_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            forged_token = f"{tenant_b.hex}.{secret}"
            with pytest.raises(ProblemError):
                await magic_link.consume_link(
                    factory,
                    app_settings,
                    redis,
                    token=forged_token,
                    user_agent=None,
                    portal_url=None,
                )
            # The genuine token (correct tenant) still works.
            genuine = f"{tenant_a.hex}.{secret}"
            result = await magic_link.consume_link(
                factory, app_settings, redis, token=genuine, user_agent=None, portal_url=None
            )
            assert result.status == "ok"
        finally:
            await redis.aclose()
            await engine.dispose()

    import asyncio

    asyncio.run(run())


def test_magic_link_email_code_second_factor(
    client: TestClient, world_and_tenant: tuple[World, uuid.UUID], app_settings: Any
) -> None:
    world, tenant_id = world_and_tenant
    h = bearer(login(client, world, "mladmin", tenant_id=tenant_id))
    account_id, _email = _activated_account(client, h, world, f"Magic 2FA {RUN}")
    security = client.patch(
        f"{PA}/accounts/{account_id}/security", json={"magic_link_2fa": True}, headers=h
    )
    assert security.status_code == 204, security.text

    async def run() -> None:
        factory, engine = _factory(app_settings)
        redis = Redis.from_url(app_settings.redis_url.get_secret_value())
        try:
            secret = tokens.new_opaque_secret()
            link_id = await _insert_link(
                factory,
                tenant_id=tenant_id,
                account_id=uuid.UUID(account_id),
                secret=secret,
                expires_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            token = f"{tenant_id.hex}.{secret}"
            result = await magic_link.consume_link(
                factory, app_settings, redis, token=token, user_agent=None, portal_url=None
            )
            # The account requires the e-mail code; the link alone never issues a session.
            assert result.status == "code_required"
            assert result.issued is None
            assert result.link_id == link_id

            # Simulate the mailed code (never exposed by the API): set it directly.
            async with tenant_transaction(factory, tenant_id) as session:
                row = await session.get(MagicLoginLink, link_id)
                assert row is not None
                row.code_hash = tokens.sha256_hex("123456")
                row.code_expires_at = datetime.now(UTC) + timedelta(minutes=10)

            issued = await magic_link.verify_code(
                factory,
                app_settings,
                tenant_id=tenant_id,
                link_id=link_id,
                code="123456",
                user_agent=None,
            )
            assert issued.access_token

            # The code is single use too.
            with pytest.raises(ProblemError):
                await magic_link.verify_code(
                    factory,
                    app_settings,
                    tenant_id=tenant_id,
                    link_id=link_id,
                    code="123456",
                    user_agent=None,
                )
        finally:
            await redis.aclose()
            await engine.dispose()

    import asyncio

    asyncio.run(run())


def test_magic_link_request_never_reveals_existence(
    client: TestClient, world_and_tenant: tuple[World, uuid.UUID]
) -> None:
    """The request endpoint answers 204 for an unknown address too (no enumeration, rule
    0.1.13); without a host mapped to a tenant and no explicit tenant_id it is a harmless no-op."""
    resp = client.post(f"{P}/magic-link/request", json={"email": "unknown@example.invalid"})
    assert resp.status_code == 204
    assert resp.text == ""
