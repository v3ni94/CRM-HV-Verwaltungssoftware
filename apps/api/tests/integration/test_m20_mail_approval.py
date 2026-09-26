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
    """Minimal Gmail API: profile, token, send, search by Message-ID (M1), modify (archive)."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.send_forbidden = False
        # Simulates a sent mail that Gmail does not find by rfc822msgid (M1: resend once).
        self.search_empty = False
        self.archived: list[str] = []

    def sent_message_ids(self) -> list[str]:
        import email
        from email import policy

        return [
            str(email.message_from_bytes(raw, policy=policy.default)["Message-ID"])
            for raw in self.sent
        ]

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
            return httpx.Response(200, json={"id": f"sent{len(self.sent)}"})
        if path.endswith("/messages") and request.url.params.get("q", "").startswith(
            "rfc822msgid:"
        ):
            needle = request.url.params["q"].removeprefix("rfc822msgid:")
            hits = [
                {"id": f"sent{i + 1}"}
                for i, mid in enumerate(self.sent_message_ids())
                if mid.strip("<>") == needle and not self.search_empty
            ]
            return httpx.Response(200, json={"messages": hits} if hits else {})
        if path.endswith("/modify"):
            self.archived.append(path.rsplit("/", 2)[-2])
            return httpx.Response(200, json={})
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
            ("maapprover", "standard"),  # gets a custom approve role in the M16 test
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

    # Eigener Entwurf: Vier-Augen-Prinzip greift für den Ersteller/Einreicher, sobald er das
    # Kennzeichen Freigabepflicht trägt (M20-03, Betreiberentscheidung 26.09.2026); ohne
    # Kennzeichen dürfte er die dem Ticket zugeordnete Antwort selbst freigeben.
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    own_membership = next(m for m in members if m["user_id"] == str(world.users["maadmin"]))
    flag_url = f"/api/v1/tenant/members/{own_membership['membership_id']}/reply-approval"
    _ok(client.put(flag_url, json={"required": True, "reason": "neuer_mitarbeiter"}, headers=h))
    own = client.post(f"{M}/messages/{draft['id']}/approve", headers=h)
    assert own.status_code == 409
    assert "Vier-Augen" in own.json()["detail"]
    _ok(client.put(flag_url, json={"required": False}, headers=h))

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


def _gmail_box(client: TestClient, h: dict[str, str], address: str) -> dict[str, Any]:
    box = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": address, "kind": "gmail", "secret": "rt"}, headers=h
        ),
        201,
    )
    return dict(_ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h)))


def _pending_draft(
    client: TestClient, h: dict[str, str], box_id: str, tag: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    doc = _upload(
        client, h, f"{tag}.eml", _eml(f"m-{tag}@example.com", f"Frage {tag}", f"<{tag}@x>")
    )
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box_id}, headers=h), 201
    )
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))
    return msg, draft


def test_approve_never_sends_twice_after_commit_failure(
    client: TestClient, world: World, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 26.09.2026, M1: the status change after ``send_raw`` fails; the message stays
    ``sending`` with its Message-ID. The next approval finds the mail at Gmail by that id
    and records ``sent`` without a second send. Only when Gmail has no trace is the mail
    sent again, with the same Message-ID (idempotency key), never with a new one."""
    from mhvp.communication import routers

    h = bearer(login(client, world, "maadmin"))
    freigeber = bearer(login(client, world, "mafreigeber"))
    box = _gmail_box(client, h, f"m1-{RUN}@example.com")
    _, draft = _pending_draft(client, h, box["id"], f"m1a-{RUN}")

    real_record = routers._record_sent
    fail_next = {"value": True}

    async def flaky_record(*args: Any, **kwargs: Any) -> None:
        if fail_next["value"]:
            fail_next["value"] = False
            raise RuntimeError("Verbindung nach dem Versand verloren")
        await real_record(*args, **kwargs)

    monkeypatch.setattr(routers, "_record_sent", flaky_record)
    # The middleware answers 500 for the lost status change; the send already happened.
    assert client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber).status_code == 500
    assert len(fake.sent) == 1
    stuck = _ok(client.get(f"{M}/messages/{draft['id']}", headers=h))
    assert stuck["status"] == "sending"
    assert stuck["header_message_id"] == fake.sent_message_ids()[0]

    # Second approval: proof by Message-ID, no second send, Gmail id of the found mail.
    sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber))
    assert sent["status"] == "sent"
    assert sent["gmail_message_id"] == "sent1"
    assert len(fake.sent) == 1
    assert client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber).status_code == 409

    # No trace at Gmail: one resend with the same Message-ID.
    _, draft2 = _pending_draft(client, h, box["id"], f"m1b-{RUN}")
    fail_next["value"] = True
    assert client.post(f"{M}/messages/{draft2['id']}/approve", headers=freigeber).status_code == 500
    assert len(fake.sent) == 2
    fake.search_empty = True
    resent = _ok(client.post(f"{M}/messages/{draft2['id']}/approve", headers=freigeber))
    fake.search_empty = False
    assert resent["status"] == "sent"
    assert len(fake.sent) == 3
    ids = fake.sent_message_ids()
    assert ids[1] == ids[2] == resent["header_message_id"]
    assert ids[0] != ids[1]

    # A transport refusal (403) leaves the draft pending with the error, nothing sent.
    _, draft3 = _pending_draft(client, h, box["id"], f"m1c-{RUN}")
    fake.send_forbidden = True
    assert client.post(f"{M}/messages/{draft3['id']}/approve", headers=freigeber).status_code == 409
    fake.send_forbidden = False
    assert _ok(client.get(f"{M}/messages/{draft3['id']}", headers=h))["status"] == "pending"
    assert len(fake.sent) == 3


def test_approve_requires_mailbox_access_and_excludes_last_editor(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    """Review 26.09.2026, M16: an approver without access to the (non default) mailbox is
    refused; whoever last edited the draft text counts for the Vier-Augen-Prinzip."""
    h = bearer(login(client, world, "maadmin"))
    freigeber = bearer(login(client, world, "mafreigeber"))
    role = _ok(
        client.post(
            "/api/v1/tenant/roles",
            json={
                "code": f"mailapprove_{RUN}",
                "name": "Mailfreigabe",
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
    assert role["id"]
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    membership = next(m for m in members if m["user_id"] == str(world.users["maapprover"]))
    assert (
        client.put(
            f"/api/v1/tenant/members/{membership['membership_id']}/roles",
            json={"role_codes": [f"mailapprove_{RUN}"]},
            headers=h,
        ).status_code
        == 204
    )
    approver = bearer(login(client, world, "maapprover"))
    box = _gmail_box(client, h, f"m16-{RUN}@example.com")
    doc = _upload(
        client, h, "m16.eml", _eml(f"m16-{RUN}@example.com", f"M16 {RUN}", f"<m16-{RUN}@x>")
    )
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box["id"]}, headers=h),
        201,
    )
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    # The second admin edits the text, the first admin submits.
    _ok(
        client.patch(
            f"{M}/messages/{draft['id']}/draft",
            json={"body": "Geänderter Text."},
            headers=freigeber,
        )
    )
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))

    # Last editor cannot approve (Vier-Augen-Prinzip).
    edited = client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber)
    assert edited.status_code == 409
    assert "Vier-Augen" in edited.json()["detail"]

    # Approver without a grant for the mailbox: the draft is not even visible (404).
    assert client.post(f"{M}/messages/{draft['id']}/approve", headers=approver).status_code == 404
    _ok(
        client.put(
            f"{M}/mailboxes/{box['id']}/users",
            json={"user_ids": [str(world.users["maapprover"])]},
            headers=h,
        )
    )
    sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=approver))
    assert sent["status"] == "sent"
    assert sent["approved_by"] == str(world.users["maapprover"])


def _invoice_eml(sender: str, subject: str, msg_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Lieferant <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Anbei unsere Rechnung.")
    msg.add_attachment(
        b"%PDF-1.4 rechnung", maintype="application", subtype="pdf", filename="Rechnung.pdf"
    )
    return bytes(msg)


def test_invoice_forwarding_runs_once_after_commit(
    client: TestClient, world: World, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 26.09.2026, M13: the automatic forwarding is only queued inside the ingest and
    sent by the follow up job after the commit, exactly once per message; a rolled back
    ingest forwards nothing."""
    import email
    from email import policy

    from mhvp.communication import services

    # Without a worker the follow up job runs inline (``ai_inline``), like the archive job.
    state = client.app.state  # type: ignore[attr-defined]
    monkeypatch.setattr(state, "settings", state.settings.model_copy(update={"ai_inline": True}))
    h = bearer(login(client, world, "maadmin"))
    supplier = f"telekom-m13-{RUN}@example.com"
    _ok(
        client.put(
            f"{M}/invoice-forwarding",
            json={
                "enabled": True,
                "forward_address": "buchhaltung@example.com",
                "sender_allowlist": [supplier],
            },
            headers=h,
        )
    )
    box = _gmail_box(client, h, f"m13-{RUN}@example.com")
    doc = _upload(
        client, h, "m13.eml", _invoice_eml(supplier, f"Rechnung 4711 {RUN}", f"<m13-{RUN}@x>")
    )
    before = len(fake.sent)
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box["id"]}, headers=h),
        201,
    )
    forward = msg["classification"]["invoice_forward"]
    assert (forward["decision"], forward["status"]) == ("forward", "sent")
    assert forward["forwarded_to"] == "buchhaltung@example.com"
    assert len(fake.sent) == before + 1
    parsed = email.message_from_bytes(fake.sent[-1], policy=policy.default)
    assert parsed["Subject"] == f"Weiterleitung: Rechnung 4711 {RUN}"
    assert [a.get_filename() for a in parsed.iter_attachments()] == ["Rechnung.pdf"]

    # Re-import of the same mail: known message, no second forwarding; the job finds
    # nothing queued.
    again = _ok(client.post(f"{M}/ingest", json={"document_id": doc}, headers=h), 201)
    assert again["id"] == msg["id"]
    assert len(fake.sent) == before + 1
    from mhvp.communication.tasks import forward_queued_once

    settings = client.app.state.settings  # type: ignore[attr-defined]
    assert asyncio.run(forward_queued_once(settings, world.tenant_a)) == {
        "forwarded": 0,
        "failed": 0,
    }
    assert len(fake.sent) == before + 1

    # Ingest that fails after the classification rolls back: nothing is forwarded.
    real = services._classify_and_queue_forward

    async def classify_then_fail(*args: Any, **kwargs: Any) -> None:
        await real(*args, **kwargs)
        raise RuntimeError("Fehler nach der Klassifikation")

    monkeypatch.setattr(services, "_classify_and_queue_forward", classify_then_fail)
    doc2 = _upload(
        client, h, "m13b.eml", _invoice_eml(supplier, f"Rechnung 4712 {RUN}", f"<m13b-{RUN}@x>")
    )
    failed = client.post(
        f"{M}/ingest", json={"document_id": doc2, "mailbox_id": box["id"]}, headers=h
    )
    assert failed.status_code == 500
    assert len(fake.sent) == before + 1
    assert not [
        m
        for m in _ok(client.get(f"{M}/messages", headers=h))
        if m["subject"] == f"Rechnung 4712 {RUN}"
    ]
