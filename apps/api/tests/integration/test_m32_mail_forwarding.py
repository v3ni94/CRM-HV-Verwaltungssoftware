"""M32: company invoices (for example telecom, health insurance) are forwarded to the
invoicing mailbox and archived in Gmail; property invoices are never forwarded automatically.
The approved-senders list learns from confirmations; done mails are archived best effort."""

import asyncio
import base64
import json
from collections.abc import Iterator
from email import message_from_bytes
from email.message import EmailMessage
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.communication import gmail
from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m8_import import _settings as s3_settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
TARGET = "muellerhv@inbox.lexware.email"


def _settings(database: Database, redis_url: str) -> Settings:
    base = s3_settings(database, redis_url)
    return base.model_copy(
        update={
            "google_client_id": "test-google-client",
            "google_client_secret": SecretStr("test-google-secret"),
        }
    )


class FakeGmail:
    """OAuth token endpoint plus the Gmail calls used by forwarding and archiving."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.archived: list[str] = []
        self.by_rfc822: dict[str, str] = {}
        self.calls: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(f"{request.method} {request.url.path}")
        if "oauth2.googleapis.com" in url or "accounts.google.com" in url:
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path.endswith("/messages/send"):
            raw = json.loads(request.content)["raw"]
            self.sent.append(base64.urlsafe_b64decode(raw + "=="))
            return httpx.Response(200, json={"id": f"sent-{len(self.sent)}"})
        if request.url.path.endswith("/modify"):
            self.archived.append(request.url.path.rsplit("/", 2)[-2])
            return httpx.Response(200, json={})
        if request.url.path.endswith("/messages"):
            q = request.url.params.get("q", "")
            msgid = q.removeprefix("rfc822msgid:")
            found = self.by_rfc822.get(msgid)
            return httpx.Response(200, json={"messages": [{"id": found}] if found else []})
        return httpx.Response(404, json={})


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"fw-{RUN}", name=f"Fwd {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m32admin"), display_name="m32admin", password=PASSWORD
        )
        world.users["m32admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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
    def patched(client_id: str, client_secret: str, mailbox: Any) -> gmail.GmailClient:
        return gmail.GmailClient(
            client_id, client_secret, mailbox.secret or "", transport=fake.transport()
        )

    monkeypatch.setattr(gmail, "make_client", patched)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _eml(sender: str, subject: str, msg_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"Rechnungsstelle <{sender}>"
    msg["To"] = "verwaltung@example.com"
    msg["Subject"] = subject
    msg["Message-ID"] = msg_id
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Anbei die Rechnung.")
    msg.add_attachment(
        b"%PDF-1.4 rechnung", maintype="application", subtype="pdf", filename="rechnung.pdf"
    )
    return bytes(msg)


def _mailbox(client: TestClient, h: dict[str, str]) -> str:
    return str(
        _ok(
            client.post(
                f"{M}/mailboxes",
                json={
                    "address": f"verwaltung-{RUN}@example.com",
                    "kind": "gmail",
                    "secret": "refresh-token",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def _ingest(client: TestClient, h: dict[str, str], mailbox_id: str, raw: bytes) -> dict[str, Any]:
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("mail.eml", raw, "message/rfc822")},
            headers=h,
        ),
        201,
    )
    return dict(
        _ok(
            client.post(
                f"{M}/ingest",
                json={"document_id": doc["id"], "mailbox_id": mailbox_id},
                headers=h,
            ),
            201,
        )
    )


def test_forward_requires_configuration(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m32admin"))
    mailbox_id = _mailbox(client, h)
    msg = _ingest(client, h, mailbox_id, _eml("x@telekom.de", "Rechnung", f"<u1-{RUN}@t.de>"))
    refused = client.post(f"{M}/messages/{msg['id']}/forward-invoice", json={}, headers=h)
    assert refused.status_code == 409
    assert "nicht eingerichtet" in refused.text


def test_forward_sends_archives_and_learns_sender(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    h = bearer(login(client, world, "m32admin"))
    config = _ok(
        client.put(
            f"{M}/forwarding",
            json={"enabled": True, "address": TARGET, "mode": "suggest", "senders": []},
            headers=h,
        )
    )
    assert config["enabled"] is True
    mailbox_id = _mailbox(client, h)
    msg_id = f"<inv-{RUN}@telekom.de>"
    msg = _ingest(client, h, mailbox_id, _eml(f"tk-{RUN}@telekom.de", "Rechnung Mai", msg_id))
    fake.by_rfc822[msg_id] = "gm-1"
    out = _ok(
        client.post(
            f"{M}/messages/{msg['id']}/forward-invoice",
            json={"remember_sender": True},
            headers=h,
        )
    )
    assert out["forwarded_to"] == TARGET
    assert out["forwarded_at"] is not None
    assert out["status"] == "done"
    # Original haengt unveraendert als message/rfc822 an und ging an das Rechnungsprogramm.
    assert len(fake.sent) == 1
    forward = message_from_bytes(fake.sent[0])
    assert forward["To"] == TARGET
    assert forward["Subject"].startswith("WG:")
    attached = [p for p in forward.walk() if p.get_content_type() == "message/rfc822"]
    assert len(attached) == 1
    # Im Postfach archiviert (INBOX-Label entfernt) und Absender gelernt.
    assert fake.archived == ["gm-1"]
    learned = _ok(client.get(f"{M}/forwarding", headers=h))
    assert f"tk-{RUN}@telekom.de" in learned["senders"]
    # Doppelte Weiterleitung wird abgelehnt.
    again = client.post(f"{M}/messages/{msg['id']}/forward-invoice", json={}, headers=h)
    assert again.status_code == 409
    assert "bereits weitergeleitet" in again.text


def test_done_status_archives_in_gmail_best_effort(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    h = bearer(login(client, world, "m32admin"))
    mailbox_id = _mailbox(client, h)
    msg_id = f"<done-{RUN}@aok.de>"
    msg = _ingest(client, h, mailbox_id, _eml(f"service-{RUN}@aok.de", "Beitrag", msg_id))
    fake.by_rfc822[msg_id] = "gm-2"
    out = _ok(client.patch(f"{M}/messages/{msg['id']}", json={"status": "done"}, headers=h))
    assert out["status"] == "done"
    assert "gm-2" in fake.archived
    # Keine Weiterleitung ohne Klick oder Automatikfreigabe: nur archiviert.
    assert out["forwarded_at"] is None
