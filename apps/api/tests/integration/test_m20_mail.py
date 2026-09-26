"""M20 mailbox with synthetic e-mails: intake from .eml, sender matched to contact, property
number and urgency by rules, template category, appointment suggestion, attachment stored,
re-import without second case, threading of replies, ticket from mail, reply draft, sending
refused without configured mailbox, mailbox secret never returned."""

import asyncio
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ml-{RUN}", name=f"Mail {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"mlb-{RUN}", name=f"Mail B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("m20admin", "tenant_admin", a),
            ("m20read", "read_only_master_data", a),
            ("m20adminb", "tenant_admin", b),
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _eml(
    sender: str,
    subject: str,
    body: str,
    msg_id: str,
    reply_to: str | None = None,
    attach: bool = False,
) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieterin <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Wed, 23 Sep 2026 09:00:00 +0200"
    if reply_to:
        msg["In-Reply-To"] = reply_to
    msg.set_content(body)
    if attach:
        msg.add_attachment(
            b"%PDF-1.4 test", maintype="application", subtype="pdf", filename="foto.pdf"
        )
    return bytes(msg)


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "message/rfc822")}, headers=h),
            201,
        )["id"]
    )


def test_mail_intake_to_ticket(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m20admin"))
    sender = f"erika{RUN}@example.com"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "salutation": "Frau",
                "first_name": "Erika",
                "last_name": f"Post{RUN}",
                "emails": [{"email": sender}],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "801", "name": "Posthaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/ticket-templates",
            json={"category": "Wasserschaden", "title": "Wasserschaden", "sla_hours": 12},
            headers=h,
        ),
        201,
    )
    box = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": "info@example.com", "secret": "geheim"}, headers=h
        ),
        201,
    )
    assert box["has_secret"] is True
    assert "secret" not in box

    raw = _eml(
        sender,
        "Wasserschaden Objekt 801",
        "Guten Tag, dringend: Wasser tropft. Termin am 05.10.2026 um 10:30 Uhr möglich.",
        "<m1@example.test>",
        attach=True,
    )
    doc = _upload(client, h, "m1.eml", raw)
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box["id"]}, headers=h),
        201,
    )
    assert msg["contact_id"] == contact["id"]
    assert msg["property_id"] is not None
    assert msg["classification"]["urgency"] == "urgent"
    assert msg["classification"]["category"] == "Wasserschaden"
    assert msg["appointment_suggestions"][0]["date"] == "2026-10-05"
    assert msg["appointment_suggestions"][0]["time"] == "2026-10-05T10:30:00"
    assert len(msg["attachment_document_ids"]) == 1
    again = _ok(client.post(f"{M}/ingest", json={"document_id": doc}, headers=h), 201)
    assert again["id"] == msg["id"]

    reply = _ok(
        client.post(
            f"{M}/ingest",
            json={
                "document_id": _upload(
                    client,
                    h,
                    "m2.eml",
                    _eml(
                        sender,
                        "AW: Wasserschaden",
                        "Danke",
                        "<m2@example.test>",
                        "<m1@example.test>",
                    ),
                )
            },
            headers=h,
        ),
        201,
    )
    assert reply["thread_id"] == msg["id"]

    ticket = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=h), 201)
    assert ticket["priority"] == "urgent"
    assert (
        _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=h), 201)["ticket_id"]
        == ticket["ticket_id"]
    )
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    assert draft["body"].startswith(f"Sehr geehrte Frau Post{RUN},")
    assert f"Vorgang {ticket['number']}" in draft["body"]
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))
    blocked = client.post(f"{M}/messages/{draft['id']}/approve", headers=h)
    assert blocked.status_code == 409  # own draft: Vier-Augen-Prinzip
    cal = _ok(
        client.post(
            f"{M}/messages/{msg['id']}/appointment",
            json={"index": 0, "title": "Besichtigung Wasserschaden"},
            headers=h,
        ),
        201,
    )
    assert cal["date"] == "2026-10-05"
    listed = _ok(client.get(f"{M}/messages", params={"contact_id": contact["id"]}, headers=h))
    assert {m["id"] for m in listed} >= {msg["id"], reply["id"]}
    reader = bearer(login(client, world, "m20read"))
    assert client.get(f"{M}/messages", headers=reader).status_code == 403

    # Tenant separation (review 26.09.2026, H8): the second tenant sees none of these
    # messages, neither in the list nor by id.
    other = bearer(login(client, world, "m20adminb"))
    assert {m["id"] for m in _ok(client.get(f"{M}/messages", headers=other))}.isdisjoint(
        {msg["id"], reply["id"]}
    )
    assert client.get(f"{M}/messages/{msg['id']}", headers=other).status_code == 404


def test_list_preview_count_and_literal_search(client: TestClient, world: World) -> None:
    """Review 26.09.2026, M3: the list carries a 200 character preview instead of the full
    text, the detail delivers the text, the count endpoint answers the badge and ``%`` or
    ``_`` in the search term match literally."""
    h = bearer(login(client, world, "m20admin"))
    long_text = "Zeile " * 100
    doc = _upload(
        client, h, "m3.eml", _eml(f"m3{RUN}@example.com", f"Lang {RUN}", long_text, f"<m3-{RUN}@x>")
    )
    msg = _ok(client.post(f"{M}/ingest", json={"document_id": doc}, headers=h), 201)
    assert msg["body"].startswith("Zeile Zeile")
    row = next(m for m in _ok(client.get(f"{M}/messages", headers=h)) if m["id"] == msg["id"])
    assert "body" not in row
    assert "body_html" not in row
    assert row["body_preview"].endswith("…")
    assert len(row["body_preview"]) == 201
    detail = _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))
    assert detail["body"] == msg["body"]
    assert detail["body_preview"] == row["body_preview"]

    count = _ok(client.get(f"{M}/messages/count", params={"direction": "in"}, headers=h))
    listed = _ok(client.get(f"{M}/messages", params={"direction": "in", "limit": 500}, headers=h))
    assert count["count"] == len(listed) >= 1
    assert _ok(client.get(f"{M}/messages/count", params={"status": "sent"}, headers=h)) == {
        "count": 0
    }
    # A bare wildcard matches nothing literally instead of every message.
    assert _ok(client.get(f"{M}/messages", params={"q": "%%%"}, headers=h)) == []
    assert msg["id"] in {
        m["id"] for m in _ok(client.get(f"{M}/messages", params={"q": f"Lang {RUN}"}, headers=h))
    }


def test_reply_found_by_references_header(client: TestClient, world: World) -> None:
    """Review 26.09.2026, M7: a reply whose ``In-Reply-To`` points to a mail the system never
    saw still joins the case through the ``References`` chain."""
    h = bearer(login(client, world, "m20admin"))
    sender = f"m7{RUN}@example.com"
    first = _ok(
        client.post(
            f"{M}/ingest",
            json={
                "document_id": _upload(
                    client, h, "m7a.eml", _eml(sender, f"Balkon {RUN}", "Frage", f"<m7a-{RUN}@x>")
                ),
                "auto_ticket": True,
            },
            headers=h,
        ),
        201,
    )
    assert first["ticket_id"]
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieterin <{sender}>",
        "info@example.com",
        f"AW: Balkon {RUN}",
        f"<m7c-{RUN}@x>",
    )
    msg["In-Reply-To"] = f"<m7b-unknown-{RUN}@x>"  # forwarded via the customer's own client
    msg["References"] = f"<m7a-{RUN}@x> <m7b-unknown-{RUN}@x>"
    msg.set_content("Nachtrag")
    reply = _ok(
        client.post(
            f"{M}/ingest",
            json={"document_id": _upload(client, h, "m7c.eml", bytes(msg)), "auto_ticket": True},
            headers=h,
        ),
        201,
    )
    assert reply["thread_id"] == first["id"]
    assert reply["ticket_id"] == first["ticket_id"]


def test_rejected_and_inline_attachments_are_recorded(client: TestClient, world: World) -> None:
    """Review 26.09.2026, M8: an attachment the upload rules refuse is listed with name, type
    and reason on the message; an inline signature image is not stored as a document."""
    h = bearer(login(client, world, "m20admin"))
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieterin <m8{RUN}@example.com>",
        "info@example.com",
        f"Anhang {RUN}",
        f"<m8-{RUN}@x>",
    )
    msg.set_content("Siehe Anhang.")
    msg.add_alternative('<p>Siehe Anhang <img src="cid:logo1"></p>', subtype="html")
    logo = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    msg.add_attachment(
        logo,
        maintype="image",
        subtype="png",
        filename="logo.png",
        disposition="inline",
        cid="<logo1>",
    )
    msg.add_attachment(
        b"MZ\x90\x00", maintype="application", subtype="x-msdownload", filename="setup.exe"
    )
    msg.add_attachment(b"%PDF-1.4 ok", maintype="application", subtype="pdf", filename="ok.pdf")
    row = _ok(
        client.post(
            f"{M}/ingest",
            json={"document_id": _upload(client, h, "m8.eml", bytes(msg))},
            headers=h,
        ),
        201,
    )
    assert len(row["attachment_document_ids"]) == 1
    rejected = row["classification"]["attachments_rejected"]
    assert [r["filename"] for r in rejected] == ["setup.exe"]
    assert rejected[0]["mime"] == "application/x-msdownload"
    assert rejected[0]["size"] == 4
    assert "nicht zulässig" in rejected[0]["reason"]
    assert row["classification"]["attachments_total"] == 2
    assert row["classification"]["inline_skipped"] == 1


def test_ticket_from_mail_links_contact_and_trims_quotes(client: TestClient, world: World) -> None:
    """Review 26.09.2026, M17: the ticket carries ``contact_id`` (contact page) and a public
    description without quoted mails and signature; the full text stays on the message."""
    h = bearer(login(client, world, "m20admin"))
    sender = f"m17{RUN}@example.com"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "last_name": f"Quote{RUN}", "emails": [{"email": sender}]},
            headers=h,
        ),
        201,
    )
    body = (
        "Guten Tag,\n\nder Aufzug steht seit gestern.\n\nMit freundlichen Grüßen\nErika\n\n"
        "Am 24.09.2026 um 09:00 schrieb Verwaltung <info@example.com>:\n> Ihre Anfrage ist da."
    )
    msg = _ok(
        client.post(
            f"{M}/ingest",
            json={
                "document_id": _upload(
                    client, h, "m17.eml", _eml(sender, f"Aufzug {RUN}", body, f"<m17-{RUN}@x>")
                ),
                "auto_ticket": True,
            },
            headers=h,
        ),
        201,
    )
    ticket = _ok(client.get(f"/api/v1/tickets/{msg['ticket_id']}", headers=h))
    assert ticket["contact_id"] == contact["id"]
    assert ticket["initiator_contact_id"] == contact["id"]
    assert ticket["public_description"] == "Guten Tag,\n\nder Aufzug steht seit gestern."
    assert "> Ihre Anfrage" in _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))["body"]
