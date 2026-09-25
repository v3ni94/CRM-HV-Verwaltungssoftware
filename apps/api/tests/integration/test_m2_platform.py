"""M2 acceptance: tenants from seeds, auth, tenant switch, permissions, gates, webhooks."""

import asyncio
import base64
import http.server
import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

import jwt
import pyotp
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from mhvp.core import crypto
from mhvp.core.auth import tokens
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.webhook_tasks import dispatch_once
from mhvp.core.webhooks import verify
from mhvp.main import create_app
from mhvp.platform import services
from tests.conftest import make_settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration
PASSWORD = "correct horse battery staple"
RUN = uuid.uuid4().hex[:8]


def _settings(database: Database, redis_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": SecretStr(database.app_url),
        "redis_url": SecretStr(redis_url),
        "master_key": SecretStr(base64.b64encode(b"k" * 32).decode()),
        "jwt_private_key": SecretStr(_PEM),
        "jwt_issuer": "http://testserver",
        "webhook_allow_private_targets": True,
    }
    values.update(overrides)
    return make_settings(**values)


_PEM = tokens.generate_private_key_pem()


@dataclass
class World:
    tenant_a: uuid.UUID
    tenant_b: uuid.UUID
    app_url: str = ""
    users: dict[str, uuid.UUID] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)

    def allow_code_reuse(self, name: str) -> None:
        """Test helper: forget the last TOTP step so repeated test logins can reuse a code."""
        from sqlalchemy import create_engine

        engine = create_engine(self.app_url)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE app_user SET totp_last_step = NULL WHERE id = :id"),
                {"id": self.users[name]},
            )
        engine.dispose()

    def email(self, name: str) -> str:
        return f"{name}-{RUN}@example.org"


async def _build_world(settings: Settings) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"a-{RUN}", name=f"Mandant A {RUN}")
        b, _ = await services.provision_tenant(
            factory, slug=f"b-{RUN}", name=f"Mandant B {RUN}", domains=[f"portal-b-{RUN}.test"]
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "admin": (False, [(a, "tenant_admin")]),
            "reader": (False, [(a, "read_only")]),
            "both": (False, [(a, "tenant_admin"), (b, "standard")]),
            "padmin": (True, []),
            "padmin2": (True, [(a, "tenant_admin")]),
            "locked": (False, [(a, "read_only")]),
        }
        for name, (is_admin, memberships) in specs.items():
            user_id = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = user_id
            for tenant_id, role in memberships:
                await services.add_member(
                    factory,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role_codes=[role],
                    actor_user_id=None,
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_build_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _code(secret: str, offset: int = 0) -> str:
    totp = pyotp.TOTP(secret)
    return totp.generate_otp(int(time.time() // totp.interval) + offset)


def login(
    client: TestClient,
    world: World,
    name: str,
    tenant_id: uuid.UUID | None = None,
    offset: int = 0,
    reuse: bool = True,
) -> dict[str, Any]:
    if reuse and name in world.secrets:
        world.allow_code_reuse(name)
    step = client.post(
        "/api/v1/auth/login", json={"email": world.email(name), "password": PASSWORD}
    )
    assert step.status_code == 200, step.text
    step_body = step.json()
    if step_body["status"] == "ok":
        # 2FA-Pflicht gilt nur für Administratoren; alle anderen sind direkt angemeldet.
        issued: dict[str, Any] = dict(step_body["tokens"])
        if tenant_id and str(issued.get("tenant_id")) != str(tenant_id):
            switched = client.post(
                "/api/v1/auth/switch-tenant",
                json={"tenant_id": str(tenant_id)},
                headers={"Authorization": f"Bearer {issued['access_token']}"},
            )
            assert switched.status_code == 200, switched.text
            return dict(switched.json())
        return issued
    mfa = step_body["mfa_token"]
    if step_body["status"] == "mfa_setup_required":
        setup = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": mfa})
        assert setup.status_code == 200, setup.text
        world.secrets[name] = setup.json()["secret"]
    body: dict[str, Any] = {"mfa_token": mfa, "code": _code(world.secrets[name], offset)}
    if tenant_id:
        body["tenant_id"] = str(tenant_id)
    verified = client.post("/api/v1/auth/mfa/verify", json=body)
    assert verified.status_code == 200, verified.text
    return dict(verified.json())


def bearer(tokens_: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens_['access_token']}"}


# Seeds -----------------------------------------------------------------------------------


def test_seeds_create_both_tenants_with_ci_values(database: Database, redis_url: str) -> None:
    async def run() -> dict[str, uuid.UUID]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            first = await services.seed_tenants(factory)
            second = await services.seed_tenants(factory)
            assert first == second  # idempotent
            return first
        finally:
            await engine.dispose()

    tenants = asyncio.run(run())
    assert set(tenants) == {"hausverwaltung-mueller", "timo-mueller"}
    hvm = services.load_seed("hausverwaltung-mueller.json")
    assert hvm["company"]["register_number"] == "HRB 104762"
    assert hvm["company"]["register_court"] == "Amtsgericht Düsseldorf"
    assert hvm["branding"]["accent_color"] == "#E6A83C"
    assert hvm["company"]["vat_id"] is None  # not in the CI source, never invented
    tm = services.load_seed("timo-mueller.json")
    assert tm["company"]["register_number"] is None


def test_branding_is_public_by_portal_host(client: TestClient, world: World) -> None:
    response = client.get("/api/v1/tenant/branding", headers={"Host": f"portal-b-{RUN}.test"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(world.tenant_b)
    assert client.get("/api/v1/tenant/branding").status_code == 404


# Login, MFA, sessions --------------------------------------------------------------------


def test_login_with_totp_setup_selects_single_tenant(client: TestClient, world: World) -> None:
    issued = login(client, world, "admin")
    assert issued["tenant_id"] == str(world.tenant_a)
    me = client.get("/api/v1/auth/me", headers=bearer(issued)).json()
    assert "tenant_settings:update" in me["permissions"]
    assert me["roles"] == ["tenant_admin"]


def test_totp_code_cannot_be_replayed(client: TestClient, world: World) -> None:
    # Only administrators are forced into TOTP (admin-only 2FA policy), so the replay
    # protection is exercised with a fresh tenant admin whose steps no other test consumes.
    admin = bearer(login(client, world, "admin"))
    email = f"replay-{RUN}@example.org"
    created = client.post(
        "/api/v1/tenant/members",
        json={
            "email": email,
            "display_name": "Replay Admin",
            "role_codes": ["tenant_admin"],
            "password": PASSWORD,
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()
    assert step["status"] == "mfa_setup_required", step
    secret = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": step["mfa_token"]}).json()[
        "secret"
    ]
    first = client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": step["mfa_token"], "code": _code(secret)}
    )
    assert first.status_code == 200, first.text
    mfa = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "mfa_token"
    ]
    # The code of the current step was used by the first login.
    replay = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": mfa, "code": _code(secret)})
    assert replay.status_code == 401
    fresh = client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": mfa, "code": _code(secret, 1)}
    )
    assert fresh.status_code == 200


def test_lockout_after_repeated_failures(client: TestClient, world: World) -> None:
    for _ in range(10):
        wrong = client.post(
            "/api/v1/auth/login",
            json={"email": world.email("locked"), "password": "wrong password!!"},
        )
        assert wrong.status_code == 401
    right = client.post(
        "/api/v1/auth/login", json={"email": world.email("locked"), "password": PASSWORD}
    )
    assert right.status_code == 423
    assert right.json()["code"] == "MHVP-AUTH-0004"


def test_unknown_user_and_wrong_password_look_the_same(client: TestClient, world: World) -> None:
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.org", "password": PASSWORD}
    )
    wrong = client.post(
        "/api/v1/auth/login", json={"email": world.email("admin"), "password": "not the password"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["code"] == wrong.json()["code"]


def test_refresh_rotation_and_reuse_detection(client: TestClient, world: World) -> None:
    issued = login(client, world, "admin", offset=1)
    first = issued["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first
    # Reusing the rotated token ends the whole session family.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_sessions_list_and_logout(client: TestClient, world: World) -> None:
    issued = login(client, world, "padmin2")
    listed = client.get("/api/v1/auth/sessions", headers=bearer(issued)).json()
    assert listed
    assert (
        client.post(
            "/api/v1/auth/logout", json={"refresh_token": issued["refresh_token"]}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]}
        ).status_code
        == 401
    )


# Tenant switch (acceptance) --------------------------------------------------------------


def test_user_switches_between_tenants(client: TestClient, world: World) -> None:
    issued = login(client, world, "both")
    assert issued["tenant_id"] is None
    assert {t["id"] for t in issued["tenants"]} == {str(world.tenant_a), str(world.tenant_b)}
    in_a = client.post(
        "/api/v1/auth/switch-tenant",
        json={"tenant_id": str(world.tenant_a)},
        headers=bearer(issued),
    )
    assert in_a.status_code == 200
    settings_a = client.get("/api/v1/tenant/settings", headers=bearer(in_a.json())).json()
    assert settings_a["tenant_id"] == str(world.tenant_a)
    in_b = client.post(
        "/api/v1/auth/switch-tenant",
        json={"tenant_id": str(world.tenant_b)},
        headers=bearer(in_a.json()),
    )
    settings_b = client.get("/api/v1/tenant/settings", headers=bearer(in_b.json())).json()
    assert settings_b["tenant_id"] == str(world.tenant_b)
    # standard role in B has no update right
    patch = client.patch(
        "/api/v1/tenant/settings", json={"company": {"name": "X"}}, headers=bearer(in_b.json())
    )
    assert patch.status_code == 403


def test_non_member_cannot_switch(client: TestClient, world: World) -> None:
    issued = login(client, world, "admin")
    denied = client.post(
        "/api/v1/auth/switch-tenant",
        json={"tenant_id": str(world.tenant_b)},
        headers=bearer(issued),
    )
    assert denied.status_code == 403


def test_platform_switch_requires_reason_and_is_recorded(client: TestClient, world: World) -> None:
    issued = login(client, world, "padmin")
    assert issued["tenant_id"] is None
    no_reason = client.post(
        "/api/v1/auth/switch-tenant",
        json={"tenant_id": str(world.tenant_a)},
        headers=bearer(issued),
    )
    assert no_reason.status_code == 422
    switched = client.post(
        "/api/v1/auth/switch-tenant",
        json={"tenant_id": str(world.tenant_a), "reason": "Support Ticket 4711 Einstellungen"},
        headers=bearer(issued),
    )
    assert switched.status_code == 200
    assert switched.json()["refresh_token"] is None
    events = client.get(
        "/api/v1/tenant/events?type=platform.tenant_switched", headers=bearer(switched.json())
    ).json()
    assert any(e["payload"]["reason"] == "Support Ticket 4711 Einstellungen" for e in events)


def test_host_and_token_tenant_must_match(client: TestClient, world: World) -> None:
    issued = login(client, world, "admin")
    response = client.get(
        "/api/v1/tenant/settings", headers=bearer(issued) | {"Host": f"portal-b-{RUN}.test"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "MHVP-AUTH-0005"


# Permissions, settings, audit ------------------------------------------------------------


def test_read_only_user_cannot_change_anything(client: TestClient, world: World) -> None:
    issued = login(client, world, "reader", offset=-1)
    headers = bearer(issued)
    assert client.get("/api/v1/tenant/settings", headers=headers).status_code == 200
    for method, url, body in [
        ("PATCH", "/api/v1/tenant/settings", {"company": {"name": "X"}}),
        ("POST", "/api/v1/tenant/api-keys", {"name": "x", "scopes": ["tenant_settings:read"]}),
        ("POST", "/api/v1/tenant/webhooks", {"url": "http://127.0.0.1:9/x", "event_types": ["*"]}),
        ("POST", "/api/v1/tenant/roles", {"code": "sneaky", "name": "Sneaky"}),
        (
            "POST",
            "/api/v1/tenant/release-gates/requests",
            {"gate": "G1", "scope": "Alles für alle Objekte", "evidence": "keine"},
        ),
    ]:
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code == 403, (url, response.text)


def test_settings_update_is_versioned_and_audited(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "admin"))
    current = client.get("/api/v1/tenant/settings", headers=headers)
    etag = current.headers["etag"]
    stale = client.patch(
        "/api/v1/tenant/settings",
        json={"company": {"name": "Neu"}},
        headers=headers | {"If-Match": '"999"'},
    )
    assert stale.status_code == 412
    updated = client.patch(
        "/api/v1/tenant/settings",
        json={"company": {"name": f"Mandant A {RUN} neu", "city": "Monheim am Rhein"}},
        headers=headers | {"If-Match": etag},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == current.json()["version"] + 1
    audit = client.get("/api/v1/tenant/audit-log", headers=headers).json()
    assert audit[0]["changes"]["company"]["new"]["city"] == "Monheim am Rhein"
    bad_colour = client.patch(
        "/api/v1/tenant/settings", json={"branding": {"accent_color": "orange"}}, headers=headers
    )
    assert bad_colour.status_code == 422


def test_api_key_scopes_and_revocation(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "admin"))
    created = client.post(
        "/api/v1/tenant/api-keys",
        json={"name": "Objektakte", "scopes": ["tenant_settings:read"]},
        headers=headers,
    )
    assert created.status_code == 201
    key = created.json()["key"]
    assert client.get("/api/v1/tenant/settings", headers={"X-API-Key": key}).status_code == 200
    assert (
        client.patch("/api/v1/tenant/settings", json={}, headers={"X-API-Key": key}).status_code
        == 403
    )
    assert (
        client.get("/api/v1/tenant/settings", headers={"X-API-Key": key[:-2] + "xx"}).status_code
        == 401
    )
    assert (
        client.delete(
            f"/api/v1/tenant/api-keys/{created.json()['id']}", headers=headers
        ).status_code
        == 204
    )
    assert client.get("/api/v1/tenant/settings", headers={"X-API-Key": key}).status_code == 401


def test_custom_role_with_inheritance(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "admin"))
    parent = client.post(
        "/api/v1/tenant/roles",
        json={"code": f"base_{RUN}", "name": "Basis", "permissions": ["audit:read"]},
        headers=headers,
    )
    child = client.post(
        "/api/v1/tenant/roles",
        json={
            "code": f"child_{RUN}",
            "name": "Kind",
            "parent_role_id": parent.json()["id"],
            "permissions": ["tenant_settings:read"],
        },
        headers=headers,
    )
    assert child.status_code == 201
    bad = client.post(
        "/api/v1/tenant/roles",
        json={"code": f"bad_{RUN}", "name": "Bad", "permissions": ["money:print"]},
        headers=headers,
    )
    assert bad.status_code == 422
    members = client.get("/api/v1/tenant/members", headers=headers).json()
    reader = next(m for m in members if m["user_id"] == str(world.users["locked"]))
    assert (
        client.put(
            f"/api/v1/tenant/members/{reader['membership_id']}/roles",
            json={"role_codes": [f"child_{RUN}"]},
            headers=headers,
        ).status_code
        == 204
    )


# Release gates ---------------------------------------------------------------------------


def test_release_gate_needs_second_person(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "padmin2"))
    state = client.get("/api/v1/tenant/release-gates", headers=admin).json()
    assert all(not g["open"] for g in state)
    requested = client.post(
        "/api/v1/tenant/release-gates/requests",
        json={
            "gate": "G1",
            "scope": "Testumfang Objektgruppe Pilot",
            "evidence": "Prüfbericht Testfall",
        },
        headers=admin,
    )
    assert requested.status_code == 201
    request_id = requested.json()["id"]
    url = f"/api/v1/platform/tenants/{world.tenant_a}/release-gates/requests/{request_id}/approve"
    # padmin2 is platform admin and requester: the same person cannot approve.
    same = client.post(url, json={}, headers=admin)
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    tenant_admin_only = bearer(login(client, world, "admin"))
    assert client.post(url, json={}, headers=tenant_admin_only).status_code == 403
    other = login(client, world, "padmin")
    approved = client.post(url, json={"comment": "geprüft"}, headers=bearer(other))
    assert approved.status_code == 200
    opened = client.get("/api/v1/tenant/release-gates", headers=admin).json()
    assert next(g for g in opened if g["gate"] == "G1")["open"] is True
    revoked = client.post(
        f"/api/v1/tenant/release-gates/requests/{request_id}/revoke", json={}, headers=admin
    )
    assert revoked.status_code == 200
    closed = client.get("/api/v1/tenant/release-gates", headers=admin).json()
    assert all(not g["open"] for g in closed)


# Webhooks --------------------------------------------------------------------------------


class _Receiver(http.server.BaseHTTPRequestHandler):
    received: ClassVar[list[tuple[dict[str, str], bytes]]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Receiver.received.append((dict(self.headers), body))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return None


def test_webhook_delivery_signed_and_retried(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        headers = bearer(login(client, world, "admin"))
        url = f"http://127.0.0.1:{server.server_port}/hook"
        created = client.post(
            "/api/v1/tenant/webhooks",
            json={"url": url, "event_types": ["tenant_settings.updated"]},
            headers=headers,
        )
        assert created.status_code == 201
        secret = created.json()["secret"]
        dead = client.post(
            "/api/v1/tenant/webhooks",
            json={"url": "http://127.0.0.1:9/dead", "event_types": ["*"]},
            headers=headers,
        )
        client.patch(
            "/api/v1/tenant/settings", json={"company": {"name": f"Webhook {RUN}"}}, headers=headers
        )
        asyncio.run(dispatch_once(_settings(database, redis_url)))
        received = [
            r for r in _Receiver.received if json.loads(r[1])["type"] == "tenant_settings.updated"
        ]
        assert received
        headers_in, body = received[-1]
        assert verify(secret, body, headers_in["X-MHVP-Signature"], now=int(time.time()))
        assert not verify("wrong", body, headers_in["X-MHVP-Signature"], now=int(time.time()))
        ok = client.get(
            f"/api/v1/tenant/webhooks/{created.json()['id']}/deliveries", headers=headers
        ).json()
        assert ok[0]["status"] == "succeeded"
        failed = client.get(
            f"/api/v1/tenant/webhooks/{dead.json()['id']}/deliveries", headers=headers
        ).json()
        assert failed
        assert all(d["status"] == "pending" and d["attempts"] == 1 for d in failed)
        # Second dispatch does not duplicate deliveries (idempotent enqueue).
        count = len(_Receiver.received)
        asyncio.run(dispatch_once(_settings(database, redis_url)))
        assert len(_Receiver.received) == count
    finally:
        server.shutdown()


def test_webhook_private_target_refused_outside_dev(
    database: Database, redis_url: str, world: World
) -> None:
    settings = _settings(database, redis_url, webhook_allow_private_targets=False)
    with TestClient(create_app(settings)) as strict:
        headers = bearer(login(strict, world, "admin"))
        for url in (
            "http://127.0.0.1:8080/x",
            "https://10.0.0.1/x",
            "https://user:pw@example.org/x",
            "ftp://example.org",
        ):
            response = strict.post(
                "/api/v1/tenant/webhooks", json={"url": url, "event_types": ["*"]}, headers=headers
            )
            assert response.status_code == 422, url


# Storage level guarantees ----------------------------------------------------------------


def test_totp_secret_is_encrypted_at_rest(
    world: World, migrator_engine: Engine, client: TestClient
) -> None:
    login(client, world, "padmin")
    with migrator_engine.connect() as conn:
        raw = conn.execute(
            text("SELECT totp_secret FROM app_user WHERE id = :id"), {"id": world.users["padmin"]}
        ).scalar_one()
    assert raw is not None
    assert world.secrets["padmin"].encode() not in bytes(raw)
    assert bytes(raw)[:2] == b"v1"


def test_events_are_append_only(migrator_engine: Engine, world: World) -> None:
    with migrator_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("UPDATE domain_event SET type = 'forged'"))
    with migrator_engine.begin() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM audit_log"))


def test_tenant_data_isolated_between_tenants(app_engine: Engine, world: World) -> None:
    with app_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        tenants = set(conn.execute(text("SELECT DISTINCT tenant_id FROM role")).scalars())
    assert tenants == {world.tenant_a}


# OIDC ------------------------------------------------------------------------------------


def test_oidc_authorization_code_with_pkce(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    client_id = f"objektakte-{RUN}"
    with migrator_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO oidc_client (id, client_id, name, redirect_uris, active, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :c, 'Objektakte', ARRAY['https://objektakte.test/cb'], true, now(), now())"
            ),
            {"c": client_id},
        )
    discovery = client.get("/.well-known/openid-configuration").json()
    assert discovery["code_challenge_methods_supported"] == ["S256"]
    headers = bearer(login(client, world, "admin"))
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": "https://objektakte.test/cb",
        "scope": "openid email",
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "state": "xyz",
        "nonce": "n-1",
    }
    redirect = client.get(
        "/api/v1/oidc/authorize", params=params, headers=headers, follow_redirects=False
    )
    assert redirect.status_code == 302
    code = redirect.headers["location"].split("code=")[1].split("&")[0]
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://objektakte.test/cb",
        "client_id": client_id,
        "code_verifier": "wrong" * 10,
    }
    assert client.post("/api/v1/oidc/token", data=form).status_code == 400
    form["code_verifier"] = verifier
    issued = client.post("/api/v1/oidc/token", data=form)
    assert issued.status_code == 200, issued.text
    jwk = client.get("/api/v1/oidc/jwks").json()["keys"][0]
    key = jwt.PyJWK(jwk).key
    claims = jwt.decode(issued.json()["id_token"], key, algorithms=["ES256"], audience=client_id)
    assert claims["email"] == world.email("admin")
    assert claims["nonce"] == "n-1"
    assert client.post("/api/v1/oidc/token", data=form).status_code == 400  # code used once
    params["redirect_uri"] = "https://evil.test/cb"
    assert (
        client.get(
            "/api/v1/oidc/authorize", params=params, headers=headers, follow_redirects=False
        ).status_code
        == 400
    )


def _challenge(verifier: str) -> str:
    import hashlib

    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def test_tenant_admin_manages_members_and_users_change_password(
    client: TestClient, world: World
) -> None:
    """Expected by hand (operator 25.09.2026): a tenant admin adds a user with start password
    and roles, a contact is created alongside; the new user logs in and changes the password
    (wrong current password refused); the admin resets the password, disables the membership
    (login to the tenant refused) and cannot disable their own membership; a standard user
    cannot manage members."""
    admin = bearer(login(client, world, "admin"))
    email = f"neu-{RUN}@example.org"
    created = client.post(
        "/api/v1/tenant/members",
        json={
            "email": email,
            "display_name": f"Neue Person {RUN}",
            "password": PASSWORD,
            "role_codes": ["standard"],
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    member = created.json()
    assert member["roles"] == ["standard"]
    assert member["contact_id"] is not None
    contact = client.get(f"/api/v1/contacts/{member['contact_id']}", headers=admin)
    assert contact.status_code == 200, contact.text
    assert contact.json()["emails"][0]["email"] == email
    # Without a start password a new account cannot be created; an existing one just joins.
    missing = client.post(
        "/api/v1/tenant/members",
        json={
            "email": f"x-{RUN}@example.org",
            "display_name": "Ohne Passwort",
            "role_codes": ["standard"],
        },
        headers=admin,
    )
    assert missing.status_code == 422, missing.text

    def login_new(password: str) -> Any:
        return client.post("/api/v1/auth/login", json={"email": email, "password": password})

    # Standard role: no forced 2FA (the policy binds administrators only), direct session.
    first = login_new(PASSWORD).json()
    assert first["status"] == "ok", first
    user = bearer(first["tokens"])
    wrong = client.post(
        "/api/v1/auth/password",
        json={"current_password": "falsch", "new_password": "ein neues langes Passwort"},
        headers=user,
    )
    assert wrong.status_code == 401, wrong.text
    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "ein neues langes Passwort"},
        headers=user,
    )
    assert changed.status_code == 204, changed.text
    assert login_new(PASSWORD).status_code == 401
    assert login_new("ein neues langes Passwort").status_code == 200
    # A standard user may not manage members.
    assert client.get("/api/v1/tenant/members", headers=user).status_code == 403
    # Admin resets the password and disables the membership.
    reset = client.post(
        f"/api/v1/tenant/members/{member['membership_id']}/reset-password",
        json={"password": "Startpasswort 2026"},
        headers=admin,
    )
    assert reset.status_code == 204, reset.text
    assert login_new("Startpasswort 2026").status_code == 200
    disabled = client.patch(
        f"/api/v1/tenant/members/{member['membership_id']}",
        json={"status": "disabled"},
        headers=admin,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"
    # Membership disabled: the password still works, but no tenant session exists any more.
    step = login_new("Startpasswort 2026").json()
    assert step["status"] == "ok", step
    assert step["tokens"]["tenant_id"] is None
    assert step["tokens"]["tenants"] == []
    blocked = client.get("/api/v1/tenant/members", headers=bearer(step["tokens"]))
    assert blocked.status_code == 403, blocked.text
    me = next(
        m
        for m in client.get("/api/v1/tenant/members", headers=admin).json()
        if m["email"] == world.email("admin")
    )
    own = client.patch(
        f"/api/v1/tenant/members/{me['membership_id']}", json={"status": "disabled"}, headers=admin
    )
    assert own.status_code == 422, own.text


def test_mfa_policy_admins_only_and_trusted_device(client: TestClient, world: World) -> None:
    """2FA-Pflicht nur für Administratoren; „Gerät merken" (180 Tage) überspringt nach
    korrektem Passwort nur den TOTP-Schritt und erlischt beim TOTP-Reset."""
    admin = bearer(login(client, world, "admin"))
    email = f"device-{RUN}@example.org"
    created = client.post(
        "/api/v1/tenant/members",
        json={
            "email": email,
            "display_name": "Device Admin",
            "role_codes": ["tenant_admin"],
            "password": PASSWORD,
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text

    # Administrator: Einrichtung erzwungen; Verify mit remember_device liefert ein Gerätetoken.
    step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()
    assert step["status"] == "mfa_setup_required", step
    secret = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": step["mfa_token"]}).json()[
        "secret"
    ]
    verified = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": step["mfa_token"], "code": _code(secret), "remember_device": True},
    )
    assert verified.status_code == 200, verified.text
    device_token = verified.json()["device_token"]
    assert device_token

    # Vertrautes Gerät: Passwort + Gerätetoken genügen, kein TOTP-Schritt.
    trusted = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD, "device_token": device_token},
    ).json()
    assert trusted["status"] == "ok", trusted
    assert trusted["tokens"]["access_token"]

    # Falsches Passwort bleibt falsch, auch mit Gerätetoken.
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "falsches Passwort", "device_token": device_token},
    )
    assert bad.status_code == 401, bad.text

    # Fremdes Gerätetoken (anderer Nutzer) zählt nicht: TOTP bleibt Pflicht.
    other = client.post(
        "/api/v1/auth/login",
        json={
            "email": world.email("admin"),
            "password": PASSWORD,
            "device_token": device_token,
        },
    ).json()
    assert other["status"] == "mfa_required", other

    # Manipuliertes Token fällt auf den TOTP-Schritt zurück statt zu scheitern.
    tampered = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD, "device_token": device_token[:-2] + "xx"},
    ).json()
    assert tampered["status"] == "mfa_required", tampered
