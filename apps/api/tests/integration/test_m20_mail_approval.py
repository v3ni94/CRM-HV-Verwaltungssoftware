"""M20 Vier-Augen-Freigabe für ausgehende E-Mails: Entwurf anlegen und bearbeiten, submit,
Freigabe durch denselben Nutzer scheitert, Freigabe durch einen anderen Nutzer sendet über
Gmail und legt ein Ticket-Event an, reject setzt den Entwurf mit Notiz zurück, eine 403 von
Gmail führt zu pending mit 409, Filter nach direction und Volltext, Thread-Endpunkt."""

import asyncio
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

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

pytestmark = pytest.mark.integration
M = "/api/v1/mail"


def _eml(sender: str, subject: str, msg_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Bitte um Rückmeldung wegen der Heizung.")
    return bytes(msg)


class FakeGmail:
    """Minimal Gmail API: profile, token, send."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.send_forbidden = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        assert request.headers.get("Authorization") == "Bearer t"
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "1"})
        if path.endswith("/messages/send"):
            if self.send_forbidden:
                return httpx.Response(403, json={"error": "forbidden"})
            import base64
            import json

            encoded = json.loads(request.content)["raw"]
            self.sent.append(base64.urlsafe_b64decode(encoded + "=="))
            return httpx.Response(200, json={"id": "sent1"})
        return httpx.Response(404)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ma-{RUN}", name=f"MailApp {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("maadmin", "tenant_admin"),
            ("maclerk", "standard"),
            ("mafreigeber", "tenant_admin"),
        ]:
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "message/rfc822")}, headers=h),
            201,
        )["id"]
    )


def test_approval_workflow(client: TestClient, world: World, fake: FakeGmail) -> None:
    h = bearer(login(client, world, "maadmin"))
    freigeber = bearer(login(client, world, "mafreigeber"))
    clerk = bearer(login(client, world, "maclerk"))

    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info{RUN}@example.com", "kind": "gmail", "secret": "rt"},
            headers=h,
        ),
        201,
    )
    box = _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h))
    assert box["enabled"] is True

    sender = f"mieter{RUN}@example.com"
    raw = _eml(sender, f"Heizung defekt {RUN}", f"<ma1-{RUN}@x>")
    doc = _upload(client, h, "m1.eml", raw)
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box["id"]}, headers=h),
        201,
    )
    ticket = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=h), 201)

    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    assert draft["status"] == "draft"

    edited = _ok(
        client.patch(
            f"{M}/messages/{draft['id']}/draft",
            json={"body": "Bearbeiteter Entwurfstext.", "subject": "AW: Heizung defekt"},
            headers=h,
        )
    )
    assert edited["body"] == "Bearbeiteter Entwurfstext."

    # Standard-Nutzer ohne communication:approve darf nicht freigeben.
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))
    assert client.post(f"{M}/messages/{draft['id']}/approve", headers=clerk).status_code == 403

    pending = _ok(client.get(f"{M}/messages/{draft['id']}", headers=h))
    assert pending["status"] == "pending"
    assert pending["submitted_by"] == str(world.users["maadmin"])

    # Eigener Entwurf: Vier-Augen-Prinzip greift auch für den Ersteller/Einreicher.
    own = client.post(f"{M}/messages/{draft['id']}/approve", headers=h)
    assert own.status_code == 409
    assert "Vier-Augen" in own.json()["detail"]

    # Freigabe durch einen anderen Nutzer sendet über Gmail.
    sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber))
    assert sent["status"] == "sent"
    assert sent["gmail_message_id"] == "sent1"
    assert sent["approved_by"] == str(world.users["mafreigeber"])
    assert len(fake.sent) == 1

    # Ticket-Event mail_sent liegt am verknüpften Ticket.
    events = _ok(client.get(f"/api/v1/tickets/{ticket['ticket_id']}", headers=h))
    assert any(e["kind"] == "mail_sent" for e in events.get("events", []))

    # Thread liefert Eingang und Antwort chronologisch.
    thread = _ok(client.get(f"{M}/messages/{msg['id']}/thread", headers=h))
    assert [m["id"] for m in thread] == [msg["id"], draft["id"]]

    # Filter direction und Volltext.
    out_only = _ok(client.get(f"{M}/messages", params={"direction": "out"}, headers=h))
    assert all(m["direction"] == "out" for m in out_only)
    assert draft["id"] in {m["id"] for m in out_only}
    found = _ok(client.get(f"{M}/messages", params={"q": f"Heizung defekt {RUN}"}, headers=h))
    assert msg["id"] in {m["id"] for m in found}


def test_reject_and_gmail_forbidden(client: TestClient, world: World, fake: FakeGmail) -> None:
    h = bearer(login(client, world, "maadmin"))
    freigeber = bearer(login(client, world, "mafreigeber"))

    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info2{RUN}@example.com", "kind": "gmail", "secret": "rt"},
            headers=h,
        ),
        201,
    )
    box = _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h))

    sender = f"mieter2{RUN}@example.com"
    doc = _upload(client, h, "m2.eml", _eml(sender, f"Wasserschaden {RUN}", f"<ma2-{RUN}@x>"))
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box["id"]}, headers=h),
        201,
    )
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))

    # 403 von Gmail: der Versand scheitert, Status bleibt pending.
    fake.send_forbidden = True
    forbidden = client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber)
    assert forbidden.status_code == 409
    assert "Sendeberechtigung" in forbidden.json()["detail"]
    still_pending = _ok(client.get(f"{M}/messages/{draft['id']}", headers=h))
    assert still_pending["status"] == "pending"
    fake.send_forbidden = False

    # reject setzt den Entwurf mit Notiz zurück.
    rejected = _ok(
        client.post(
            f"{M}/messages/{draft['id']}/reject",
            json={"note": "Bitte höflicher formulieren."},
            headers=freigeber,
        )
    )
    assert rejected["status"] == "draft"
    assert rejected["rejection_note"] == "Bitte höflicher formulieren."

    # Ein bereits gesendeter oder wieder als Entwurf vorliegender Vorgang lässt sich nicht
    # ein zweites Mal freigeben.
    assert client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber).status_code == 409
