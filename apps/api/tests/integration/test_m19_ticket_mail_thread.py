"""Ticket-Mailverlauf, Antwort aus dem Ticket und Ticketnummer im Betreff (operator
26.09.2026, docs/rules/M19-02-tnr.md): die Antwort trägt genau einmal ``TNR#<nummer>``,
eine erneute Antwort verdoppelt die Kennung nicht, eingehende Mails mit Kennung werden dem
Ticket des Mandanten zugeordnet (nicht über Mandantengrenzen), der Verlauf listet Anhänge mit
Name, Größe und Typ, die Anhangsvorschau ist auf Ticket-Mails beschränkt, Antworten brauchen
tickets:update und communication:update, der Versand bleibt beim Vier-Augen-Weg."""

import asyncio
import email
from collections.abc import Iterator
from email import policy
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
from tests.integration.test_m20_mail_approval import FakeGmail, _upload

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"
M = "/api/v1/mail"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _eml(
    sender: str,
    subject: str,
    msg_id: str,
    *,
    cc: str | None = None,
    in_reply_to: str | None = None,
    html: str | None = None,
    attachment: tuple[str, bytes, str] | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    if cc:
        msg["Cc"] = cc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Im Bad tropft es aus der Decke.\n\n> alter Text")
    if html:
        msg.add_alternative(html, subtype="html")
    if attachment:
        name, data, mime = attachment
        maintype, subtype = mime.split("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return bytes(msg)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"tmt-{RUN}", name=f"Thread {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"tm2-{RUN}", name=f"Thread2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("tmtadmin", "tenant_admin", a),
            ("tmfreigeber", "tenant_admin", a),
            ("tmreader", "read_only", a),
            ("tmotherb", "tenant_admin", b),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _mailbox(client: TestClient, admin: dict[str, str], address: str) -> Any:
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": address, "kind": "gmail", "secret": "tm"},
            headers=admin,
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=admin))
    return box


def _ingest(client: TestClient, h: dict[str, str], raw: bytes, mailbox_id: str, name: str) -> Any:
    eml = _upload(client, h, name, raw)
    return _ok(
        client.post(f"{M}/ingest", json={"document_id": eml, "mailbox_id": mailbox_id}, headers=h),
        201,
    )


def test_ticket_thread_reply_with_tnr_and_inbound_assignment(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    admin = bearer(login(client, world, "tmtadmin"))
    freigeber = bearer(login(client, world, "tmfreigeber"))
    reader = bearer(login(client, world, "tmreader"))
    other = bearer(login(client, world, "tmotherb"))
    box = _mailbox(client, admin, f"info-tm{RUN}@example.com")
    sender = f"erika-tm{RUN}@example.com"

    # Eingehende Mail mit Kopie, HTML und Bildanhang; Ticket daraus.
    raw = _eml(
        sender,
        f"Wasserschaden Küche {RUN}",
        f"<tm1-{RUN}@x>",
        cc=f"hans-tm{RUN}@example.com, info-tm{RUN}@example.com",
        html="<p>Im Bad <b>tropft</b> es.</p><script>alert(1)</script>",
        attachment=("foto.png", PNG, "image/png"),
    )
    msg = _ingest(client, admin, raw, box["id"], "tm1.eml")
    assert msg["cc_addresses"] == [f"hans-tm{RUN}@example.com", f"info-tm{RUN}@example.com"]
    assert "<b>tropft</b>" in msg["body_html"]
    assert "script" not in msg["body_html"]
    ticket_ref = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), 201)
    ticket_id, number = ticket_ref["ticket_id"], ticket_ref["number"]

    # Verlauf: eine eingehende Mail mit Anhangsliste (Name, Größe, Typ) und Postfachadresse.
    thread = _ok(client.get(f"{T}/{ticket_id}/messages", headers=admin))
    assert [m["direction"] for m in thread] == ["in"]
    assert thread[0]["mailbox_address"] == f"info-tm{RUN}@example.com"
    att = thread[0]["attachments"]
    assert len(att) == 1
    assert att[0]["filename"] == "foto.png"
    assert att[0]["mime_type"] == "image/png"
    assert att[0]["size"] == len(PNG)
    assert att[0]["missing"] is False
    document_id = att[0]["document_id"]

    # Anhangsvorschau nur über den Ticketbezug: Bild inline, Download als Datei, fremder
    # Mandant und fremdes Ticket ohne Treffer.
    preview = client.get(f"{T}/{ticket_id}/mail-attachments/{document_id}/content", headers=admin)
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"].startswith("image/png")
    assert preview.headers["content-disposition"].startswith("inline")
    assert preview.content == PNG
    download = client.get(
        f"{T}/{ticket_id}/mail-attachments/{document_id}/content",
        params={"download": "true"},
        headers=admin,
    )
    assert download.headers["content-disposition"].startswith("attachment")
    assert (
        client.get(
            f"{T}/{ticket_id}/mail-attachments/{document_id}/content", headers=other
        ).status_code
        == 404
    )
    assert client.get(f"{T}/{ticket_id}/messages", headers=other).status_code == 404

    # Postfachzugriff (H2): ohne Freigabe für das (nicht als Standard markierte) Postfach
    # sieht die Leserolle weder Verlauf noch Einzelmail, Thread oder Anhang; nach Freigabe
    # per PUT /mail/mailboxes/{id}/users ist alles lesbar.
    assert _ok(client.get(f"{T}/{ticket_id}/messages", headers=reader)) == []
    assert client.get(f"{M}/messages/{msg['id']}", headers=reader).status_code == 404
    assert client.get(f"{M}/messages/{msg['id']}/thread", headers=reader).status_code == 404
    assert (
        client.get(
            f"{T}/{ticket_id}/mail-attachments/{document_id}/content", headers=reader
        ).status_code
        == 404
    )
    _ok(
        client.put(
            f"{M}/mailboxes/{box['id']}/users",
            json={"user_ids": [str(world.users["tmreader"])]},
            headers=admin,
        )
    )
    assert len(_ok(client.get(f"{T}/{ticket_id}/messages", headers=reader))) == 1
    assert _ok(client.get(f"{M}/messages/{msg['id']}", headers=reader))["id"] == msg["id"]
    assert len(_ok(client.get(f"{M}/messages/{msg['id']}/thread", headers=reader))) == 1

    # Vorschau der Antwortvorlage liefert An und Kopie aus der Ursprungsmail (ohne eigenes
    # Postfach in der Kopie).
    tpl = _ok(
        client.post(
            f"{T}/reply-templates",
            json={"name": f"Eingang {RUN}", "subject": "Ihr Anliegen", "body": "{anrede},"},
            headers=admin,
        ),
        201,
    )
    pv = _ok(client.get(f"{T}/{ticket_id}/reply-templates/{tpl['id']}/preview", headers=admin))
    assert pv["to_addresses"] == [sender]
    assert pv["cc_addresses"] == [f"hans-tm{RUN}@example.com"]

    # Vorbelegung ohne Vorlage: An, Kopie, Betreff mit Kennung, Postfach.
    ctx = _ok(client.get(f"{T}/{ticket_id}/reply-context", headers=reader))
    assert ctx["to_addresses"] == [sender]
    assert ctx["cc_addresses"] == [f"hans-tm{RUN}@example.com"]
    assert ctx["subject"] == f"AW: Wasserschaden Küche {RUN} TNR#{number}"
    assert ctx["reply_to_message_id"] == msg["id"]
    assert ctx["mailbox_address"] == f"info-tm{RUN}@example.com"
    assert ctx["can_send"] is True

    # Berechtigung: Leserolle darf nicht antworten (kein tickets:update).
    reply = {
        "subject": f"AW: Wasserschaden Küche {RUN}",
        "body": "Wir kümmern uns.",
        "cc_addresses": [f"hans-tm{RUN}@example.com"],
        "reply_to_message_id": msg["id"],
        "confirm": True,
    }
    assert client.post(f"{T}/{ticket_id}/reply", json=reply, headers=reader).status_code == 403
    # Fremde Nachricht als Bezug wird abgewiesen.
    foreign_ref = client.post(
        f"{T}/{ticket_id}/reply",
        json=reply | {"reply_to_message_id": "01920000-0000-7000-8000-0000000000aa"},
        headers=admin,
    )
    assert foreign_ref.status_code == 404, foreign_ref.text

    # Antwort: Entwurf im Postausgang (pending), Betreff mit genau einer Kennung TNR#<nummer>,
    # Kopie übernommen, In-Reply-To und References gesetzt.
    first = _ok(client.post(f"{T}/{ticket_id}/reply", json=reply, headers=admin), 201)
    assert first["status"] == "pending"
    assert first["subject"] == f"AW: Wasserschaden Küche {RUN} TNR#{number}"
    assert first["subject"].count("TNR#") == 1
    assert first["cc_addresses"] == [f"hans-tm{RUN}@example.com"]
    assert first["in_reply_to"] == f"<tm1-{RUN}@x>"
    assert first["references_header"] == f"<tm1-{RUN}@x>"
    assert len(fake.sent) == 0

    # Erneute Antwort mit bereits gekennzeichnetem Betreff: keine doppelte Kennung.
    second = _ok(
        client.post(
            f"{T}/{ticket_id}/reply",
            json=reply | {"subject": first["subject"], "cc_addresses": []},
            headers=admin,
        ),
        201,
    )
    assert second["subject"] == first["subject"]
    assert second["subject"].count("TNR#") == 1

    # Vier-Augen-Freigabe sendet mit Cc, In-Reply-To und References; Fehler bleibt vermerkt.
    fake.send_forbidden = True
    failed = client.post(f"{M}/messages/{first['id']}/approve", headers=freigeber)
    assert failed.status_code == 409, failed.text
    after_fail = _ok(client.get(f"{M}/messages/{first['id']}", headers=admin))
    assert after_fail["status"] == "pending"
    assert after_fail["send_error"]
    fake.send_forbidden = False
    sent = _ok(client.post(f"{M}/messages/{first['id']}/approve", headers=freigeber))
    assert sent["status"] == "sent"
    assert sent["send_error"] is None
    parsed = email.message_from_bytes(fake.sent[0], policy=policy.default)
    assert parsed["Subject"] == f"AW: Wasserschaden Küche {RUN} TNR#{number}"
    assert parsed["Cc"] == f"hans-tm{RUN}@example.com"
    assert parsed["In-Reply-To"] == f"<tm1-{RUN}@x>"
    assert parsed["References"] == f"<tm1-{RUN}@x>"

    # Verlauf chronologisch nach Empfang, Versand oder Anlage: Eingang, zweiter Entwurf
    # (pending, angelegt vor dem Versand), gesendete Antwort.
    thread = _ok(client.get(f"{T}/{ticket_id}/messages", headers=admin))
    assert [(m["direction"], m["status"]) for m in thread] == [
        ("in", "assigned"),
        ("out", "pending"),
        ("out", "sent"),
    ]

    # Eingehende Mail ohne Thread-Kopfzeilen, aber mit Kennung im Betreff: Zuordnung zum Ticket.
    follow = _ingest(
        client,
        admin,
        _eml(sender, f"Re: Rückfrage TNR#{number}", f"<tm2-{RUN}@x>"),
        box["id"],
        "tm2.eml",
    )
    assert follow["ticket_id"] == ticket_id
    assert follow["thread_id"] == msg["id"]
    thread = _ok(client.get(f"{T}/{ticket_id}/messages", headers=admin))
    assert len(thread) == 4
    assert follow["id"] in {m["id"] for m in thread}
    tickets = _ok(client.get(T, headers=admin))
    assert not [t for t in tickets if t["title"] == f"Re: Rückfrage TNR#{number}"]

    # Fremder Absender mit Kennung (H5): keine Zuordnung, nur Vorschlag; das Ticket bleibt
    # unverändert und der Antwortempfänger bleibt der ursprüngliche Absender.
    stranger = _ingest(
        client,
        admin,
        _eml(f"fremd-tm{RUN}@example.com", f"Bitte um Info TNR#{number}", f"<tm5-{RUN}@x>"),
        box["id"],
        "tm5.eml",
    )
    assert stranger["ticket_id"] != ticket_id
    assert stranger["classification"]["tnr_suggestion"]["ticket_id"] == ticket_id
    assert stranger["classification"]["tnr_suggestion"]["number"] == number
    assert len(_ok(client.get(f"{T}/{ticket_id}/messages", headers=admin))) == 4
    ctx = _ok(client.get(f"{T}/{ticket_id}/reply-context", headers=admin))
    assert ctx["to_addresses"] == [sender]
    # Landet eine fremde Adresse über die Thread-Kopfzeilen im Ticket (Antwort auf unsere
    # gesendete Mail von einer anderen Adresse), bleibt sie bei einer Antwort auf diese Mail
    # nur Vorschlag zur ausdrücklichen Auswahl, nicht Empfänger.
    via_thread = _ingest(
        client,
        admin,
        _eml(
            f"fremd2-tm{RUN}@example.com",
            f"Re: Wasserschaden Küche {RUN}",
            f"<tm5b-{RUN}@x>",
            in_reply_to=sent["header_message_id"],
        ),
        box["id"],
        "tm5b.eml",
    )
    assert via_thread["ticket_id"] == ticket_id
    ctx = _ok(
        client.get(
            f"{T}/{ticket_id}/reply-context",
            params={"reply_to_message_id": via_thread["id"]},
            headers=admin,
        )
    )
    assert ctx["to_addresses"] == [sender]
    assert ctx["unverified_sender"] == f"fremd2-tm{RUN}@example.com"

    # Fremder Mandant: dieselbe Nummer trifft nie das Ticket des anderen Mandanten; ohne
    # eigenes Ticket mit dieser Nummer entsteht dort ein neues Ticket.
    other_box = _mailbox(client, other, f"info-tm2-{RUN}@example.com")
    stray = _ingest(
        client,
        other,
        _eml("fremd@example.com", f"Frage TNR#{number}", f"<tm3-{RUN}@x>"),
        other_box["id"],
        "tm3.eml",
    )
    assert stray["ticket_id"] != ticket_id
    assert "tnr_suggestion" not in stray["classification"]
    assert len(_ok(client.get(f"{T}/{ticket_id}/messages", headers=admin))) == 5

    # Dokumentsuche für eigene Anhänge im Antwortformular.
    found = _ok(client.get(f"{T}/{ticket_id}/reply-documents", params={"q": "foto"}, headers=admin))
    assert any(d["document_id"] == document_id for d in found)
    assert found[0]["size"] == len(PNG)
    assert (
        client.get(
            f"{T}/{ticket_id}/reply-documents", params={"q": "foto"}, headers=other
        ).status_code
        == 404
    )


def test_mail_workspace_reply_draft_carries_tnr(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "tmtadmin"))
    box = _mailbox(client, admin, f"info-tm-b{RUN}@example.com")
    msg = _ingest(
        client,
        admin,
        _eml(f"karl-tm{RUN}@example.com", f"Heizung kalt {RUN}", f"<tm4-{RUN}@x>"),
        box["id"],
        "tm4.eml",
    )
    ticket_ref = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), 201)
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", json={}, headers=admin), 201)
    assert draft["subject"] == f"AW: Heizung kalt {RUN} TNR#{ticket_ref['number']}"
    assert draft["references_header"] == f"<tm4-{RUN}@x>"


def test_reply_to_closed_ticket_reopens_and_notifies(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "tmtadmin"))
    box = _mailbox(client, admin, f"info-tm-c{RUN}@example.com")
    sender = f"lena-tm{RUN}@example.com"
    msg = _ingest(
        client,
        admin,
        _eml(sender, f"Tür klemmt {RUN}", f"<tm6-{RUN}@x>"),
        box["id"],
        "tm6.eml",
    )
    ticket_ref = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), 201)
    ticket_id, number = ticket_ref["ticket_id"], ticket_ref["number"]
    _ok(
        client.patch(
            f"{T}/{ticket_id}",
            json={"assignee_user_id": str(world.users["tmtadmin"]), "status": "done"},
            headers=admin,
        )
    )
    assert _ok(client.get(f"{T}/{ticket_id}", headers=admin))["status"] == "done"

    # Kundenantwort im Thread auf das erledigte Ticket: wieder in Bearbeitung, Ereignis
    # ``reopened``, Benachrichtigung an den Bearbeiter (H4).
    follow = _ingest(
        client,
        admin,
        _eml(sender, f"Re: Tür klemmt {RUN}", f"<tm7-{RUN}@x>", in_reply_to=f"<tm6-{RUN}@x>"),
        box["id"],
        "tm7.eml",
    )
    assert follow["ticket_id"] == ticket_id
    detail = _ok(client.get(f"{T}/{ticket_id}", headers=admin))
    assert detail["status"] == "in_progress"
    assert detail["resolved_at"] is None
    kinds = [e["kind"] for e in detail["events"]]
    assert "reopened" in kinds
    assert kinds.count("mail_received") == 1
    notes = _ok(client.get("/api/v1/workspace/notifications", headers=admin))
    items = notes if isinstance(notes, list) else notes.get("items", [])
    assert any(
        n["kind"] == "ticket.mail_received" and str(number) in n["title"] and "wieder" in n["title"]
        for n in items
    ), items

    # Weitere Mail am offenen Ticket: Benachrichtigung ohne erneute Wiedereröffnung.
    _ingest(
        client,
        admin,
        _eml(sender, f"Re: Tür klemmt {RUN} TNR#{number}", f"<tm8-{RUN}@x>"),
        box["id"],
        "tm8.eml",
    )
    detail = _ok(client.get(f"{T}/{ticket_id}", headers=admin))
    assert [e["kind"] for e in detail["events"]].count("reopened") == 1
    assert [e["kind"] for e in detail["events"]].count("mail_received") == 2
