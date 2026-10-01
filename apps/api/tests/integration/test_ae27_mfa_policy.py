"""AE27 (M2-04, M21-09): second factor policy per tenant (docs/rules/M2-04.md).

Expected results: without a stored policy the second factor stays voluntary for everybody
(operator decision M2-01, nobody is forced to set up a factor); a tenant that chooses
``all_staff`` (set explicitly in these tests) makes it mandatory for every CRM role, the portal
role not; a covered user without a factor is asked to set up TOTP at the next login (no session
before, no lockout, running sessions stay); a setup token is neither an MFA step token nor
usable once a factor exists; the last factor of a covered user cannot be removed; the policy
endpoints are tenant separated, need ``tenant_settings`` rights and validate their input; the
magic link login hands over to the TOTP setup when the portal switch is on.
"""

import asyncio
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from mhvp.core import crypto
from mhvp.core.auth import mfa_policy, tokens
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.portal import magic_link
from mhvp.portal.models import MagicLoginLink
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, _settings, bearer
from tests.webauthn_fake import FakeAuthenticator

pytestmark = pytest.mark.integration
A = "/api/v1/auth"
POLICY = f"{A}/mfa-policy"
RUN = uuid.uuid4().hex[:8]
RP, ORIGIN = "testserver", "http://testserver"


def _cfg(database: Database, redis_url: str) -> Any:
    return _settings(
        database, redis_url, webauthn_enabled=True, webauthn_rp_id=RP, webauthn_origins=[ORIGIN]
    )


@dataclass
class Tenant:
    id: uuid.UUID
    emails: dict[str, str]


def _tenant(settings: Any, roles: dict[str, str], mode: str | None = None) -> Tenant:
    """A fresh tenant per test (no shared state between tests) with one user per role.

    ``mode=None`` leaves the tenant without a policy row (the default, voluntary); tests that
    need the obligation pass ``mode="all_staff"`` and so set the policy explicitly."""

    async def build() -> Tenant:
        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        tag = uuid.uuid4().hex[:6]
        try:
            tenant_id, _ = await services.provision_tenant(
                factory, slug=f"ae27-{RUN}-{tag}", name=f"AE27 {RUN} {tag}"
            )
            emails: dict[str, str] = {}
            for name, role in roles.items():
                email = f"ae27-{name}-{tag}-{RUN}@example.org"
                uid = await services.create_user(
                    factory, email=email, display_name=name, password=PASSWORD
                )
                await services.add_member(
                    factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
                )
                emails[name] = email
            if mode is not None:
                async with tenant_transaction(factory, tenant_id) as session:
                    await mfa_policy.store_policy(
                        session,
                        tenant_id=tenant_id,
                        actor_user_id=None,
                        crm_mode=mode,
                        crm_role_codes=[],
                        portal_required=False,
                    )
            return Tenant(tenant_id, emails)
        finally:
            await engine.dispose()

    return asyncio.run(build())


@pytest.fixture
def settings(database: Database, redis_url: str) -> Any:
    return _cfg(database, redis_url)


@pytest.fixture
def client(settings: Any) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _code(secret: str, offset: int = 0) -> str:
    totp = pyotp.TOTP(secret)
    return totp.generate_otp(int(time.time() // totp.interval) + offset)


def _login(client: TestClient, email: str) -> dict[str, Any]:
    step = client.post(f"{A}/login", json={"email": email, "password": PASSWORD})
    assert step.status_code == 200, step.text
    return dict(step.json())


def _enrol(client: TestClient, email: str) -> tuple[dict[str, Any], str]:
    """Login of a covered user without a factor: setup step, then the session."""
    step = _login(client, email)
    assert step["status"] == "mfa_setup_required", step
    token = step["mfa_setup_token"]
    start = client.post(f"{A}/mfa/setup/start", json={"mfa_setup_token": token})
    assert start.status_code == 200, start.text
    secret = start.json()["secret"]
    done = client.post(
        f"{A}/mfa/setup/confirm", json={"mfa_setup_token": token, "code": _code(secret)}
    )
    assert done.status_code == 200, done.text
    return dict(done.json()), secret


def _put(client: TestClient, h: dict[str, str], **body: Any) -> Any:
    payload = {"crm_mode": "voluntary", "crm_role_codes": [], "portal_required": False} | body
    return client.put(POLICY, json=payload, headers=h)


def test_default_without_policy_row_is_voluntary_and_forces_nobody(
    client: TestClient, settings: Any
) -> None:
    """Operator decision M2-01 stays the default: no setup step, no obligation, no stored row."""
    world = _tenant(settings, {"admin": "tenant_admin", "clerk": "standard"})
    sessions: dict[str, dict[str, str]] = {}
    for name, email in world.emails.items():
        step = _login(client, email)
        assert step["status"] == "ok", step
        assert step["mfa_setup_token"] is None
        assert step["mfa_token"] is None
        assert step["access_token"]
        sessions[name] = bearer(step)
        me = client.get(f"{A}/me", headers=sessions[name]).json()
        assert (me["totp_enabled"], me["mfa_required"]) == (False, False)

    default = client.get(POLICY, headers=sessions["admin"])
    assert default.status_code == 200, default.text
    body = default.json()
    assert (body["crm_mode"], body["crm_role_codes"], body["portal_required"], body["stored"]) == (
        "voluntary",
        [],
        False,
        False,
    )

    # The voluntary second factor of M2-01 still works: switch on by the user, off again.
    setup = client.post(f"{A}/totp/setup", headers=sessions["clerk"])
    assert setup.status_code == 200, setup.text
    confirmed = client.post(
        f"{A}/totp/confirm", json={"code": _code(setup.json()["secret"])}, headers=sessions["clerk"]
    )
    assert confirmed.status_code == 204, confirmed.text
    off = client.post(
        f"{A}/totp/disable", json={"current_password": PASSWORD}, headers=sessions["clerk"]
    )
    assert off.status_code == 204, off.text


def test_all_staff_policy_asks_staff_for_setup_at_next_login(
    client: TestClient, settings: Any
) -> None:
    world = _tenant(settings, {"admin": "tenant_admin"}, mode="all_staff")
    email = world.emails["admin"]
    step = _login(client, email)
    assert step["status"] == "mfa_setup_required"
    assert step["access_token"] is None
    assert step["refresh_token"] is None
    token = step["mfa_setup_token"]
    assert token
    assert step["mfa_token"] is None

    # The setup token is no MFA step token, and garbage is no setup token.
    wrong_kind = client.post(f"{A}/mfa/verify", json={"mfa_token": token, "code": "123456"})
    assert wrong_kind.status_code == 401
    assert (
        client.post(f"{A}/mfa/setup/start", json={"mfa_setup_token": "x" * 20}).status_code == 401
    )
    assert client.post(f"{A}/mfa/setup/start", json={}).status_code == 422

    start = client.post(f"{A}/mfa/setup/start", json={"mfa_setup_token": token})
    assert start.status_code == 200, start.text
    secret = start.json()["secret"]
    assert start.json()["otpauth_uri"].startswith("otpauth://totp/")
    right = _code(secret)
    bad = "000000" if right != "000000" else "111111"
    wrong = client.post(f"{A}/mfa/setup/confirm", json={"mfa_setup_token": token, "code": bad})
    assert wrong.status_code == 401
    done = client.post(f"{A}/mfa/setup/confirm", json={"mfa_setup_token": token, "code": right})
    assert done.status_code == 200, done.text
    assert done.json()["tenant_id"] == str(world.id)
    h = bearer(done.json())
    me = client.get(f"{A}/me", headers=h).json()
    assert me["totp_enabled"] is True
    assert me["mfa_required"] is True

    # Once a factor exists the setup token is worthless; the next login asks for the factor.
    again = client.post(f"{A}/mfa/setup/start", json={"mfa_setup_token": token})
    assert again.status_code == 401
    next_step = _login(client, email)
    assert next_step["status"] == "mfa_required"
    assert next_step["mfa_methods"] == ["totp"]
    # A plain MFA token never opens the setup step.
    assert (
        client.post(
            f"{A}/mfa/setup/start", json={"mfa_setup_token": next_step["mfa_token"]}
        ).status_code
        == 401
    )

    # The only factor of a covered user stays.
    off = client.post(f"{A}/totp/disable", json={"current_password": PASSWORD}, headers=h)
    assert off.status_code == 409, off.text
    assert off.json()["code"] == "MHVP-AUTH-0015"


def test_running_sessions_stay_and_voluntary_restores_m2_01(
    client: TestClient, settings: Any
) -> None:
    world = _tenant(settings, {"admin": "tenant_admin", "clerk": "standard"}, mode="all_staff")
    h, _secret = _enrol(client, world.emails["admin"])
    admin = bearer(h)
    # Voluntary: password alone is enough again (operator decision M2-01).
    assert _put(client, admin, crm_mode="voluntary").status_code == 200
    clerk = _login(client, world.emails["clerk"])
    assert clerk["status"] == "ok"
    assert client.get(f"{A}/me", headers=bearer(clerk)).json()["mfa_required"] is False

    # Switching the obligation on does not end the running session (refresh still works).
    assert _put(client, admin, crm_mode="all_staff").status_code == 200
    refreshed = client.post(f"{A}/refresh", json={"refresh_token": clerk["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert client.get(f"{A}/me", headers=bearer(refreshed.json())).json()["mfa_required"] is True
    # The next login asks for the setup.
    assert _login(client, world.emails["clerk"])["status"] == "mfa_setup_required"

    # Under voluntary the admin may switch TOTP off again.
    assert _put(client, admin, crm_mode="voluntary").status_code == 200
    off = client.post(f"{A}/totp/disable", json={"current_password": PASSWORD}, headers=admin)
    assert off.status_code == 204, off.text


def test_roles_mode_covers_only_listed_roles(client: TestClient, settings: Any) -> None:
    world = _tenant(
        settings,
        {"admin": "tenant_admin", "clerk": "standard", "second": "administrator"},
        mode="all_staff",
    )
    admin = bearer(_enrol(client, world.emails["admin"])[0])
    stored = _put(client, admin, crm_mode="roles", crm_role_codes=["administrator"])
    assert stored.status_code == 200, stored.text
    assert stored.json()["crm_role_codes"] == ["administrator"]
    assert stored.json()["stored"] is True
    assert _login(client, world.emails["clerk"])["status"] == "ok"
    assert _login(client, world.emails["second"])["status"] == "mfa_setup_required"


def test_policy_endpoints_permissions_validation_and_tenant_separation(
    client: TestClient, settings: Any
) -> None:
    world = _tenant(settings, {"admin": "tenant_admin", "reader": "read_only"})
    other = _tenant(settings, {"admin": "tenant_admin"})
    admin = bearer(_login(client, world.emails["admin"]))
    other_admin = bearer(_login(client, other.emails["admin"]))

    default = client.get(POLICY, headers=admin)
    assert default.status_code == 200, default.text
    body = default.json()
    assert (body["crm_mode"], body["portal_required"], body["stored"]) == (
        "voluntary",
        False,
        False,
    )
    assert "tenant_admin" in body["available_role_codes"]
    assert "portal_user" not in body["available_role_codes"]

    # Validation.
    assert _put(client, admin, crm_mode="roles", crm_role_codes=[]).status_code == 422
    assert _put(client, admin, crm_mode="roles", crm_role_codes=["nope"]).status_code == 422
    assert _put(client, admin, crm_mode="roles", crm_role_codes=["portal_user"]).status_code == 422
    assert _put(client, admin, crm_mode="bogus").status_code == 422
    assert _put(client, admin, unexpected=True).status_code == 422
    assert client.get(f"{POLICY}?filter[x]=1", headers=admin).status_code == 422

    # Permissions: reading needs tenant_settings:read, changing tenant_settings:update.
    assert client.get(POLICY).status_code == 401
    reader = bearer(_login(client, world.emails["reader"]))
    assert client.get(POLICY, headers=reader).status_code == 200
    assert _put(client, reader, crm_mode="voluntary").status_code == 403

    # Tenant separation: the other tenant's change leaves this one on the default.
    changed = _put(client, other_admin, crm_mode="all_staff", portal_required=True)
    assert changed.status_code == 200, changed.text
    assert client.get(POLICY, headers=other_admin).json()["crm_mode"] == "all_staff"
    own = client.get(POLICY, headers=admin).json()
    assert (own["crm_mode"], own["portal_required"], own["stored"]) == ("voluntary", False, False)
    assert _login(client, world.emails["reader"])["status"] == "ok"


def _portal_account(client: TestClient, admin: dict[str, str], name: str) -> tuple[str, str]:
    contact = client.post(
        "/api/v1/contacts", json={"kind": "company", "company_name": name}, headers=admin
    )
    assert contact.status_code == 201, contact.text
    email = f"ae27-portal-{uuid.uuid4().hex[:6]}-{RUN}@example.org"
    inv = client.post(
        "/api/v1/portal-admin/accounts",
        json={"contact_id": contact.json()["id"], "email": email, "display_name": name},
        headers=admin,
    )
    assert inv.status_code == 201, inv.text
    accepted = client.post(
        "/api/v1/portal/invitations/accept",
        json={"token": inv.json()["invitation_token"], "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return inv.json()["id"], email


def _link(settings: Any, tenant_id: uuid.UUID, account_id: str) -> str:
    async def insert() -> str:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            secret = tokens.new_opaque_secret()
            async with tenant_transaction(factory, tenant_id) as session:
                session.add(
                    MagicLoginLink(
                        tenant_id=tenant_id,
                        account_id=uuid.UUID(account_id),
                        token_hash=tokens.sha256_hex(secret),
                        expires_at=datetime.now(UTC) + timedelta(minutes=15),
                    )
                )
            return f"{tenant_id.hex}.{secret}"
        finally:
            await engine.dispose()

    return asyncio.run(insert())


def test_portal_role_optional_by_default_and_switch_covers_magic_link(
    client: TestClient, settings: Any
) -> None:
    world = _tenant(settings, {"admin": "tenant_admin"})
    admin = bearer(_login(client, world.emails["admin"]))
    account_id, email = _portal_account(client, admin, f"AE27 Portal {RUN}")
    # Default: the portal role keeps the optional second factor (section 14).
    assert _login(client, email)["status"] == "ok"
    first = client.post(
        "/api/v1/portal/magic-link/consume", json={"token": _link(settings, world.id, account_id)}
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "ok"

    # Portal switch on (staff stay voluntary): password and magic link both hand over to the setup.
    assert _put(client, admin, crm_mode="voluntary", portal_required=True).status_code == 200
    assert _login(client, world.emails["admin"])["status"] == "ok"
    portal_user = bearer(first.json())
    assert client.get(POLICY, headers=portal_user).status_code == 403
    assert _login(client, email)["status"] == "mfa_setup_required"
    consumed = client.post(
        "/api/v1/portal/magic-link/consume", json={"token": _link(settings, world.id, account_id)}
    )
    assert consumed.status_code == 200, consumed.text
    out = consumed.json()
    assert out["status"] == "mfa_setup_required"
    assert out["access_token"] is None
    assert tokens.decode_mfa_setup_token(settings, out["mfa_setup_token"])[1] == world.id

    # Service layer: the same hand over, the step token names the tenant.
    service_token = _link(settings, world.id, account_id)

    async def service_step() -> magic_link.LinkResult:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        redis = Redis.from_url(settings.redis_url.get_secret_value())
        try:
            return await magic_link.consume_link(
                factory,
                settings,
                redis,
                token=service_token,
                user_agent=None,
                portal_url=None,
            )
        finally:
            await redis.aclose()
            await engine.dispose()

    result = asyncio.run(service_step())
    assert result.status == "mfa_setup_required"
    assert result.issued is None
    assert result.step_token is not None

    # After the setup the magic link asks for the TOTP code with the tenant in the token.
    setup_token = out["mfa_setup_token"]
    start = client.post(f"{A}/mfa/setup/start", json={"mfa_setup_token": setup_token})
    assert start.status_code == 200, start.text
    done = client.post(
        f"{A}/mfa/setup/confirm",
        json={"mfa_setup_token": setup_token, "code": _code(start.json()["secret"])},
    )
    assert done.status_code == 200, done.text
    assert done.json()["tenant_id"] == str(world.id)
    totp_step = client.post(
        "/api/v1/portal/magic-link/consume", json={"token": _link(settings, world.id, account_id)}
    ).json()
    assert totp_step["status"] == "mfa_required"
    assert tokens.mfa_token_tenant(settings, totp_step["mfa_token"]) == world.id


def _register_passkey(client: TestClient, h: dict[str, str], fake: FakeAuthenticator) -> str:
    opts = client.post(f"{A}/webauthn/register/options", json={"passwordless": False}, headers=h)
    assert opts.status_code == 200, opts.text
    body = fake.create(opts.json()["public_key"]) | {
        "challenge_id": opts.json()["challenge_id"],
        "label": "AE27",
    }
    done = client.post(f"{A}/webauthn/register/verify", json=body, headers=h)
    assert done.status_code == 201, done.text
    return str(done.json()["id"])


def test_passkey_counts_as_factor_and_last_one_stays(client: TestClient, settings: Any) -> None:
    world = _tenant(settings, {"admin": "tenant_admin", "clerk": "standard"})
    admin = bearer(_login(client, world.emails["admin"]))
    clerk = bearer(_login(client, world.emails["clerk"]))
    credential = _register_passkey(client, clerk, FakeAuthenticator(RP, ORIGIN))
    assert _put(client, admin, crm_mode="all_staff").status_code == 200

    # A passkey is a second factor: no setup step, the usual MFA step.
    step = _login(client, world.emails["clerk"])
    assert step["status"] == "mfa_required"
    assert step["mfa_methods"] == ["webauthn"]
    # The only factor of a covered user stays; under voluntary it may go.
    refused = client.delete(f"{A}/webauthn/credentials/{credential}", headers=clerk)
    assert refused.status_code == 409, refused.text
    assert _put(client, admin, crm_mode="voluntary").status_code == 200
    assert client.delete(f"{A}/webauthn/credentials/{credential}", headers=clerk).status_code == 204
