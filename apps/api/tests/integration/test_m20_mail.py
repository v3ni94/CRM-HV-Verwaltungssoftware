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
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m20admin", "tenant_admin"), ("m20read", "read_only_master_data")]:
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
    blocked = client.post(f"{M}/messages/{draft['id']}/send", headers=h)
    assert blocked.status_code == 409  # mailbox not enabled
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
