"""M20-03 Direktversand von Ticketantworten (Betreiberentscheidung 26.09.2026): Mitglieder mit
``communication:approve`` senden direkt, Mitglieder mit Kennzeichen (Azubi, neuer
Mitarbeiter) und alle bei aktiver Notbremse brauchen eine zweite Person. Versand läuft über
``approve_and_send`` (M20-06)."""

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.communication import gmail
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m19_ticket_reply_templates import _ok
from tests.integration.test_m20_mail_approval import FakeGmail, _eml, _upload

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"
M = "/api/v1/mail"
S = "/api/v1/tenant/settings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ds-{RUN}", name=f"Direkt {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ds2-{RUN}", name=f"Direkt2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("dsadmin", "tenant_admin", a),
            ("dsazubi", "tenant_admin", a),
            ("dsclerk", "clerk_no_delete", a),
            ("dsotherb", "tenant_admin", b),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
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


def _ticket(client: TestClient, admin: dict[str, str], tag: str) -> tuple[str, dict[str, Any]]:
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info-{tag}{RUN}@example.com", "kind": "gmail", "secret": "ds"},
            headers=admin,
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=admin))
    sender = f"kunde-{tag}{RUN}@example.com"
    raw = _eml(sender, f"Frage {tag} {RUN}", f"<{tag}-{RUN}@x>")
    eml = _upload(client, admin, f"{tag}.eml", raw)
    msg = _ok(
        client.post(
            f"{M}/ingest", json={"document_id": eml, "mailbox_id": box["id"]}, headers=admin
        ),
        201,
    )
    ticket_id = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), 201)[
        "ticket_id"
    ]
    return ticket_id, box


def _reply(client: TestClient, h: dict[str, str], ticket_id: str, body: str, **extra: Any) -> Any:
    return _ok(
        client.post(
            f"{T}/{ticket_id}/reply",
            json={"subject": "AW: Frage", "body": body, "confirm": True, **extra},
            headers=h,
        ),
        201,
    )


def _members(client: TestClient, h: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {m["display_name"]: m for m in _ok(client.get("/api/v1/tenant/members", headers=h))}


def _events(client: TestClient, h: dict[str, str], kind: str) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        _ok(client.get("/api/v1/tenant/events", params={"type": kind}, headers=h)),
    )


def test_regular_approver_sends_directly_and_flag_requires_second_person(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    admin = bearer(login(client, world, "dsadmin"))
    azubi = bearer(login(client, world, "dsazubi"))
    clerk = bearer(login(client, world, "dsclerk"))
    other = bearer(login(client, world, "dsotherb"))

    # Standard: Notbremse aus, kein Kennzeichen.
    assert _ok(client.get(S, headers=admin))["ticket_reply_approval_all"] is False
    members = _members(client, admin)
    assert members["dsazubi"]["reply_approval_required"] is False

    # Kennzeichen nur mit tenant_settings:update, Grund ist Pflicht, Änderung protokolliert.
    azubi_membership = members["dsazubi"]["membership_id"]
    flag_url = f"/api/v1/tenant/members/{azubi_membership}/reply-approval"
    assert (
        client.put(flag_url, json={"required": True, "reason": "azubi"}, headers=clerk).status_code
        == 403
    )
    assert client.put(flag_url, json={"required": True}, headers=admin).status_code == 422
    flagged = _ok(
        client.put(
            flag_url,
            json={"required": True, "reason": "azubi", "until": "2027-12-31"},
            headers=admin,
        )
    )
    assert flagged["reply_approval_required"] is True
    assert flagged["reply_approval_reason"] == "azubi"
    assert flagged["reply_approval_until"] == "2027-12-31"
    changed = _events(client, admin, "membership.reply_approval_changed")
    assert any(
        e["payload"]["user_id"] == str(world.users["dsazubi"])
        and e["payload"]["after"]["reason"] == "azubi"
        for e in changed
    )
    # Mandantentrennung: fremder Mandant sieht weder Mitglied noch Einstellung.
    assert client.put(flag_url, json={"required": False}, headers=other).status_code == 404
    assert _ok(client.get(S, headers=other))["ticket_reply_approval_all"] is False

    ticket_id, box = _ticket(client, admin, "ds")
    _ok(
        client.put(
            f"{M}/mailboxes/{box['id']}/users",
            json={"user_ids": [str(world.users["dsclerk"]), str(world.users["dsazubi"])]},
            headers=admin,
        )
    )

    # Regulärer Mitarbeiter mit communication:approve: Entwurf, Selbstfreigabe, Versand.
    sent = _reply(client, admin, ticket_id, "Guten Tag, Ihr Anliegen liegt uns vor.")
    assert sent["status"] == "sent", sent
    assert sent["direct_send"] == {"attempted": True, "reason": None, "error": None}
    assert sent["approved_by"] == str(world.users["dsadmin"])
    assert sent["author_approval_required"] is False
    assert len(fake.sent) == 1
    kinds = [e["kind"] for e in _ok(client.get(f"{T}/{ticket_id}", headers=admin))["events"]]
    for kind in ("reply_drafted", "reply_submitted", "reply_approved", "reply_sent", "mail_sent"):
        assert kind in kinds, kind
    direct = _events(client, admin, "message.direct_sent")
    assert [
        e
        for e in direct
        if e["payload"]["ticket_id"] == ticket_id
        and e["payload"]["user_id"] == str(world.users["dsadmin"])
        and e["payload"]["origin"] == "ticket"
    ]

    # Azubi (Kennzeichen) trotz Recht communication:approve: bleibt pending, kann nicht
    # selbst freigeben, Freigabeberechtigte werden benachrichtigt.
    draft = _reply(client, azubi, ticket_id, "Guten Tag, wir melden uns in Kürze.")
    assert draft["status"] == "pending"
    assert draft["direct_send"] == {"attempted": False, "reason": "author_flagged", "error": None}
    assert draft["author_approval_required"] is True
    assert draft["author_approval_reason"] == "azubi"
    assert len(fake.sent) == 1
    own = client.post(f"{M}/messages/{draft['id']}/approve", headers=azubi)
    assert own.status_code == 409, own.text
    notes = _ok(client.get("/api/v1/workspace/notifications", headers=admin))
    assert any(
        n["kind"] == "mail.approval_requested" and n["entity_id"] == draft["id"] for n in notes
    ), notes
    azubi_notes = _ok(client.get("/api/v1/workspace/notifications", headers=azubi))
    assert not [n for n in azubi_notes if n["entity_id"] == draft["id"]]

    # Zweite Person gibt frei; Nachvollziehbarkeit im Mailverlauf und in den Ereignissen.
    released = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=admin))
    assert released["status"] == "sent"
    assert len(fake.sent) == 2
    thread = _ok(client.get(f"{T}/{ticket_id}/messages", headers=admin))
    row = next(m for m in thread if m["id"] == draft["id"])
    assert row["created_by_name"] == "dsazubi"
    assert row["approved_by_name"] == "dsadmin"
    assert row["author_approval_required"] is True
    events = _ok(client.get(f"{T}/{ticket_id}", headers=admin))["events"]
    approved = [
        e
        for e in events
        if e["kind"] == "reply_approved" and e["data"]["message_id"] == draft["id"]
    ]
    assert approved
    assert approved[0]["data"]["self_approved"] is False
    assert approved[0]["data"]["drafted_by"] == str(world.users["dsazubi"])
    reply_sent = [
        e for e in events if e["kind"] == "reply_sent" and e["data"]["message_id"] == draft["id"]
    ]
    assert reply_sent
    assert reply_sent[0]["data"]["author_approval_reason"] == "azubi"

    # Mitarbeiter ohne communication:approve: bleibt pending (Vier-Augen wie bisher).
    clerk_reply = _reply(client, clerk, ticket_id, "Guten Tag, wir melden uns.")
    assert clerk_reply["status"] == "pending"
    assert clerk_reply["direct_send"]["reason"] == "no_permission"
    assert len(fake.sent) == 2

    # Befristetes Kennzeichen abgelaufen: Azubi sendet direkt.
    _ok(
        client.put(
            flag_url,
            json={"required": True, "reason": "neuer_mitarbeiter", "until": "2026-01-01"},
            headers=admin,
        )
    )
    expired = _reply(client, azubi, ticket_id, "Guten Tag, die Frist ist abgelaufen.")
    assert expired["status"] == "sent"
    assert len(fake.sent) == 3

    # Notbremse an: alle Antworten mit Freigabe, auch für Administratoren.
    assert (
        client.patch(S, json={"ticket_reply_approval_all": True}, headers=clerk).status_code == 403
    )
    assert _ok(client.patch(S, json={"ticket_reply_approval_all": True}, headers=admin))[
        "ticket_reply_approval_all"
    ]
    assert any(
        "ticket_reply_approval_all" in e["payload"]["fields"]
        for e in _events(client, admin, "tenant_settings.updated")
    )
    braked = _reply(client, admin, ticket_id, "Guten Tag, Notbremse.")
    assert braked["status"] == "pending"
    assert braked["direct_send"]["reason"] == "tenant_all"
    assert client.post(f"{M}/messages/{braked['id']}/approve", headers=admin).status_code == 409
    assert len(fake.sent) == 3
    _ok(client.patch(S, json={"ticket_reply_approval_all": False}, headers=admin))


def test_mailbox_message_without_ticket_keeps_four_eyes(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    """Freie Mailentwürfe aus dem Postfach (kein Ticket) bleiben beim Vier-Augen-Prinzip,
    auch für Mitglieder mit communication:approve."""
    admin = bearer(login(client, world, "dsadmin"))
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info-free{RUN}@example.com", "kind": "gmail", "secret": "ds"},
            headers=admin,
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=admin))
    raw = _eml(f"frei-{RUN}@example.com", f"Frei {RUN}", f"<free-{RUN}@x>")
    eml = _upload(client, admin, "free.eml", raw)
    msg = _ok(
        client.post(
            f"{M}/ingest", json={"document_id": eml, "mailbox_id": box["id"]}, headers=admin
        ),
        201,
    )
    assert msg["ticket_id"] is None
    draft = _ok(
        client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin),
        201,
    )
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
    assert client.post(f"{M}/messages/{draft['id']}/approve", headers=admin).status_code == 409
    assert len(fake.sent) == 0
