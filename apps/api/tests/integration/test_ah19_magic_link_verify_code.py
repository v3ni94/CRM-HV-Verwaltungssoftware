"""GAG-36: endpoint test of POST /portal/magic-link/verify-code (M21-01, section 14).

Exercises the HTTP endpoint (not only the service layer as ``test_m21_magic_link`` does):
correct code issues a session, a wrong code is refused without consuming the code, an expired
code and a code from another tenant are refused, the code is single use, malformed input is
422 and the anonymous rate limit answers 429. The mailed code is never returned by the API
(rule 0.1.13), so the test sets a known code hash directly on the link row."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.auth import tokens
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.portal.models import MagicLoginLink
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
RUN = "9-" + uuid.uuid4().hex[:6]
CODE = "482915"


async def _world(settings: Any) -> tuple[World, uuid.UUID, uuid.UUID]:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ah19-a-{RUN}", name=f"AH19 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ah19-b-{RUN}", name=f"AH19 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email(f"ah19admin-{RUN}"), display_name="ah19", password=PASSWORD
        )
        world.users[f"ah19admin-{RUN}"] = uid
        for tenant in (a, b):
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
            )
        return world, a, b
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> tuple[World, uuid.UUID, uuid.UUID]:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def app_settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


@pytest.fixture
def client(app_settings: Any) -> Any:
    with TestClient(create_app(app_settings)) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _account_with_2fa(client: TestClient, w: World, tenant_id: uuid.UUID, name: str) -> str:
    h = bearer(login(client, w, f"ah19admin-{RUN}", tenant_id=tenant_id))
    contact = _ok(
        client.post("/api/v1/contacts", json={"kind": "company", "company_name": name}, headers=h),
        201,
    )
    email = f"{name.lower().replace(' ', '-')}-{RUN}@example.org"
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
    resp = client.patch(
        f"{PA}/accounts/{inv['id']}/security", json={"magic_link_2fa": True}, headers=h
    )
    assert resp.status_code == 204, resp.text
    return str(inv["id"])


def _consumed_link(
    client: TestClient, settings: Any, tenant_id: uuid.UUID, account_id: str, *, expired: bool
) -> uuid.UUID:
    """Inserts a link, consumes it over the API (status code_required) and sets a known code."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    secret = tokens.new_opaque_secret()

    async def insert() -> None:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                session.add(
                    MagicLoginLink(
                        tenant_id=tenant_id,
                        account_id=uuid.UUID(account_id),
                        token_hash=tokens.sha256_hex(secret),
                        expires_at=datetime.now(UTC) + timedelta(minutes=15),
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(insert())
    out = _ok(client.post(f"{P}/magic-link/consume", json={"token": f"{tenant_id.hex}.{secret}"}))
    assert out["status"] == "code_required"
    assert out["access_token"] is None
    link_id = uuid.UUID(out["link_id"])

    async def set_code() -> None:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                row = await session.get(MagicLoginLink, link_id)
                assert row is not None
                row.code_hash = tokens.sha256_hex(CODE)
                delta = timedelta(minutes=-1) if expired else timedelta(minutes=10)
                row.code_expires_at = datetime.now(UTC) + delta
        finally:
            await engine.dispose()

    asyncio.run(set_code())
    return link_id


def _verify(client: TestClient, tenant_id: uuid.UUID, link_id: uuid.UUID, code: str) -> Any:
    return client.post(
        f"{P}/magic-link/verify-code",
        json={"tenant_id": str(tenant_id), "link_id": str(link_id), "code": code},
    )


def test_verify_code_wrong_then_correct_then_reused(
    client: TestClient, world: tuple[World, uuid.UUID, uuid.UUID], app_settings: Any
) -> None:
    w, a, _b = world
    account_id = _account_with_2fa(client, w, a, "AH19 Code")
    link_id = _consumed_link(client, app_settings, a, account_id, expired=False)

    wrong = _verify(client, a, link_id, "000000")
    assert wrong.status_code == 401, wrong.text
    assert wrong.json()["code"] == "MHVP-AUTH-0011"

    out = _ok(_verify(client, a, link_id, CODE))
    assert out["status"] == "ok"
    assert out["access_token"]
    assert "code" not in out  # the code is never echoed

    again = _verify(client, a, link_id, CODE)
    assert again.status_code == 401, again.text


def test_verify_code_expired_and_other_tenant(
    client: TestClient, world: tuple[World, uuid.UUID, uuid.UUID], app_settings: Any
) -> None:
    w, a, b = world
    account_id = _account_with_2fa(client, w, a, "AH19 Abgelaufen")
    expired = _consumed_link(client, app_settings, a, account_id, expired=True)
    resp = _verify(client, a, expired, CODE)
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] == "MHVP-AUTH-0011"

    valid = _consumed_link(client, app_settings, a, account_id, expired=False)
    # The same link id under another tenant is invisible (RLS), so it is refused.
    other = _verify(client, b, valid, CODE)
    assert other.status_code == 401, other.text
    # Unknown link id.
    assert _verify(client, a, uuid.uuid4(), CODE).status_code == 401
    # Still usable in its own tenant afterwards.
    assert _ok(_verify(client, a, valid, CODE))["status"] == "ok"


def test_verify_code_validation(client: TestClient) -> None:
    bad = [
        {"tenant_id": str(uuid.uuid4()), "link_id": str(uuid.uuid4()), "code": "12"},
        {"tenant_id": "x", "link_id": str(uuid.uuid4()), "code": CODE},
        {"tenant_id": str(uuid.uuid4()), "code": CODE},
    ]
    for body in bad:
        assert client.post(f"{P}/magic-link/verify-code", json=body).status_code == 422


def test_verify_code_rate_limited(database: Database, redis_url: str) -> None:
    settings = base_settings(
        database,
        redis_url,
        rate_limit_enabled=True,
        rate_limit_per_minute_anonymous=3,
        rate_limit_trust_forwarded_for=True,
    )
    address = f"198.51.100.{uuid.uuid4().int % 250 + 1}"
    body = {"tenant_id": str(uuid.uuid4()), "link_id": str(uuid.uuid4()), "code": CODE}
    with TestClient(create_app(settings)) as rl_client:
        headers = {"X-Forwarded-For": address}
        codes = [
            rl_client.post(f"{P}/magic-link/verify-code", json=body, headers=headers).status_code
            for _ in range(5)
        ]
    assert 429 in codes, codes
    first = codes.index(429)
    assert all(c == 401 for c in codes[:first]), codes
    assert all(c == 429 for c in codes[first:]), codes
    assert first == 3


def test_verify_code_locked_after_five_failures(
    client: TestClient, world: tuple[World, uuid.UUID, uuid.UUID], app_settings: Any
) -> None:
    """GAI-310: five wrong codes invalidate code and link; the correct code is then refused
    and every failure is recorded as an event without the code."""
    from sqlalchemy import select

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.events import DomainEvent

    w, a, _b = world
    account_id = _account_with_2fa(client, w, a, "AH19 Sperre")
    link_id = _consumed_link(client, app_settings, a, account_id, expired=False)
    for _ in range(5):
        resp = _verify(client, a, link_id, "000001")
        assert resp.status_code == 401, resp.text
    assert _verify(client, a, link_id, CODE).status_code == 401

    async def check() -> None:
        engine = create_app_engine(app_settings)
        try:
            async with tenant_transaction(create_session_factory(engine), a) as session:
                row = await session.get(MagicLoginLink, link_id)
                assert row is not None
                assert row.code_failed_attempts == 5
                assert row.code_used_at is None
                assert row.expires_at <= datetime.now(UTC)
                events = (
                    await session.scalars(
                        select(DomainEvent).where(
                            DomainEvent.entity_id == link_id,
                            DomainEvent.type == "portal.magic_link.code_failed",
                        )
                    )
                ).all()
                assert len(events) == 5
                assert any(e.payload.get("locked") for e in events)
                assert all("code" not in e.payload for e in events)
        finally:
            await engine.dispose()

    asyncio.run(check())
