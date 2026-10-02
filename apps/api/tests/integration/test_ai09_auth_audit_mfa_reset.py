"""AI09 (GAH-302, GAH-301): security events of the login flow and four eyes reset of the
second factor by tenant administrators.

Expected results: a successful login, a wrong password, the lockout after the last allowed failure, a
password change, TOTP on and off and a revoked session each write exactly one domain event of
the documented type in the user's tenant, without password or code in the payload; a wrong
password for an unknown email writes nothing. The reset is refused while the switch
``mfa_admin_reset_enabled`` is off (409), needs ``members:update`` (403), is tenant separated
(404), refuses approval by the requester (409) and, after approval by a second administrator,
switches TOTP off so that the next login is password only, notifies the user and records
``auth.mfa_reset``.
"""

import asyncio
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.auth import passwords
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.models import Notification
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, _settings, bearer

pytestmark = pytest.mark.integration
A = "/api/v1/auth"
R = f"{A}/mfa-reset"
RUN = uuid.uuid4().hex[:8]


@dataclass
class World:
    tenant_id: uuid.UUID
    emails: dict[str, str]
    users: dict[str, uuid.UUID]


def _world(settings: Any, roles: dict[str, str]) -> World:
    async def build() -> World:
        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        tag = uuid.uuid4().hex[:6]
        try:
            tenant_id, _ = await services.provision_tenant(
                factory, slug=f"9-ai09-{RUN}-{tag}", name=f"AI09 {RUN} {tag}"
            )
            emails: dict[str, str] = {}
            users: dict[str, uuid.UUID] = {}
            for name, role in roles.items():
                email = f"ai09-{name}-{tag}-{RUN}@example.org"
                uid = await services.create_user(
                    factory, email=email, display_name=name, password=PASSWORD
                )
                await services.add_member(
                    factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
                )
                emails[name], users[name] = email, uid
            return World(tenant_id, emails, users)
        finally:
            await engine.dispose()

    return asyncio.run(build())


def _rows(settings: Any, tenant_id: uuid.UUID, model: Any, **where: Any) -> list[Any]:
    async def run() -> list[Any]:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as s:
                stmt = select(model)
                for key, value in where.items():
                    stmt = stmt.where(getattr(model, key) == value)
                return list((await s.scalars(stmt)).all())
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _events(settings: Any, world: World, type_: str, user: str) -> list[DomainEvent]:
    return _rows(settings, world.tenant_id, DomainEvent, type=type_, entity_id=world.users[user])


@pytest.fixture
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


@pytest.fixture
def client(settings: Any) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _login(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    return client.post(f"{A}/login", json={"email": email, "password": password})


def _session(client: TestClient, email: str) -> dict[str, str]:
    step = _login(client, email)
    assert step.status_code == 200, step.text
    assert step.json()["status"] == "ok", step.json()
    return bearer(step.json())


def _enable_totp(client: TestClient, h: dict[str, str]) -> str:
    secret = client.post(f"{A}/totp/setup", headers=h).json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert client.post(f"{A}/totp/confirm", json={"code": code}, headers=h).status_code == 204
    return secret


def test_login_events_without_secrets(client: TestClient, settings: Any) -> None:
    world = _world(settings, {"admin": "tenant_admin"})
    email = world.emails["admin"]
    h = _session(client, email)
    assert len(_events(settings, world, "auth.login_succeeded", "admin")) == 1
    assert _login(client, email, "falsch-123456").status_code == 401
    failed = _events(settings, world, "auth.login_failed", "admin")
    assert len(failed) == 1
    assert failed[0].payload == {"factor": "password", "reason": "wrong_password"}
    assert "falsch" not in json.dumps(failed[0].payload)
    # Unknown email: no tenant, nothing recorded, no error.
    assert _login(client, f"ai09-unknown-{RUN}@example.org").status_code == 401

    secret = _enable_totp(client, h)
    assert len(_events(settings, world, "auth.totp_enabled", "admin")) == 1
    off = client.post(f"{A}/totp/disable", json={"current_password": PASSWORD}, headers=h)
    assert off.status_code == 204, off.text
    assert len(_events(settings, world, "auth.totp_disabled", "admin")) == 1
    for event in _events(settings, world, "auth.totp_enabled", "admin"):
        assert secret not in json.dumps(event.payload)

    families = client.get(f"{A}/sessions", headers=h).json()
    assert families
    gone = client.delete(f"{A}/sessions/{families[0]['family_id']}", headers=h)
    assert gone.status_code == 204
    assert len(_events(settings, world, "auth.session_revoked", "admin")) == 1

    h2 = _session(client, email)
    new = PASSWORD + "-Neu9"
    changed = client.post(
        f"{A}/password", json={"current_password": PASSWORD, "new_password": new}, headers=h2
    )
    assert changed.status_code == 204, changed.text
    events = _events(settings, world, "auth.password_changed", "admin")
    assert len(events) == 1
    assert PASSWORD not in json.dumps(events[0].payload)


def test_lockout_event(client: TestClient, settings: Any) -> None:
    world = _world(settings, {"clerk": "standard"})
    for _ in range(passwords.MAX_FAILED_LOGINS):
        _login(client, world.emails["clerk"], "falsch-123456")
    assert len(_events(settings, world, "auth.account_locked", "clerk")) == 1
    assert _login(client, world.emails["clerk"]).status_code == 423


def test_mfa_reset_four_eyes(client: TestClient, settings: Any) -> None:
    world = _world(
        settings,
        {"a1": "tenant_admin", "a2": "tenant_admin", "clerk": "standard", "reader": "read_only"},
    )
    other = _world(settings, {"x": "tenant_admin"})
    h1 = _session(client, world.emails["a1"])
    h2 = _session(client, world.emails["a2"])
    hr = _session(client, world.emails["reader"])
    hx = _session(client, other.emails["x"])
    hc = _session(client, world.emails["clerk"])
    _enable_totp(client, hc)
    members = client.get("/api/v1/tenant/members", headers=h1).json()
    target = next(m["membership_id"] for m in members if m["email"] == world.emails["clerk"])
    body = {"membership_id": target, "reason": "Smartphone verloren, Identität geprüft."}

    # Switch off (default): refused.
    assert client.get(f"{R}/settings", headers=h1).json() == {"enabled": False}
    off = client.post(f"{R}/requests", json=body, headers=h1)
    assert off.status_code == 409
    assert off.json()["code"] == "MHVP-AUTH-0016"
    # Permission and validation.
    assert client.put(f"{R}/settings", json={"enabled": True}, headers=hr).status_code == 403
    assert client.post(f"{R}/requests", json=body, headers=hr).status_code == 403
    assert client.put(f"{R}/settings", json={"enabled": True}, headers=h1).status_code == 200
    short = client.post(f"{R}/requests", json={**body, "reason": "kurz"}, headers=h1)
    assert short.status_code == 422
    # Tenant separation: the other tenant does not see the membership.
    assert client.put(f"{R}/settings", json={"enabled": True}, headers=hx).status_code == 200
    assert client.post(f"{R}/requests", json=body, headers=hx).status_code == 404

    created = client.post(f"{R}/requests", json=body, headers=h1)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    assert client.post(f"{R}/requests", json=body, headers=h2).status_code == 409
    assert client.get(f"{R}/requests", headers=hx).json() == []
    assert client.post(f"{R}/requests/{rid}/approve", json={}, headers=hx).status_code == 404
    same = client.post(f"{R}/requests/{rid}/approve", json={}, headers=h1)
    assert same.status_code == 409
    assert same.json()["code"] == "MHVP-AUTH-0017"
    # Before the approval the clerk still needs the code.
    assert _login(client, world.emails["clerk"]).json()["status"] == "mfa_required"

    ok = client.post(f"{R}/requests/{rid}/approve", json={"comment": "geprüft"}, headers=h2)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"
    assert _login(client, world.emails["clerk"]).json()["status"] == "ok"
    assert client.post(f"{R}/requests/{rid}/reject", json={}, headers=h2).status_code == 409
    assert len(_events(settings, world, "auth.mfa_reset", "clerk")) == 1
    notes = _rows(settings, world.tenant_id, Notification, user_id=world.users["clerk"])
    assert any(n.kind == "auth.mfa_reset" for n in notes)
