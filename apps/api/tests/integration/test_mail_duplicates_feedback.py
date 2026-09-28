"""Operator feedback 28.09.2026: "teilweise Mehrfachauflistung der gleichen E-Mail" in the mail
workspace although copies across own mailboxes are linked since 1.36.0. One test per examined
cause; expected values are fixed here (one row per mail, stored copies are kept as evidence).

Causes found and fixed:
- the thread view, the ticket mail history, the ticket message count and the contact history
  listed every linked copy (copies share thread, ticket and contact);
- the delivered copy of an own sent mail (reply with cc to an own mailbox) was stored as a new
  inbound mail next to the sent one (the duplicate check compared inbound rows only);
- a mail without ``Message-ID`` and ``Date`` fetched twice from Gmail (sync, push, retry or
  backfill overlap) was stored twice, the content key needs a timestamp.

Examined and not a duplicate: two personal mailboxes (neither collective) already link; a
reply in the thread is a mail of its own; a forwarded mail has its own ``Message-ID`` and
content; the list query has no joins that could multiply rows."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services as platform_services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail import _ok
from tests.integration.test_mail_progress_duplicates import _eml, _ingest, _mailbox

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
T = "/api/v1/tickets"
DATE = "Mon, 28 Sep 2026 09:00:00 +0200"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await platform_services.provision_tenant(
            factory, slug=f"mdf-{RUN}", name=f"Mail Mehrfach {RUN}"
        )
        b, _ = await platform_services.provision_tenant(
            factory, slug=f"mdfb-{RUN}", name=f"Mail Mehrfach B {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("mdfadmin", "tenant_admin", a),
            ("mdfstd", "standard", a),
            ("mdfadminb", "tenant_admin", b),
        ]:
            uid = await platform_services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await platform_services.add_member(
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


def _list(client: TestClient, h: dict[str, str], q: str, **extra: Any) -> list[str]:
    res = client.get(f"{M}/messages", params={"q": q, **extra}, headers=h)
    rows = _ok(res)
    ids = [m["id"] for m in rows]
    assert len(ids) == len(set(ids)), "list rows must be unique"
    assert res.headers["x-total-count"] == str(len(ids))
    return ids


def _run(database: Database, redis_url: str, tenant: Any, work: Any) -> Any:
    """Runs ``work(session, settings, blobs)`` in a tenant transaction like a worker."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore

    settings = _settings(database, redis_url)

    async def run() -> Any:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, tenant) as session:
                return await work(session, settings, BlobStore(settings))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _gmail_ingest(
    database: Database, redis_url: str, tenant: Any, raw: bytes, mailbox: str, gmail_id: str
) -> tuple[str, bool]:
    from mhvp.communication.services import ingest_raw

    async def work(session: Any, settings: Any, blobs: Any) -> tuple[str, bool]:
        row, created = await ingest_raw(
            session,
            blobs,
            settings,
            tenant_id=tenant,
            actor_user_id=None,
            raw=raw,
            mailbox_id=uuid.UUID(mailbox),
            auto_ticket=True,
            gmail_message_id=gmail_id,
            gmail_thread_id=f"t-{gmail_id}",
        )
        return str(row.id), created

    result: tuple[str, bool] = _run(database, redis_url, tenant, work)
    return result


def _count(database: Database, tenant: Any, where: str, **params: Any) -> int:
    engine = sa.create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)}
            )
            return int(
                conn.execute(
                    sa.text(f"SELECT count(*) FROM message WHERE tenant_id = :t AND {where}"),
                    {"t": str(tenant), **params},
                ).scalar_one()
            )
    finally:
        engine.dispose()


def test_copies_in_two_personal_mailboxes_are_listed_once_everywhere(
    client: TestClient, world: World, database: Database
) -> None:
    """Neither mailbox is collective: the earlier copy leads, the later one is linked. List,
    count, thread view, ticket history, ticket count and contact history show the mail once;
    both rows stay stored."""
    admin = bearer(login(client, world, "mdfadmin"))
    std = bearer(login(client, world, "mdfstd"))
    brink = _mailbox(client, admin, f"brink-{RUN}@example.com")
    weber = _mailbox(client, admin, f"weber-{RUN}@example.com")
    assert brink["is_collective"] is False
    assert weber["is_collective"] is False
    for box in (brink, weber):
        _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"is_default": True}, headers=admin))
    sender = f"zwei{RUN}@example.com"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Eva",
                "last_name": f"Zwei{RUN}",
                "emails": [{"email": sender}],
            },
            headers=admin,
        ),
        201,
    )
    subject = f"Zwei persoenlich {RUN}"
    raw = _eml(sender, subject, "Heizung defekt", f"<zwei-{RUN}@x>", DATE, "brink, weber")
    first = _ingest(client, admin, raw, mailbox_id=brink["id"], auto_ticket=True)
    second = _ingest(client, admin, raw, mailbox_id=weber["id"], auto_ticket=True)
    assert second["id"] != first["id"]
    assert second["duplicate_of_id"] == first["id"]
    assert second["ticket_id"] == first["ticket_id"]
    assert first["contact_id"] == contact["id"]

    assert _list(client, admin, subject) == [first["id"]]
    assert _list(client, std, subject) == [first["id"]]
    assert _ok(client.get(f"{M}/messages/count", params={"q": subject}, headers=admin)) == {
        "count": 1
    }
    for mid in (first["id"], second["id"]):
        thread = _ok(client.get(f"{M}/messages/{mid}/thread", headers=admin))
        assert [m["id"] for m in thread] == [first["id"]]
    history = _ok(client.get(f"{T}/{first['ticket_id']}/messages", headers=admin))
    assert [m["id"] for m in history] == [first["id"]]
    ticket = _ok(client.get(f"{T}/{first['ticket_id']}", headers=admin))
    assert ticket["message_count"] == 1
    events = _ok(client.get(f"/api/v1/contacts/{contact['id']}/history", headers=admin))
    assert [e for e in events if e["kind"] == "email_in" and e["title"] == subject]
    assert len([e for e in events if e["kind"] == "email_in" and e["title"] == subject]) == 1
    # Evidence: both copies stay stored.
    assert _count(database, world.tenant_a, "header_message_id = :m", m=f"<zwei-{RUN}@x>") == 2
    # Tenant separation: the other tenant sees nothing of it.
    other = bearer(login(client, world, "mdfadminb"))
    assert _list(client, other, subject) == []


def test_reply_in_thread_is_a_mail_of_its_own_and_listed_once(
    client: TestClient, world: World
) -> None:
    """A reply of the sender in the same thread is a second mail: the list shows both mails
    once each, the thread shows both, nothing is repeated."""
    admin = bearer(login(client, world, "mdfadmin"))
    box = _mailbox(client, admin, f"thread-{RUN}@example.com")
    sender = f"faden{RUN}@example.com"
    subject = f"Faden {RUN}"
    first = _ingest(
        client,
        admin,
        _eml(sender, subject, "Erste Mail", f"<f1-{RUN}@x>", DATE, "thread"),
        mailbox_id=box["id"],
        auto_ticket=True,
    )
    reply_raw = _eml(
        sender,
        f"Re: {subject}",
        "Nachtrag",
        f"<f2-{RUN}@x>",
        "Mon, 28 Sep 2026 10:00:00 +0200",
        "thread",
    ).replace(b"Message-ID:", f"In-Reply-To: <f1-{RUN}@x>\nMessage-ID:".encode(), 1)
    reply = _ingest(client, admin, reply_raw, mailbox_id=box["id"], auto_ticket=True)
    assert reply["thread_id"] == first["id"]
    assert reply["ticket_id"] == first["ticket_id"]
    assert set(_list(client, admin, subject)) == {first["id"], reply["id"]}
    thread = _ok(client.get(f"{M}/messages/{reply['id']}/thread", headers=admin))
    assert [m["id"] for m in thread] == [first["id"], reply["id"]]


def test_forwarded_mail_is_a_mail_of_its_own(client: TestClient, world: World) -> None:
    """A forward (new Message-ID, "WG:" subject, quoted text) is another mail and stays listed
    on its own; nothing is linked or hidden."""
    admin = bearer(login(client, world, "mdfadmin"))
    box = _mailbox(client, admin, f"fwd-{RUN}@example.com")
    subject = f"Weiterleitung {RUN}"
    original = _ingest(
        client,
        admin,
        _eml(f"orig{RUN}@example.com", subject, "Original", f"<o-{RUN}@x>", DATE, "fwd"),
        mailbox_id=box["id"],
    )
    forwarded = _ingest(
        client,
        admin,
        _eml(
            f"kollege{RUN}@example.com",
            f"WG: {subject}",
            "---------- Weitergeleitete Nachricht ----------\nOriginal",
            f"<w-{RUN}@x>",
            "Mon, 28 Sep 2026 11:00:00 +0200",
            "fwd",
        ),
        mailbox_id=box["id"],
    )
    assert forwarded["duplicate_of_id"] is None
    assert set(_list(client, admin, subject)) == {original["id"], forwarded["id"]}


def test_same_gmail_message_without_message_id_and_date_is_stored_once(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Gmail sync and push (or the retry queue) fetch the same Gmail message twice. Without
    Message-ID and Date the content key had no timestamp, so the mail was stored twice; the
    Gmail id of the mailbox now returns the stored row."""
    admin = bearer(login(client, world, "mdfadmin"))
    box = _mailbox(client, admin, f"gmailid-{RUN}@example.com")
    subject = f"Ohne Kennung {RUN}"
    raw = _eml(f"ohne{RUN}@example.com", subject, "Kein Datum", None, DATE, "gmailid")
    raw = raw.replace(f"Date: {DATE}\n".encode(), b"", 1)
    assert b"Date:" not in raw
    assert b"Message-ID" not in raw
    first_id, created = _gmail_ingest(database, redis_url, world.tenant_a, raw, box["id"], "g1")
    assert created is True
    again_id, created_again = _gmail_ingest(
        database, redis_url, world.tenant_a, raw, box["id"], "g1"
    )
    assert again_id == first_id
    assert created_again is False
    assert _list(client, admin, subject) == [first_id]
    assert _count(database, world.tenant_a, "subject = :s", s=subject) == 1
    # A different Gmail message with the same text is still a mail of its own.
    other_id, other_created = _gmail_ingest(
        database, redis_url, world.tenant_a, raw, box["id"], "g2"
    )
    assert other_created is True
    assert other_id != first_id


def test_delivered_copy_of_own_sent_mail_is_linked_to_the_sent_mail(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """A reply sent from brink@ with cc to info@ comes back through the sync of info@ with the
    same Message-ID. It was listed as a new inbound mail next to the sent one (and could open
    a ticket); now it is stored as a linked, done copy of the sent mail and hidden."""
    from mhvp.communication.models import Message

    admin = bearer(login(client, world, "mdfadmin"))
    info = _mailbox(client, admin, f"info-{RUN}@example.com")
    brink = _mailbox(client, admin, f"brinkout-{RUN}@example.com")
    subject = f"Antwort Eigentuemer {RUN}"
    msg_id = f"<sent-{RUN}@example.com>"

    async def sent_row(session: Any, settings: Any, blobs: Any) -> str:
        row = Message(
            tenant_id=world.tenant_a,
            direction="out",
            mailbox_id=uuid.UUID(brink["id"]),
            from_address=brink["address"],
            to_addresses=[f"kunde{RUN}@example.com"],
            cc_addresses=[info["address"]],
            subject=subject,
            body="Vielen Dank",
            header_message_id=msg_id,
            status="sent",
            sent_at=datetime.now(UTC),
        )
        session.add(row)
        await session.flush()
        return str(row.id)

    sent_id = _run(database, redis_url, world.tenant_a, sent_row)
    raw = _eml(brink["address"], subject, "Vielen Dank", msg_id, DATE, f"kunde{RUN}@example.com")
    raw = raw.replace(b"From: Mieter <", b"From: Brink <", 1)
    echo_id, created = _gmail_ingest(database, redis_url, world.tenant_a, raw, info["id"], "e1")
    assert created is True
    echo = _ok(client.get(f"{M}/messages/{echo_id}", headers=admin))
    assert echo["duplicate_of_id"] == sent_id
    assert echo["status"] == "done"
    assert echo["ticket_id"] is None
    assert echo["direction"] == "in"
    listed = _list(client, admin, subject, include_closed=True)
    assert listed == [sent_id]
    # A foreign sender with the same Message-ID is no echo of the own mail.
    spoof = _eml(f"fremd{RUN}@example.com", subject, "Anders", msg_id, DATE, "info")
    spoof_id, _ = _gmail_ingest(database, redis_url, world.tenant_a, spoof, brink["id"], "s1")
    assert _ok(client.get(f"{M}/messages/{spoof_id}", headers=admin))["duplicate_of_id"] is None
