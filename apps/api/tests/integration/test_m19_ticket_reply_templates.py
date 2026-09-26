"""Antwortvorlagen für Tickets (operator 26.09.2026): CRUD je Mandant, Platzhalter werden in
der Vorschau aus Ticket und Kontakt gefüllt, unbekannte Platzhalter werden abgewiesen,
Mandantentrennung, Versand nur mit ausdrücklicher Bestätigung und nur über den bestehenden
Antwortweg (Einreichung, Vier-Augen-Freigabe, Postfach des Tickets) inklusive Standardanhang."""

import asyncio
import email
from collections.abc import Iterator
from email import policy
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
from tests.integration.test_m20_mail_approval import FakeGmail, _eml, _upload

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"
M = "/api/v1/mail"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rt-{RUN}", name=f"Antwort {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rt2-{RUN}", name=f"Antwort2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("rtadmin", "tenant_admin", a),
            ("rtfreigeber", "tenant_admin", a),
            ("rtreader", "read_only", a),
            ("rtotherb", "tenant_admin", b),
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


def _upload_pdf(c: TestClient, h: dict[str, str], name: str) -> str:
    data = b"%PDF-1.4\n%Merkblatt\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "application/pdf")}, headers=h),
            201,
        )["id"]
    )


def test_reply_template_crud_placeholders_and_tenant_separation(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "rtadmin"))
    reader = bearer(login(client, world, "rtreader"))
    other = bearer(login(client, world, "rtotherb"))

    # Unbekannte Platzhalter werden abgewiesen, damit kein leerer Marker hinausgeht.
    bad = client.post(
        f"{T}/reply-templates",
        json={"name": f"Falsch {RUN}", "subject": "x", "body": "Hallo {mieter}"},
        headers=admin,
    )
    assert bad.status_code == 422, bad.text
    assert "{mieter}" in bad.json()["detail"]

    # Unbekannter Anhang wird abgewiesen.
    missing = client.post(
        f"{T}/reply-templates",
        json={
            "name": f"Anhang fehlt {RUN}",
            "subject": "x",
            "body": "y",
            "attachment_document_ids": ["01920000-0000-7000-8000-0000000000aa"],
        },
        headers=admin,
    )
    assert missing.status_code == 404, missing.text

    doc = _upload_pdf(client, admin, "merkblatt.pdf")
    tpl = _ok(
        client.post(
            f"{T}/reply-templates",
            json={
                "name": f"Eingangsbestätigung {RUN}",
                "subject": "Ihr Anliegen zu Ticket {ticketnummer}",
                "body": "{anrede},\n\nvielen Dank für Ihre Nachricht zu {objekt}.\n\n{name}",
                "topic": "vertrag",
                "attachment_document_ids": [doc],
            },
            headers=admin,
        ),
        201,
    )
    assert tpl["topic"] == "vertrag"
    assert tpl["attachment_document_ids"] == [doc]

    # Gleicher Name im Mandanten: Konflikt; anderer Mandant darf denselben Namen verwenden.
    dup = client.post(
        f"{T}/reply-templates",
        json={"name": tpl["name"], "subject": "x", "body": "y"},
        headers=admin,
    )
    assert dup.status_code == 409
    _ok(
        client.post(
            f"{T}/reply-templates",
            json={"name": tpl["name"], "subject": "x", "body": "y"},
            headers=other,
        ),
        201,
    )

    # Lesen mit tickets:read, Schreiben nur mit tickets:update oder Admin.
    listed = _ok(client.get(f"{T}/reply-templates", headers=reader))
    assert tpl["id"] in {t["id"] for t in listed}
    assert (
        client.post(
            f"{T}/reply-templates",
            json={"name": f"Nur lesen {RUN}", "subject": "x", "body": "y"},
            headers=reader,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{T}/reply-templates/{tpl['id']}", json={"subject": "neu"}, headers=reader
        ).status_code
        == 403
    )
    placeholders = _ok(client.get(f"{T}/reply-templates/placeholders", headers=reader))
    assert {"anrede", "name", "objekt", "ticketnummer"} <= set(placeholders)

    # Mandantentrennung: der andere Mandant sieht und ändert die Vorlage nicht.
    assert tpl["id"] not in {
        t["id"] for t in _ok(client.get(f"{T}/reply-templates", headers=other))
    }
    assert client.get(f"{T}/reply-templates/{tpl['id']}", headers=other).status_code == 404
    assert (
        client.patch(
            f"{T}/reply-templates/{tpl['id']}", json={"subject": "fremd"}, headers=other
        ).status_code
        == 404
    )
    assert client.delete(f"{T}/reply-templates/{tpl['id']}", headers=other).status_code == 404

    # Unbekanntes Thema wird abgewiesen; Bearbeiten und Deaktivieren funktionieren.
    assert (
        client.patch(
            f"{T}/reply-templates/{tpl['id']}", json={"topic": "gibtesnicht"}, headers=admin
        ).status_code
        == 422
    )
    patched = _ok(
        client.patch(
            f"{T}/reply-templates/{tpl['id']}",
            json={"subject": "Ticket {ticketnummer}: Eingang bestätigt", "active": False},
            headers=admin,
        )
    )
    assert patched["active"] is False
    assert patched["subject"].startswith("Ticket {ticketnummer}")
    only_active = _ok(client.get(f"{T}/reply-templates", params={"active": True}, headers=admin))
    assert tpl["id"] not in {t["id"] for t in only_active}
    detail = _ok(client.get(f"{T}/reply-templates/{tpl['id']}", headers=admin))
    assert detail["attachments"][0]["filename"] == "merkblatt.pdf"
    assert detail["attachments"][0]["missing"] is False

    second = _ok(
        client.post(
            f"{T}/reply-templates",
            json={"name": f"Löschen {RUN}", "subject": "x", "body": "y"},
            headers=admin,
        ),
        201,
    )
    assert client.delete(f"{T}/reply-templates/{second['id']}", headers=admin).status_code == 204
    assert client.get(f"{T}/reply-templates/{second['id']}", headers=admin).status_code == 404


def test_preview_and_reply_requires_confirmation_and_uses_ticket_mailbox(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    admin = bearer(login(client, world, "rtadmin"))
    freigeber = bearer(login(client, world, "rtfreigeber"))
    other = bearer(login(client, world, "rtotherb"))

    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info-rt{RUN}@example.com", "kind": "gmail", "secret": "rt"},
            headers=admin,
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=admin))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "salutation": "Frau",
                "first_name": "Erika",
                "last_name": f"Muster{RUN}",
                "emails": [{"email": f"erika-rt{RUN}@example.com", "is_primary": True}],
            },
            headers=admin,
        ),
        201,
    )
    sender = f"erika-rt{RUN}@example.com"
    raw = _eml(sender, f"Frage zur Abrechnung {RUN}", f"<rt1-{RUN}@x>")
    eml = _upload(client, admin, "rt.eml", raw)
    msg = _ok(
        client.post(
            f"{M}/ingest", json={"document_id": eml, "mailbox_id": box["id"]}, headers=admin
        ),
        201,
    )
    ticket_ref = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), 201)
    ticket_id = ticket_ref["ticket_id"]
    _ok(client.patch(f"{T}/{ticket_id}", json={"contact_id": contact["id"]}, headers=admin))

    doc = _upload_pdf(client, admin, "hinweise.pdf")
    tpl = _ok(
        client.post(
            f"{T}/reply-templates",
            json={
                "name": f"Vorschau {RUN}",
                "subject": "AW: Ticket {ticketnummer}",
                "body": "{anrede},\n\nIhr Anliegen ({tickettitel}) liegt uns vor.\n\n{name}, {datum}",
                "attachment_document_ids": [doc],
            },
            headers=admin,
        ),
        201,
    )

    preview = _ok(client.get(f"{T}/{ticket_id}/reply-templates/{tpl['id']}/preview", headers=admin))
    assert preview["subject"] == f"AW: Ticket {ticket_ref['number']}"
    assert preview["body"].startswith(f"Sehr geehrte Frau Muster{RUN},")
    assert f"Frage zur Abrechnung {RUN}" in preview["body"]
    assert f"Erika Muster{RUN}" in preview["body"]
    assert preview["to_addresses"] == [sender]
    assert preview["mailbox_id"] == box["id"]
    assert preview["can_send"] is True
    assert preview["attachments"][0]["filename"] == "hinweise.pdf"
    assert "{" not in preview["subject"]
    # Fremder Mandant: weder Ticket noch Vorlage sichtbar.
    assert (
        client.get(
            f"{T}/{ticket_id}/reply-templates/{tpl['id']}/preview", headers=other
        ).status_code
        == 404
    )

    # Ohne ausdrückliche Bestätigung wird nichts angelegt.
    denied = client.post(
        f"{T}/{ticket_id}/reply",
        json={
            "template_id": tpl["id"],
            "subject": preview["subject"],
            "body": preview["body"],
            "attachment_document_ids": [doc],
        },
        headers=admin,
    )
    assert denied.status_code == 409, denied.text
    assert "Bestätigung" in denied.json()["detail"]
    outbound = _ok(client.get(f"{M}/messages", params={"direction": "out"}, headers=admin))
    assert not [m for m in outbound if m["ticket_id"] == ticket_id]
    assert len(fake.sent) == 0

    # Unausgefüllter Platzhalter im bearbeiteten Text wird abgewiesen.
    assert (
        client.post(
            f"{T}/{ticket_id}/reply",
            json={"subject": "x", "body": "Hallo {mieter}", "confirm": True},
            headers=admin,
        ).status_code
        == 422
    )

    # Mit Bestätigung: Nachricht am Ticket, Postfach des Tickets, eingereicht (pending), nicht
    # gesendet. Der Versand bleibt dem bestehenden Antwortweg (Freigabe) vorbehalten.
    sent_req = _ok(
        client.post(
            f"{T}/{ticket_id}/reply",
            json={
                "template_id": tpl["id"],
                "subject": preview["subject"],
                "body": preview["body"] + "\n\nMit freundlichen Grüßen",
                "attachment_document_ids": [doc],
                "confirm": True,
            },
            headers=admin,
        ),
        201,
    )
    assert sent_req["status"] == "pending"
    assert sent_req["mailbox_id"] == box["id"]
    assert sent_req["to_addresses"] == [sender]
    assert sent_req["ticket_id"] == ticket_id
    assert sent_req["attachment_document_ids"] == [doc]
    assert len(fake.sent) == 0
    events = _ok(client.get(f"{T}/{ticket_id}", headers=admin))["events"]
    assert any(e["kind"] == "reply_submitted" for e in events)

    # Vier-Augen: eigener Entwurf nicht freigebbar; anderer Nutzer sendet mit Anhang.
    assert client.post(f"{M}/messages/{sent_req['id']}/approve", headers=admin).status_code == 409
    sent = _ok(client.post(f"{M}/messages/{sent_req['id']}/approve", headers=freigeber))
    assert sent["status"] == "sent"
    assert len(fake.sent) == 1
    parsed = email.message_from_bytes(fake.sent[0], policy=policy.default)
    assert parsed["From"] == f"info-rt{RUN}@example.com"
    assert parsed["To"] == sender
    assert parsed["In-Reply-To"] == f"<rt1-{RUN}@x>"
    attachments = [p.get_filename() for p in parsed.iter_attachments()]
    assert attachments == ["hinweise.pdf"]
    assert any(
        e["kind"] == "mail_sent"
        for e in _ok(client.get(f"{T}/{ticket_id}", headers=admin))["events"]
    )
