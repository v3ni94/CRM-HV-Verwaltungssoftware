"""M20-04 Vier-Augen-Prinzip beim Mailversand: Re-Authentifizierung (Passwort/TOTP, 5 Minuten),
Mandantenkonfiguration (all/external_only/off), Vertretungsregel (Stellvertreter bei
Abwesenheit) und Superadmin-Bypass nur mit Plattform-Flag (ADR 0011)."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.communication import gmail
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail_approval import FakeGmail, _eml, _ok, _reauth

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
SETTINGS = "/api/v1/tenant/settings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"mr-{RUN}", name=f"MailReauth {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role, is_platform_admin in [
            ("mrauthor", "tenant_admin", False),
            ("mrfreigeber", "tenant_admin", False),
            ("mrsuper", "tenant_admin", True),  # ADR 0011 superadmin candidate
            ("mrabsent", "tenant_admin", False),
            # Eigene, nicht-administrative Freigaberolle (nur communication:approve, kein
            # tenant_settings:update), damit die Postfachbeschränkung wirklich greift.
            ("mrdeputy", "standard", False),
            ("mrlockout", "tenant_admin", False),  # only used by the lockout test
        ]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_platform_admin,
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def fake() -> FakeGmail:
    return FakeGmail()


@pytest.fixture
def client(
    database: Database, redis_url: str, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from pydantic import SecretStr

    settings = _settings(database, redis_url).model_copy(
        update={"google_client_id": "cid", "google_client_secret": SecretStr("csecret")}
    )
    original = gmail.GmailClient

    def patched(client_id: str, client_secret: str, refresh_token: str, **_: Any) -> Any:
        return original(
            client_id, client_secret, refresh_token, transport=httpx.MockTransport(fake.handler)
        )

    monkeypatch.setattr(gmail, "GmailClient", patched)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _gmail_box(client: TestClient, h: dict[str, str], address: str) -> dict[str, Any]:
    box = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": address, "kind": "gmail", "secret": "rt"}, headers=h
        ),
        201,
    )
    return dict(_ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h)))


def _pending_draft(client: TestClient, h: dict[str, str], box_id: str, tag: str) -> dict[str, Any]:
    raw = _eml(f"m-{tag}@example.com", f"Frage {tag}", f"<{tag}@x>")
    doc = _ok(
        client.post(
            "/api/v1/documents", files={"file": (f"{tag}.eml", raw, "message/rfc822")}, headers=h
        ),
        201,
    )["id"]
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box_id}, headers=h), 201
    )
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))
    return dict(draft)


def _set_mode(client: TestClient, h: dict[str, str], mode: str) -> None:
    current = _ok(client.get(SETTINGS, headers=h))
    patched = client.patch(
        SETTINGS,
        json={"mail_approval_mode": mode},
        headers={**h, "If-Match": f'"{current["version"]}"'},
    )
    assert patched.status_code == 200, patched.text


def test_approve_requires_recent_reauth(client: TestClient, world: World, fake: FakeGmail) -> None:
    h = bearer(login(client, world, "mrauthor"))
    freigeber = bearer(login(client, world, "mrfreigeber"))
    _set_mode(client, h, "all")
    box = _gmail_box(client, h, f"mr1-{RUN}@example.com")
    draft = _pending_draft(client, h, box["id"], f"mr1-{RUN}")

    # Ohne Re-Auth-Nachweis wird die Freigabe abgelehnt (MHVP-COMM-0002).
    blocked = client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber)
    assert blocked.status_code == 401, blocked.text
    assert blocked.json()["code"] == "MHVP-COMM-0002"

    # Falsches Passwort bleibt ein Anmeldefehler, kein Freigabefortschritt.
    wrong = client.post(f"{M}/mail-approval/reauth", json={"password": "falsch"}, headers=freigeber)
    assert wrong.status_code == 401
    assert client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber).status_code == 401

    _reauth(client, freigeber)
    sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber))
    assert sent["status"] == "sent"


def test_approve_reauth_expires_after_five_minutes(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    h = bearer(login(client, world, "mrauthor"))
    freigeber = bearer(login(client, world, "mrfreigeber"))
    _set_mode(client, h, "all")
    box = _gmail_box(client, h, f"mr2-{RUN}@example.com")
    draft = _pending_draft(client, h, box["id"], f"mr2-{RUN}")
    _reauth(client, freigeber)

    # Nachweis künstlich auf vor sechs Minuten zurückdatieren (Zeitfenster ist 5 Minuten).
    engine = create_engine(world.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        conn.execute(
            text(
                "UPDATE mail_approval_reauth SET verified_at = :ts "
                "WHERE user_id = :uid AND tenant_id = :tid"
            ),
            {
                "ts": datetime.now(UTC) - timedelta(minutes=6),
                "uid": world.users["mrfreigeber"],
                "tid": world.tenant_a,
            },
        )
    engine.dispose()

    expired = client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber)
    assert expired.status_code == 401
    assert expired.json()["code"] == "MHVP-COMM-0002"

    _reauth(client, freigeber)
    sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber))
    assert sent["status"] == "sent"


def test_mail_approval_mode_off_allows_self_send(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    """Modus ``off``: der Verfasser darf den eigenen Entwurf selbst versenden, auch ohne die
    Ticketantwort-Ausnahme aus M20-03 (kein Ticket verknüpft)."""
    h = bearer(login(client, world, "mrauthor"))
    _set_mode(client, h, "off")
    box = _gmail_box(client, h, f"mr3-{RUN}@example.com")
    # Kein Ticket verknüpft: unter ``external_only``/``all`` wäre die Selbstfreigabe ohne
    # Ticketbezug nie erlaubt (M20-03 ``_self_approval_allowed``); im Modus ``off`` entfällt
    # die Identitätsprüfung insgesamt.
    draft = _pending_draft(client, h, box["id"], f"mr3-{RUN}")
    sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=h))
    assert sent["status"] == "sent"


def test_mail_approval_deputy_gains_mailbox_access(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    h = bearer(login(client, world, "mrauthor"))
    _set_mode(client, h, "external_only")
    box = _gmail_box(client, h, f"mr4-{RUN}@example.com")
    # Postfach nur für mrabsent freigegeben; mrdeputy hat noch keinen Zugriff.
    _ok(
        client.put(
            f"{M}/mailboxes/{box['id']}/users",
            json={"user_ids": [str(world.users["mrabsent"])]},
            headers=h,
        )
    )
    # mrdeputy braucht ``communication:approve`` ohne ``tenant_settings:update``, damit die
    # Postfachbeschränkung tatsächlich greift (die Standardrolle hat keine Freigabe).
    role = _ok(
        client.post(
            "/api/v1/tenant/roles",
            json={
                "code": f"mrdeputyrole_{RUN}",
                "name": "Mail-Stellvertretung",
                "permissions": [
                    "communication:read",
                    "communication:update",
                    "communication:approve",
                ],
            },
            headers=h,
        ),
        201,
    )
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    membership = next(m for m in members if m["user_id"] == str(world.users["mrdeputy"]))
    assert (
        client.put(
            f"/api/v1/tenant/members/{membership['membership_id']}/roles",
            json={"role_codes": [role["code"]]},
            headers=h,
        ).status_code
        == 204
    )
    draft = _pending_draft(client, h, box["id"], f"mr4-{RUN}")
    deputy = bearer(login(client, world, "mrdeputy"))
    _reauth(client, deputy)
    without_deputy = client.post(f"{M}/messages/{draft['id']}/approve", headers=deputy)
    assert without_deputy.status_code == 404, without_deputy.text

    # Vertretung eintragen (Annahme M20-04: eigene Tabelle, kein HR-Modul), gültig jetzt.
    engine = create_engine(world.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        conn.execute(
            text(
                "INSERT INTO mail_approval_deputy "
                "(id, tenant_id, absent_user_id, deputy_user_id, starts_at, ends_at, note) "
                "VALUES (gen_random_uuid(), :tid, :absent, :deputy, :starts, :ends, :note)"
            ),
            {
                "tid": world.tenant_a,
                "absent": world.users["mrabsent"],
                "deputy": world.users["mrdeputy"],
                "starts": datetime.now(UTC) - timedelta(hours=1),
                "ends": datetime.now(UTC) + timedelta(days=1),
                "note": "Urlaub",
            },
        )
    engine.dispose()

    with_deputy = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=deputy))
    assert with_deputy["status"] == "sent"
    assert with_deputy["approved_by"] == str(world.users["mrdeputy"])


def test_superadmin_bypass_only_behind_platform_flag(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    """ADR 0011: der Superadmin darf die eigene Mail nur mit dem Plattform-Flag
    ``gate_superadmin_bypass`` freigeben; ohne Flag gilt das Vier-Augen-Prinzip unverändert."""
    grant_h = bearer(login(client, world, "mrsuper"))
    # Sich selbst zum Superadmin machen (ADR 0011: einziger Superadmin, hier ohne weiteren
    # Plattformadministrator im Testaufbau).
    assert (
        client.put(
            f"/api/v1/platform/users/{world.users['mrsuper']}/superadmin", headers=grant_h
        ).status_code
        == 200
    )
    # Neu anmelden: ``principal.is_superadmin`` steht erst im Token der nächsten Anmeldung.
    super_h = bearer(login(client, world, "mrsuper", reuse=False))
    _set_mode(client, super_h, "all")
    try:
        box = _gmail_box(client, super_h, f"mr5-{RUN}@example.com")
        draft = _pending_draft(client, super_h, box["id"], f"mr5-{RUN}")
        _reauth(client, super_h)

        # Flag aus (Standard): weiterhin Vier-Augen, keine Selbstfreigabe.
        refused = client.post(f"{M}/messages/{draft['id']}/approve", headers=super_h)
        assert refused.status_code == 409
        assert refused.json()["code"] == "MHVP-COMM-0001"

        # Flag an: Bypass, aber weiterhin nur mit gültigem Re-Auth-Nachweis.
        assert (
            client.patch(
                "/api/v1/platform/settings",
                json={"gate_superadmin_bypass": True},
                headers=super_h,
            ).status_code
            == 200
        )
        sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=super_h))
        assert sent["status"] == "sent"
        assert sent["approved_by"] == str(world.users["mrsuper"])
    finally:
        client.patch(
            "/api/v1/platform/settings",
            json={"gate_superadmin_bypass": False},
            headers=super_h,
        )
        client.delete(
            f"/api/v1/platform/users/{world.users['mrsuper']}/superadmin", headers=super_h
        )


def test_reauth_failures_count_towards_the_account_lockout(
    client: TestClient, world: World
) -> None:
    """M20-04 (docs/rules/M20-04.md): a wrong password at the re-authentication counts like a
    failed login; after MAX_FAILED_LOGINS the account is locked for re-auth and login alike.
    Before the hotfix 1.35.2 the endpoint had no lockout (review 27.09.2026)."""
    from mhvp.core.auth import passwords

    h = bearer(login(client, world, "mrlockout"))
    # A success resets the counter, like a successful login.
    for _ in range(passwords.MAX_FAILED_LOGINS - 1):
        assert (
            client.post(
                f"{M}/mail-approval/reauth", json={"password": "falsch"}, headers=h
            ).status_code
            == 401
        )
    _reauth(client, h)
    for _ in range(passwords.MAX_FAILED_LOGINS - 1):
        assert (
            client.post(
                f"{M}/mail-approval/reauth", json={"password": "falsch"}, headers=h
            ).status_code
            == 401
        )
    _reauth(client, h)

    for _ in range(passwords.MAX_FAILED_LOGINS):
        client.post(f"{M}/mail-approval/reauth", json={"password": "falsch"}, headers=h)
    locked = client.post(f"{M}/mail-approval/reauth", json={"password": PASSWORD}, headers=h)
    assert locked.status_code == 423, locked.text
    assert locked.json()["code"] == "MHVP-AUTH-0004"
    relogin = client.post(
        "/api/v1/auth/login", json={"email": world.email("mrlockout"), "password": PASSWORD}
    )
    assert relogin.status_code == 423, relogin.text
