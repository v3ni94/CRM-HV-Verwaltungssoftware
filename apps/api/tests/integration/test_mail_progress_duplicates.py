"""Operator 27.09.2026 (mail workspace): newest mail first in every list view, the
"in Bearbeitung" marker with the handler's name, and duplicates of one mail across own
mailboxes (personal mailbox leads, collective copy linked, one ticket for both, maintenance
endpoint for existing rows)."""

from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.communication.duplicates import is_collective_address
from mhvp.main import create_app
from mhvp.platform import services as platform_services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail import _ok, _upload

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await platform_services.provision_tenant(
            factory, slug=f"mpd-{RUN}", name=f"Mail Dup {RUN}"
        )
        b, _ = await platform_services.provision_tenant(
            factory, slug=f"mpdb-{RUN}", name=f"Mail Dup B {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("mpdadmin", "tenant_admin", a),
            ("mpdstd", "standard", a),
            ("mpdadminb", "tenant_admin", b),
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
    import asyncio

    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _eml(sender: str, subject: str, body: str, msg_id: str | None, date: str, to: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = (f"Mieter <{sender}>", to, subject)
    if msg_id:
        msg["Message-ID"] = msg_id
    msg["Date"] = date
    msg.set_content(body)
    return bytes(msg)


def _ingest(client: TestClient, h: dict[str, str], raw: bytes, **extra: Any) -> dict[str, Any]:
    doc = _upload(client, h, "mail.eml", raw)
    out: dict[str, Any] = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, **extra}, headers=h), 201
    )
    return out


def _mailbox(client: TestClient, h: dict[str, str], address: str) -> dict[str, Any]:
    out: dict[str, Any] = _ok(
        client.post(f"{M}/mailboxes", json={"address": address, "kind": "imap"}, headers=h), 201
    )
    return out


def test_collective_address_rule() -> None:
    assert is_collective_address("info@muellerhv.de")
    assert is_collective_address("Buchhaltung@muellerhv.de")
    assert is_collective_address("post-eingang@muellerhv.de")
    assert not is_collective_address("brink@muellerhv.de")
    assert not is_collective_address("t.mueller@muellerhv.de")
    assert not is_collective_address(None)


def test_list_sorts_newest_first(client: TestClient, world: World) -> None:
    """Posteingang, Filter und Suche: neueste oben (received_at absteigend), Paginierung
    behält diese Reihenfolge über Seiten hinweg."""
    h = bearer(login(client, world, "mpdadmin"))
    sender = f"sort{RUN}@example.com"
    dates = [
        "Mon, 21 Sep 2026 09:00:00 +0200",
        "Wed, 23 Sep 2026 11:30:00 +0200",
        "Tue, 22 Sep 2026 08:15:00 +0200",
    ]
    ids = [
        _ingest(
            client,
            h,
            _eml(sender, f"Sortierung {RUN} {i}", "Text", f"<s{i}-{RUN}@x>", d, "info@example.com"),
        )["id"]
        for i, d in enumerate(dates)
    ]
    rows = _ok(client.get(f"{M}/messages", params={"q": f"Sortierung {RUN}"}, headers=h))
    assert [m["id"] for m in rows] == [ids[1], ids[2], ids[0]]
    received = [m["received_at"] for m in rows]
    assert received == sorted(received, reverse=True)
    page1 = _ok(
        client.get(
            f"{M}/messages", params={"q": f"Sortierung {RUN}", "page": 1, "page_size": 2}, headers=h
        )
    )
    page2 = _ok(
        client.get(
            f"{M}/messages", params={"q": f"Sortierung {RUN}", "page": 2, "page_size": 2}, headers=h
        )
    )
    assert [m["id"] for m in page1] + [m["id"] for m in page2] == [ids[1], ids[2], ids[0]]
    by_contact = _ok(
        client.get(f"{M}/messages", params={"direction": "in", "q": f"Sortierung {RUN}"}, headers=h)
    )
    assert [m["id"] for m in by_contact] == [ids[1], ids[2], ids[0]]


def test_in_progress_marker_and_handler(client: TestClient, world: World) -> None:
    """In Bearbeitung ab Kommentar, Zuweisung oder eingereichter Antwort; Bearbeiter ist der
    zugewiesene Nutzer, sonst der Nutzer des letzten Kommentars oder der letzten Antwort."""
    admin = bearer(login(client, world, "mpdadmin"))
    std = bearer(login(client, world, "mpdstd"))
    sender = f"prog{RUN}@example.com"
    msg = _ingest(
        client,
        admin,
        _eml(
            sender,
            f"Bearbeitung {RUN}",
            "Frage",
            f"<prog-{RUN}@x>",
            "Wed, 23 Sep 2026 09:00:00 +0200",
            "info@example.com",
        ),
        auto_ticket=True,
    )
    assert msg["ticket_id"]
    assert msg["in_progress"] is False
    assert msg["handler_display_name"] is None

    def row() -> dict[str, Any]:
        rows = _ok(client.get(f"{M}/messages", params={"q": f"Bearbeitung {RUN}"}, headers=admin))
        return next(m for m in rows if m["id"] == msg["id"])

    assert row()["in_progress"] is False
    # Interner Kommentar durch m20std: in Bearbeitung von m20std.
    _ok(
        client.post(
            f"{T}/{msg['ticket_id']}/comments", json={"body": "Rückruf erledigt"}, headers=std
        ),
        201,
    )
    r = row()
    assert r["in_progress"] is True
    assert r["handler_display_name"] == "mpdstd"
    assert r["handler_user_id"] == str(world.users["mpdstd"])
    # Zuweisung schlägt den Kommentar.
    _ok(
        client.patch(
            f"{T}/{msg['ticket_id']}",
            json={"assignee_user_id": str(world.users["mpdadmin"])},
            headers=admin,
        )
    )
    r = row()
    assert r["in_progress"] is True
    assert r["handler_display_name"] == "mpdadmin"
    detail = _ok(client.get(f"{M}/messages/{msg['id']}", headers=admin))
    assert detail["in_progress"] is True
    assert detail["handler_display_name"] == "mpdadmin"

    # Antwort: unveröffentlichter Entwurf zählt nicht, eingereichter Entwurf schon.
    second = _ingest(
        client,
        admin,
        _eml(
            sender,
            f"Antwortlage {RUN}",
            "Frage",
            f"<prog2-{RUN}@x>",
            "Wed, 23 Sep 2026 10:00:00 +0200",
            "info@example.com",
        ),
        auto_ticket=True,
    )
    draft = _ok(client.post(f"{M}/messages/{second['id']}/reply-draft", headers=std), 201)

    def second_row() -> dict[str, Any]:
        rows = _ok(client.get(f"{M}/messages", params={"q": f"Antwortlage {RUN}"}, headers=admin))
        return next(m for m in rows if m["id"] == second["id"])

    assert second_row()["in_progress"] is False
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=std))
    r = second_row()
    assert r["in_progress"] is True
    assert r["handler_display_name"] == "mpdstd"
    # Ausgehende Nachrichten tragen keine Kennzeichnung.
    outgoing = next(
        m
        for m in _ok(
            client.get(
                f"{M}/messages", params={"direction": "out", "status": "pending"}, headers=admin
            )
        )
        if m["id"] == draft["id"]
    )
    assert outgoing["in_progress"] is False


def test_duplicate_across_mailboxes_leads_in_personal_mailbox(
    client: TestClient, world: World, database: Database
) -> None:
    """Dieselbe Mail an info@ (Sammelpostfach) und brink@ (persönlich): einmal in der
    Übersicht, beim persönlichen Postfach; Kopie im Sammelpostfach verknüpft, nicht gelöscht;
    beide im selben Ticket; Kennzeichnung gilt für beide Kopien."""
    admin = bearer(login(client, world, "mpdadmin"))
    std = bearer(login(client, world, "mpdstd"))
    info = _mailbox(client, admin, f"info-{RUN}@example.com")
    brink = _mailbox(client, admin, f"brink-{RUN}@example.com")
    assert info["is_collective"] is True
    assert brink["is_collective"] is False
    _ok(client.patch(f"{M}/mailboxes/{info['id']}", json={"is_default": True}, headers=admin))
    sender = f"dup{RUN}@example.com"
    raw = _eml(
        sender,
        f"Doppelt {RUN}",
        "Gleicher Text",
        f"<dup-{RUN}@x>",
        "Thu, 24 Sep 2026 09:00:00 +0200",
        "info@example.com, brink@example.com",
    )
    first = _ingest(client, admin, raw, mailbox_id=info["id"], auto_ticket=True)
    assert first["ticket_id"]
    assert first["duplicate_of_id"] is None
    # Erneuter Abruf desselben Postfachs: keine zweite Zeile.
    again = _ingest(client, admin, raw, mailbox_id=info["id"])
    assert again["id"] == first["id"]
    # Kopie im persönlichen Postfach führt, die Kopie im Sammelpostfach wird Duplikat.
    second = _ingest(client, admin, raw, mailbox_id=brink["id"])
    assert second["id"] != first["id"]
    assert second["duplicate_of_id"] is None
    assert second["ticket_id"] == first["ticket_id"]
    assert second["thread_id"] == first["id"]
    first_now = _ok(client.get(f"{M}/messages/{first['id']}", headers=admin))
    assert first_now["duplicate_of_id"] == second["id"]
    assert first_now["ticket_id"] == first["ticket_id"]

    rows = _ok(client.get(f"{M}/messages", params={"q": f"Doppelt {RUN}"}, headers=admin))
    assert [m["id"] for m in rows] == [second["id"]]
    total = client.get(f"{M}/messages", params={"q": f"Doppelt {RUN}"}, headers=admin)
    assert total.headers["x-total-count"] == "1"
    assert _ok(
        client.get(f"{M}/messages/count", params={"q": f"Doppelt {RUN}"}, headers=admin)
    ) == {"count": 1}
    both = _ok(
        client.get(
            f"{M}/messages",
            params={"q": f"Doppelt {RUN}", "include_duplicates": True},
            headers=admin,
        )
    )
    assert {m["id"] for m in both} == {first["id"], second["id"]}
    in_info = _ok(
        client.get(
            f"{M}/messages", params={"mailbox_id": info["id"], "q": f"Doppelt {RUN}"}, headers=admin
        )
    )
    assert [m["id"] for m in in_info] == [first["id"]]
    # Ein Mitglied ohne Zugriff auf brink@ sieht weiter die Kopie des Sammelpostfachs.
    for_std = _ok(client.get(f"{M}/messages", params={"q": f"Doppelt {RUN}"}, headers=std))
    assert [m["id"] for m in for_std] == [first["id"]]
    # Der Vorgang zeigt beide Kopien im selben Thread.
    thread = _ok(client.get(f"{M}/messages/{second['id']}/thread", headers=admin))
    assert {m["id"] for m in thread} >= {first["id"], second["id"]}

    # Bearbeitung an einer Kopie kennzeichnet beide.
    _ok(
        client.post(
            f"{T}/{first['ticket_id']}/comments", json={"body": "Ich übernehme"}, headers=std
        ),
        201,
    )
    for mid, headers in ((second["id"], admin), (first["id"], std)):
        detail = _ok(client.get(f"{M}/messages/{mid}", headers=headers))
        assert detail["in_progress"] is True
        assert detail["handler_display_name"] == "mpdstd"

    # Ohne Message-ID (Relay ohne Kopfzeile): gleicher Absender, Betreff, Zeitstempel und
    # Text-Hash. Eine abweichende Message-ID bleibt dagegen eine eigene Mail (Anrufnotizen).
    raw_b = _eml(
        sender,
        f"Doppelt {RUN}",
        "Gleicher Text",
        None,
        "Thu, 24 Sep 2026 09:00:00 +0200",
        "info@example.com, brink@example.com",
    )
    third = _ingest(client, admin, raw_b, mailbox_id=info["id"])
    assert third["id"] == first["id"]  # Sammelpostfach hat diese Mail bereits

    # Wartung: rückwirkende Verknüpfung vorhandener Kopien (hier künstlich gelöst).
    engine = sa.create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(world.tenant_a)},
        )
        conn.execute(
            sa.text("UPDATE message SET duplicate_of_id = NULL, ticket_id = NULL WHERE id = :id"),
            {"id": first["id"]},
        )
    engine.dispose()
    assert len(_ok(client.get(f"{M}/messages", params={"q": f"Doppelt {RUN}"}, headers=admin))) == 2
    counts = _ok(client.post(f"{M}/maintenance/link-duplicates", headers=admin))
    assert counts["linked"] >= 1
    assert counts["ticket_conflicts"] == 0
    relinked = _ok(client.get(f"{M}/messages/{first['id']}", headers=admin))
    assert relinked["duplicate_of_id"] == second["id"]
    assert relinked["ticket_id"] == second["ticket_id"]
    assert len(_ok(client.get(f"{M}/messages", params={"q": f"Doppelt {RUN}"}, headers=admin))) == 1
    # Idempotent.
    assert _ok(client.post(f"{M}/maintenance/link-duplicates", headers=admin))["linked"] == 0


# Review 1.36.0 -----------------------------------------------------------------------------


def _invoice_eml(
    sender: str, subject: str, msg_id: str, to: str, body: str = "Anbei die Rechnung."
) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = (f"Lieferant <{sender}>", to, subject)
    msg["Message-ID"] = msg_id
    msg["Date"] = "Fri, 25 Sep 2026 08:00:00 +0200"
    msg.set_content(body)
    msg.add_attachment(
        b"%PDF-1.4 rechnung", maintype="application", subtype="pdf", filename="rechnung.pdf"
    )
    return bytes(msg)


def _enable_forwarding(client: TestClient, h: dict[str, str], sender: str) -> None:
    _ok(
        client.put(
            f"{M}/invoice-forwarding",
            json={
                "enabled": True,
                "forward_address": "buchhaltung@inbox.example.com",
                "sender_allowlist": [sender],
            },
            headers=h,
        )
    )


def _ingest_direct(
    database: Database,
    redis_url: str,
    tenant: Any,
    raw: bytes,
    mailboxes: list[str],
    *,
    parallel: bool = False,
) -> None:
    """Ingests ``raw`` like the Gmail sync, one transaction per mailbox. ``parallel``: the
    second ingest starts while the first transaction is still open (two syncs of own
    mailboxes running at the same time) and the first commits one second later."""
    import asyncio
    import uuid

    from mhvp.communication.services import ingest_raw
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore

    settings = _settings(database, redis_url)

    async def run() -> None:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        blobs = BlobStore(settings)
        stored = asyncio.Event()
        release = asyncio.Event()

        async def one(mailbox_id: str, *, hold: bool) -> None:
            async with tenant_transaction(factory, tenant) as session:
                await ingest_raw(
                    session,
                    blobs,
                    settings,
                    tenant_id=tenant,
                    actor_user_id=None,
                    raw=raw,
                    mailbox_id=uuid.UUID(mailbox_id),
                    auto_ticket=True,
                )
                if hold:
                    stored.set()
                    await release.wait()

        try:
            if not parallel:
                for mailbox_id in mailboxes:
                    await one(mailbox_id, hold=False)
                return
            first = asyncio.create_task(one(mailboxes[0], hold=True))
            waiter = asyncio.create_task(stored.wait())
            done, _ = await asyncio.wait({first, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if first in done:
                waiter.cancel()
                first.result()  # surfaces the error of the first ingest
            second = asyncio.create_task(one(mailboxes[1], hold=False))
            await asyncio.sleep(1.0)
            release.set()
            await asyncio.gather(first, second)
        finally:
            await engine.dispose()

    asyncio.run(run())


def _rows(database: Database, tenant: Any, msg_id: str) -> list[Any]:
    engine = sa.create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant)},
            )
            return list(
                conn.execute(
                    sa.text(
                        "SELECT id, mailbox_id, duplicate_of_id, ticket_id, subject, body, "
                        "classification -> 'invoice_forward' ->> 'status' AS forward, "
                        "classification -> 'invoice_forward' ->> 'of' AS forward_of "
                        "FROM message WHERE header_message_id = :m AND direction = 'in' "
                        "ORDER BY created_at"
                    ),
                    {"m": msg_id},
                ).all()
            )
    finally:
        engine.dispose()


def test_parallel_syncs_of_two_mailboxes_store_one_leading_copy(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Befund 2: zwei gleichzeitige Abrufe von info@ und brink@ derselben Mail ergeben eine
    führende Zeile und eine verknüpfte Kopie, ein Ticket und höchstens eine vorgemerkte
    Rechnungsweiterleitung (Sperre je Mandant und Mailschlüssel)."""
    admin = bearer(login(client, world, "mpdadminb"))
    sender = f"par{RUN}@lieferant.example.com"
    _enable_forwarding(client, admin, sender)
    info = _mailbox(client, admin, f"info-par-{RUN}@example.com")
    brink = _mailbox(client, admin, f"brink-par-{RUN}@example.com")
    # An earlier ticket of the tenant: the ticket number sequence exists before the race.
    warm_up = _eml(sender, f"Vorlauf {RUN}", "Text", f"<pre-{RUN}@x>", "Fri, 25 Sep 2026", "x@x")
    assert _ingest(client, admin, warm_up, auto_ticket=True)["ticket_id"]
    msg_id = f"<par-{RUN}@x>"
    raw = _invoice_eml(sender, f"Rechnung {RUN} parallel", msg_id, "info@x, brink@x")
    _ingest_direct(
        database, redis_url, world.tenant_b, raw, [info["id"], brink["id"]], parallel=True
    )
    rows = _rows(database, world.tenant_b, msg_id)
    assert len(rows) == 2
    assert [r.duplicate_of_id for r in rows].count(None) == 1
    leading = next(r for r in rows if r.duplicate_of_id is None)
    assert str(leading.mailbox_id) == brink["id"]  # personal mailbox leads
    assert len({r.ticket_id for r in rows}) == 1
    assert rows[0].ticket_id is not None
    assert [r.forward for r in rows].count("queued") <= 1


def test_duplicate_copy_never_forwards_the_invoice_again(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Befund 3: die Kopie einer vorgemerkten Rechnung übernimmt den Status "queued" nicht;
    die Weiterleitung geht genau einmal hinaus, auch wenn die Kopie danach führt."""
    import asyncio

    from mhvp.communication import forwarding_dispatch
    from mhvp.communication.services import forward_queued
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    admin = bearer(login(client, world, "mpdadminb"))
    sender = f"fwd{RUN}@lieferant.example.com"
    _enable_forwarding(client, admin, sender)
    rechnung = _mailbox(client, admin, f"rechnung-fwd-{RUN}@example.com")
    brink = _mailbox(client, admin, f"brink-fwd-{RUN}@example.com")
    msg_id = f"<fwd-{RUN}@x>"
    raw = _invoice_eml(sender, f"Rechnung {RUN} Kopie", msg_id, "rechnung@x, brink@x")
    _ingest_direct(database, redis_url, world.tenant_b, raw, [rechnung["id"]])
    _ingest_direct(database, redis_url, world.tenant_b, raw, [brink["id"]])
    original, copy = _rows(database, world.tenant_b, msg_id)
    assert original.forward == "queued"
    assert copy.forward == "duplicate"
    assert copy.duplicate_of_id is None
    assert original.duplicate_of_id == copy.id

    sent: list[Any] = []

    async def fake_forward(session: Any, settings: Any, tenant_id: Any, *args: Any) -> bool:
        sent.append(args[1].id)
        return True

    monkeypatch.setattr(forwarding_dispatch, "forward_and_archive", fake_forward)
    settings = _settings(database, redis_url)

    async def run() -> None:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_b) as session:
                await forward_queued(session, settings, world.tenant_b)
        finally:
            await engine.dispose()

    asyncio.run(run())
    assert [mid for mid in sent if mid in {original.id, copy.id}] == [original.id]
    assert [r.forward for r in _rows(database, world.tenant_b, msg_id)] == ["sent", "duplicate"]


def test_message_id_collision_with_other_content_is_a_mail_of_its_own(
    client: TestClient, world: World, database: Database
) -> None:
    """Befund 21: gleiche Message-ID, aber anderer Inhalt (Betreff, Text oder Anhang) in einem
    anderen Postfach ist eine eigene Mail. Sie wird mit ihrem eigenen Inhalt gespeichert, nie
    als Kopie der gespeicherten Mail (kein Inhalt eines persönlichen Postfachs im
    Sammelpostfach)."""
    admin = bearer(login(client, world, "mpdadminb"))
    brink = _mailbox(client, admin, f"brink-col-{RUN}@example.com")
    info = _mailbox(client, admin, f"info-col-{RUN}@example.com")
    post = _mailbox(client, admin, f"post-col-{RUN}@example.com")
    msg_id = f"<col-{RUN}@x>"
    date = "Sat, 26 Sep 2026 10:00:00 +0200"
    sender = f"col{RUN}@example.com"
    secret = _eml(sender, f"Vertraulich {RUN}", "Persönlicher Inhalt", msg_id, date, "brink@x")
    first = _ingest(client, admin, secret, mailbox_id=brink["id"])
    other = _eml(sender, f"Anfrage {RUN}", "Anderer Inhalt", msg_id, date, "info@x")
    second = _ingest(client, admin, other, mailbox_id=info["id"])
    assert second["id"] != first["id"]
    assert second["duplicate_of_id"] is None
    assert (second["subject"], second["body"]) == (f"Anfrage {RUN}", "Anderer Inhalt")
    # Erneuter Abruf des Sammelpostfachs: dieselbe Zeile, keine zweite.
    assert _ingest(client, admin, other, mailbox_id=info["id"])["id"] == second["id"]
    # Gleicher Betreff und Text, aber ein anderer Anhang: ebenfalls eine eigene Mail.
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = (f"Mieter <{sender}>", "post@x", f"Vertraulich {RUN}")
    msg["Message-ID"], msg["Date"] = msg_id, date
    msg.set_content("Persönlicher Inhalt")
    msg.add_attachment(b"%PDF-1.4 anders", maintype="application", subtype="pdf", filename="a.pdf")
    third = _ingest(client, admin, bytes(msg), mailbox_id=post["id"])
    assert third["id"] not in {first["id"], second["id"]}
    assert third["duplicate_of_id"] is None
    rows = _rows(database, world.tenant_b, msg_id)
    assert [r.duplicate_of_id for r in rows] == [None, None, None]
    assert [r.body for r in rows] == [
        "Persönlicher Inhalt",
        "Anderer Inhalt",
        "Persönlicher Inhalt",
    ]
    # Die Wartung verknüpft Zeilen mit verschiedenem Inhalt ebenfalls nicht.
    _ok(client.post(f"{M}/maintenance/link-duplicates", headers=admin))
    assert [r.duplicate_of_id for r in _rows(database, world.tenant_b, msg_id)] == [None] * 3


def test_maintenance_keeps_copies_with_another_ticket_visible(
    client: TestClient, world: World, database: Database
) -> None:
    """Befund 20: Kopien derselben Mail mit verschiedenen Tickets verknüpft die Wartung nicht;
    sie werden als ticket_conflicts gezählt und bleiben beide in der Übersicht."""
    admin = bearer(login(client, world, "mpdadminb"))
    info = _mailbox(client, admin, f"info-tc-{RUN}@example.com")
    brink = _mailbox(client, admin, f"brink-tc-{RUN}@example.com")
    sender = f"tc{RUN}@example.com"
    date = "Sun, 27 Sep 2026 09:00:00 +0200"
    raw = _eml(sender, f"Konflikt {RUN}", "Gleicher Text", f"<tc-{RUN}@x>", date, "info@x")
    first = _ingest(client, admin, raw, mailbox_id=info["id"], auto_ticket=True)
    second = _ingest(client, admin, raw, mailbox_id=brink["id"])
    other_case = _ingest(
        client,
        admin,
        _eml(sender, f"Anderer Fall {RUN}", "Text", f"<tc2-{RUN}@x>", date, "info@x"),
        auto_ticket=True,
    )
    assert other_case["ticket_id"]
    assert other_case["ticket_id"] != first["ticket_id"]
    # Altbestand vor 1.36: beide Kopien ungekoppelt, jede mit eigenem Ticket.
    engine = sa.create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(world.tenant_b)},
        )
        conn.execute(
            sa.text("UPDATE message SET duplicate_of_id = NULL WHERE id IN (:a, :b)"),
            {"a": first["id"], "b": second["id"]},
        )
        conn.execute(
            sa.text("UPDATE message SET ticket_id = :t WHERE id = :id"),
            {"t": other_case["ticket_id"], "id": second["id"]},
        )
    engine.dispose()
    counts = _ok(client.post(f"{M}/maintenance/link-duplicates", headers=admin))
    # The counters cover the whole tenant (rows of other tests too); the two rows decide.
    assert counts["ticket_conflicts"] >= 1
    for mid, ticket in ((first["id"], first["ticket_id"]), (second["id"], other_case["ticket_id"])):
        detail = _ok(client.get(f"{M}/messages/{mid}", headers=admin))
        assert detail["duplicate_of_id"] is None
        assert detail["ticket_id"] == ticket
    visible = _ok(client.get(f"{M}/messages", params={"q": f"Konflikt {RUN}"}, headers=admin))
    assert {m["id"] for m in visible} == {first["id"], second["id"]}


def _run_forward_queue(database: Database, redis_url: str, tenant: Any) -> None:
    """Runs ``forward_queued`` once in a transaction of its own, like the follow up job."""
    import asyncio

    from mhvp.communication.services import forward_queued
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    settings = _settings(database, redis_url)

    async def run() -> None:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, tenant) as session:
                await forward_queued(session, settings, tenant)
        finally:
            await engine.dispose()

    asyncio.run(run())


def _forward_queue(
    database: Database, redis_url: str, tenant: Any, monkeypatch: pytest.MonkeyPatch
) -> list[Any]:
    """Runs ``forward_queued`` once with a fake dispatch; returns the ids handed over."""
    from mhvp.communication import forwarding_dispatch

    sent: list[Any] = []

    async def fake_forward(session: Any, settings: Any, tenant_id: Any, *args: Any) -> bool:
        sent.append(args[1].id)
        return True

    monkeypatch.setattr(forwarding_dispatch, "forward_and_archive", fake_forward)
    _run_forward_queue(database, redis_url, tenant)
    return sent


def test_relayed_invoice_with_changed_content_is_not_forwarded_twice(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nachprüfung zu Befund 21: Ein Verteiler ändert den Text einer Rechnung (Fußzeile) und
    behält die Message-ID. Die Mail wird als eigene Zeile gespeichert, ihre Rechnung aber nicht
    erneut vorgemerkt, solange eine Zeile mit derselben Message-ID vorgemerkt oder versendet
    ist (Status "duplicate" mit Verweis). Die Buchhaltung erhält die Rechnung einmal."""
    admin = bearer(login(client, world, "mpdadminb"))
    sender = f"rel{RUN}@lieferant.example.com"
    _enable_forwarding(client, admin, sender)
    rechnung = _mailbox(client, admin, f"rechnung-rel-{RUN}@example.com")
    brink = _mailbox(client, admin, f"brink-rel-{RUN}@example.com")
    post = _mailbox(client, admin, f"post-rel-{RUN}@example.com")
    msg_id = f"<rel-{RUN}@x>"
    subject = f"Rechnung {RUN} Verteiler"
    tenant = world.tenant_b

    def ingest(mailbox: dict[str, Any], body: str) -> None:
        raw = _invoice_eml(sender, subject, msg_id, "rechnung@x", body)
        _ingest_direct(database, redis_url, tenant, raw, [mailbox["id"]])

    ingest(rechnung, "Anbei die Rechnung.")
    ingest(brink, "Anbei die Rechnung.\n-- \nVerteiler Fusszeile")
    original, relayed = _rows(database, tenant, msg_id)
    assert (original.duplicate_of_id, relayed.duplicate_of_id) == (None, None)  # own mails
    assert original.forward == "queued"
    assert (relayed.forward, relayed.forward_of) == ("duplicate", str(original.id))

    sent = _forward_queue(database, redis_url, tenant, monkeypatch)
    assert [mid for mid in sent if mid in {original.id, relayed.id}] == [original.id]
    # A later relay while the original is already sent: again no second forward.
    ingest(post, "Anbei die Rechnung.\n-- \nZweite Fusszeile")
    rows = _rows(database, tenant, msg_id)
    assert [r.forward for r in rows] == ["sent", "duplicate", "duplicate"]
    assert rows[2].forward_of == str(original.id)
    assert _forward_queue(database, redis_url, tenant, monkeypatch) == []


def _forward_manually(client: TestClient, h: dict[str, str], message_id: str) -> Any:
    return client.post(f"{M}/messages/{message_id}/forward-invoice", headers=h)


def _suggest_then_allow(
    client: TestClient, h: dict[str, str], sender: str, raw: bytes
) -> dict[str, Any]:
    """Mail A arrives while its sender is not on the positive list (a "Weiterleiten?"
    suggestion without mailbox); afterwards the sender is put on the list, so a relay of the
    same invoice is queued automatically."""
    _ok(
        client.put(
            f"{M}/invoice-forwarding",
            json={
                "enabled": True,
                "forward_address": "buchhaltung@inbox.example.com",
                "sender_allowlist": [],
            },
            headers=h,
        )
    )
    suggestion = _ingest(client, h, raw)
    _enable_forwarding(client, h, sender)
    return suggestion


def test_manual_forward_is_refused_when_a_relay_is_queued_or_sent(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nachprüfung zu Befund 21, manueller Weg: Mail A ist nur ein "Weiterleiten?"-Vorschlag,
    ein Verteiler stellt dieselbe Rechnung (gleiche Message-ID, geänderte Fußzeile) als Mail B
    zu, deren Rechnung automatisch vorgemerkt und versendet wird. Die manuelle Weiterleitung
    von A wird mit 409 abgelehnt und nennt B; ohne Zugriff auf das Postfach von B bleibt B
    ungenannt. Die Buchhaltung erhält die Rechnung einmal."""
    from mhvp.communication import forwarding_dispatch

    admin = bearer(login(client, world, "mpdadmin"))
    std = bearer(login(client, world, "mpdstd"))
    tenant = world.tenant_a
    sender = f"man{RUN}@lieferant.example.com"
    msg_id, subject = f"<man-{RUN}@x>", f"Rechnung {RUN} manuell"
    suggestion = _suggest_then_allow(
        client, admin, sender, _invoice_eml(sender, subject, msg_id, "rechnung@x")
    )
    brink = _mailbox(client, admin, f"brink-man-{RUN}@example.com")
    relay = _invoice_eml(sender, subject, msg_id, "brink@x", "Anbei die Rechnung.\n-- \nVerteiler")
    _ingest_direct(database, redis_url, tenant, relay, [brink["id"]])
    original, relayed = _rows(database, tenant, msg_id)
    assert str(original.id) == suggestion["id"]
    assert (original.forward, relayed.forward) == (None, "queued")

    sent: list[Any] = []

    async def fake_forward(session: Any, settings: Any, tenant_id: Any, *args: Any) -> bool:
        sent.append(args[1].id)
        return True

    monkeypatch.setattr(forwarding_dispatch, "forward_and_archive", fake_forward)
    # Control: a suggestion without a relay is still forwarded manually.
    other = _ingest(
        client, admin, _invoice_eml(sender, f"{subject} solo", f"<man-solo-{RUN}@x>", "r@x")
    )
    assert _ok(_forward_manually(client, admin, other["id"]))["forwarded_to"]
    assert [str(mid) for mid in sent] == [other["id"]]
    sent.clear()

    named = f"Mail „{subject}“ vom 25.09.2026 im Postfach {brink['address']} mit derselben"
    queued = _forward_manually(client, admin, suggestion["id"])
    assert queued.status_code == 409, queued.text
    assert queued.json()["detail"] == (
        f"Die Rechnung dieser Mail ist bereits zur Weiterleitung vorgemerkt: {named} "
        "Message-ID. Eine zweite Weiterleitung an die Buchhaltung erfolgt nicht."
    )
    assert sent == []

    assert _forward_queue(database, redis_url, tenant, monkeypatch) == [relayed.id]
    monkeypatch.setattr(forwarding_dispatch, "forward_and_archive", fake_forward)
    done = _forward_manually(client, admin, suggestion["id"])
    assert done.status_code == 409, done.text
    assert done.json()["detail"].startswith(
        f"Die Rechnung dieser Mail wurde bereits weitergeleitet: {named} Message-ID."
    )
    # A member without access to the mailbox of B learns neither its subject nor its mailbox.
    hidden = _forward_manually(client, std, suggestion["id"])
    assert hidden.status_code == 409, hidden.text
    assert hidden.json()["detail"] == (
        "Die Rechnung dieser Mail wurde bereits weitergeleitet: eine Mail in einem anderen "
        "Postfach mit derselben Message-ID. Eine zweite Weiterleitung an die Buchhaltung "
        "erfolgt nicht."
    )
    assert sent == []
    assert [r.forward for r in _rows(database, tenant, msg_id)] == [None, "sent"]


def test_manual_forward_waits_for_a_parallel_ingest_of_the_same_message_id(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nachprüfung zu Befund 21, Gleichzeitigkeit: Während der Abruf von brink@ die Kopie B
    einer Rechnung aufnimmt und vormerkt (Mailsperre gehalten, noch nicht festgeschrieben),
    klickt jemand bei Mail A mit derselben Message-ID auf "Weiterleiten". Die manuelle
    Weiterleitung wartet auf die Mailsperre, sieht danach B als vorgemerkt und lehnt ab."""
    import asyncio
    import uuid

    from mhvp.communication import forwarding_dispatch
    from mhvp.communication.services import ingest_raw
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore

    admin = bearer(login(client, world, "mpdadmin"))
    tenant = world.tenant_a
    sender = f"race{RUN}@lieferant.example.com"
    msg_id, subject = f"<race-{RUN}@x>", f"Rechnung {RUN} parallel manuell"
    suggestion = _suggest_then_allow(
        client, admin, sender, _invoice_eml(sender, subject, msg_id, "rechnung@x")
    )
    brink = _mailbox(client, admin, f"brink-race-{RUN}@example.com")
    relay = _invoice_eml(sender, subject, msg_id, "brink@x", "Anbei die Rechnung.\n-- \nVerteiler")
    sent: list[Any] = []

    async def fake_forward(session: Any, settings: Any, tenant_id: Any, *args: Any) -> bool:
        sent.append(args[1].id)
        return True

    monkeypatch.setattr(forwarding_dispatch, "forward_and_archive", fake_forward)
    settings = _settings(database, redis_url)
    waiting_sql = sa.text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND "
        "database = (SELECT oid FROM pg_database WHERE datname = current_database())"
    )

    async def race() -> Any:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        held, release = asyncio.Event(), asyncio.Event()

        async def ingest_relay() -> None:
            async with tenant_transaction(factory, tenant) as session:
                await ingest_raw(
                    session,
                    BlobStore(settings),
                    settings,
                    tenant_id=tenant,
                    actor_user_id=None,
                    raw=relay,
                    mailbox_id=uuid.UUID(brink["id"]),
                    auto_ticket=False,
                )
                held.set()  # B is queued; the mail lock stays held until the commit
                await release.wait()

        async def forward_waits_for_the_mail_lock() -> bool:
            async with engine.connect() as conn:
                return bool(await conn.scalar(waiting_sql))

        try:
            ingest = asyncio.create_task(ingest_relay())
            waiter = asyncio.create_task(held.wait())
            done, _ = await asyncio.wait(
                {ingest, waiter}, timeout=30, return_when=asyncio.FIRST_COMPLETED
            )
            if waiter not in done:
                waiter.cancel()
                ingest.result()  # surfaces the error of the ingest
            forward = asyncio.create_task(
                asyncio.to_thread(_forward_manually, client, admin, suggestion["id"])
            )
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 30
            # Explicit synchronisation: the ingest commits only once the manual forward waits
            # for the mail lock (or, without that lock, has already finished).
            while not forward.done() and not await forward_waits_for_the_mail_lock():
                assert loop.time() < deadline, "forward neither waits nor ends"
                await asyncio.sleep(0.02)
            release.set()
            await ingest
            return await forward
        finally:
            release.set()
            await engine.dispose()

    response = asyncio.run(race())
    assert response.status_code == 409, response.text
    assert "ist bereits zur Weiterleitung vorgemerkt" in response.json()["detail"]
    assert sent == []
    original, relayed = _rows(database, tenant, msg_id)
    assert str(original.id) == suggestion["id"]
    assert (original.forward, relayed.forward) == (None, "queued")
    assert _forward_queue(database, redis_url, tenant, monkeypatch) == [relayed.id]


class _GmailSends:
    """Gmail client double of ``forwarding_dispatch``: records every forward sent."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send_raw(self, raw: bytes) -> str:
        self.sent.append(raw)
        return f"sent-{len(self.sent)}"

    async def archive(self, message_id: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


@pytest.fixture
def gmail_sends(monkeypatch: pytest.MonkeyPatch) -> _GmailSends:
    """The real ``forward_and_archive`` with a recorded Gmail send path (no OAuth, no network)."""
    from mhvp.communication import forwarding_dispatch

    sends = _GmailSends()

    async def oauth(*_: Any) -> tuple[str, str]:
        return "cid", "secret"

    monkeypatch.setattr(forwarding_dispatch, "oauth_client", oauth)
    monkeypatch.setattr(forwarding_dispatch, "make_client", lambda *_: sends)
    return sends


def _gmail_mailbox(client: TestClient, h: dict[str, str], address: str) -> dict[str, Any]:
    out: dict[str, Any] = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": address, "kind": "gmail", "secret": "rt"}, headers=h
        ),
        201,
    )
    return out


def _invoice_forward(client: TestClient, h: dict[str, str], message_id: str) -> dict[str, Any]:
    detail = _ok(client.get(f"{M}/messages/{message_id}", headers=h))
    out: dict[str, Any] = detail["classification"]["invoice_forward"]
    return out


def _confirmations(database: Database, tenant: Any, sender: str) -> Any:
    (row,) = _sql_rows(
        database,
        tenant,
        "SELECT invoice_forwarding -> 'confirmed_counts' -> :s AS n FROM tenant_settings "
        "WHERE tenant_id = :t",
        s=sender.lower(),
        t=str(tenant),
    )
    return row.n


def test_manual_forward_without_gmail_mailbox_is_not_sent(
    client: TestClient, world: World, database: Database, gmail_sends: _GmailSends
) -> None:
    """Nachprüfung 1.36.0: Mail A ohne Postfach (Upload) hat keinen Gmail-Sendeweg. Die
    manuelle Weiterleitung sendet nichts, antwortet 409 mit dem Grund und markiert A als
    "not_sent" statt "sent"; der Absender gilt nicht als bestätigt. Dieselbe Rechnung als Kopie
    B in einem Gmail-Postfach wird danach genau einmal weitergeleitet, A bleibt wegen B
    gesperrt."""
    from mhvp.communication.forwarding_dispatch import NOT_SENT_NO_GMAIL

    admin = bearer(login(client, world, "mpdadmin"))
    tenant = world.tenant_a
    sender = f"ns{RUN}@lieferant.example.com"
    msg_id, subject = f"<ns-{RUN}@x>", f"Rechnung {RUN} ohne Postfach"
    raw = _invoice_eml(sender, subject, msg_id, "rechnung@x")
    suggestion = _suggest_then_allow(client, admin, sender, raw)
    assert suggestion["mailbox_id"] is None

    refused = _forward_manually(client, admin, suggestion["id"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == NOT_SENT_NO_GMAIL
    assert gmail_sends.sent == []
    forward = _invoice_forward(client, admin, suggestion["id"])
    assert (forward.get("status"), forward.get("error")) == ("not_sent", NOT_SENT_NO_GMAIL)
    assert "forwarded_to" not in forward
    assert _confirmations(database, tenant, sender) is None

    box = _gmail_mailbox(client, admin, f"brink-ns-{RUN}@example.com")
    copy = _ingest(client, admin, raw, mailbox_id=box["id"])
    assert copy["id"] != suggestion["id"]
    forwarded = _ok(_forward_manually(client, admin, copy["id"]))
    assert forwarded["forwarded_to"] == "buchhaltung@inbox.example.com"
    assert len(gmail_sends.sent) == 1
    assert _confirmations(database, tenant, sender) == 1
    again = _forward_manually(client, admin, suggestion["id"])
    assert again.status_code == 409, again.text
    assert again.json()["detail"].startswith(
        "Die Rechnung dieser Mail wurde bereits weitergeleitet"
    )
    assert len(gmail_sends.sent) == 1
    by_id = {str(r.id): r.forward for r in _rows(database, tenant, msg_id)}
    assert by_id == {suggestion["id"]: "not_sent", copy["id"]: "sent"}


def test_manual_forward_without_gmail_mailbox_keeps_an_earlier_sent(
    client: TestClient, world: World, database: Database, gmail_sends: _GmailSends
) -> None:
    """Nachprüfung 1.36.0: Eine Mail, deren Rechnung schon als "sent" markiert ist (Postfach
    inzwischen entfernt oder Marker vor 1.36.0), behält "sent", wenn die manuelle Weiterleitung
    mangels Gmail-Postfach nichts sendet. Die Sperre für Kopien mit derselben Message-ID
    bleibt bestehen."""
    from mhvp.communication.forwarding_dispatch import NOT_SENT_NO_GMAIL

    admin = bearer(login(client, world, "mpdadmin"))
    tenant = world.tenant_a
    sender = f"nss{RUN}@lieferant.example.com"
    msg_id, subject = f"<nss-{RUN}@x>", f"Rechnung {RUN} bereits gesendet"
    raw = _invoice_eml(sender, subject, msg_id, "rechnung@x")
    suggestion = _suggest_then_allow(client, admin, sender, raw)
    _sql_rows(
        database,
        tenant,
        "UPDATE message SET classification = jsonb_set(classification, "
        "'{invoice_forward,status}', '\"sent\"') WHERE id = :id RETURNING id",
        id=suggestion["id"],
    )
    refused = _forward_manually(client, admin, suggestion["id"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == NOT_SENT_NO_GMAIL
    assert gmail_sends.sent == []
    assert _invoice_forward(client, admin, suggestion["id"])["status"] == "sent"
    relay = _invoice_eml(sender, subject, msg_id, "brink@x", "Anbei die Rechnung.\n-- \nVerteiler")
    box = _gmail_mailbox(client, admin, f"brink-nss-{RUN}@example.com")
    relayed = _ingest(client, admin, relay, mailbox_id=box["id"])
    assert _invoice_forward(client, admin, relayed["id"])["status"] == "duplicate"
    assert gmail_sends.sent == []


def test_queued_forward_without_gmail_mailbox_is_marked_not_sent(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    gmail_sends: _GmailSends,
) -> None:
    """Nachprüfung 1.36.0, automatischer Weg: eine vorgemerkte Rechnung in einem IMAP-Postfach
    hat keinen Gmail-Sendeweg. Der Nachlaufjob sendet nichts und markiert sie "not_sent" statt
    "sent". Ein Verteiler stellt dieselbe Rechnung (gleiche Message-ID, geänderte Fußzeile) in
    ein Gmail-Postfach zu; sie wird vorgemerkt und genau einmal weitergeleitet."""
    import email
    from email import policy

    from mhvp.communication.forwarding_dispatch import NOT_SENT_NO_GMAIL

    admin = bearer(login(client, world, "mpdadminb"))
    tenant = world.tenant_b
    sender = f"nsq{RUN}@lieferant.example.com"
    _enable_forwarding(client, admin, sender)
    imap = _mailbox(client, admin, f"rechnung-nsq-{RUN}@example.com")
    box = _gmail_mailbox(client, admin, f"brink-nsq-{RUN}@example.com")
    msg_id, subject = f"<nsq-{RUN}@x>", f"Rechnung {RUN} IMAP"
    raw = _invoice_eml(sender, subject, msg_id, "rechnung@x")
    _ingest_direct(database, redis_url, tenant, raw, [imap["id"]])
    (queued,) = _rows(database, tenant, msg_id)
    assert queued.forward == "queued"

    _run_forward_queue(database, redis_url, tenant)
    assert gmail_sends.sent == []
    (not_sent,) = _rows(database, tenant, msg_id)
    assert not_sent.forward == "not_sent"
    forward = _invoice_forward(client, admin, str(not_sent.id))
    assert (forward["error"], forward.get("forwarded_to")) == (NOT_SENT_NO_GMAIL, None)

    relay = _invoice_eml(sender, subject, msg_id, "brink@x", "Anbei die Rechnung.\n-- \nVerteiler")
    _ingest_direct(database, redis_url, tenant, relay, [box["id"]])
    assert [r.forward for r in _rows(database, tenant, msg_id)] == ["not_sent", "queued"]
    _run_forward_queue(database, redis_url, tenant)
    _run_forward_queue(database, redis_url, tenant)
    assert len(gmail_sends.sent) == 1
    parsed = email.message_from_bytes(gmail_sends.sent[0], policy=policy.default)
    assert parsed["Subject"] == f"Weiterleitung: {subject}"
    assert [r.forward for r in _rows(database, tenant, msg_id)] == ["not_sent", "sent"]


def test_not_sent_forward_goes_out_once_after_the_mailbox_is_switched_to_gmail(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    gmail_sends: _GmailSends,
) -> None:
    """Nachprüfung 1.36.0: Eine mangels Gmail-Postfach als "not_sent" markierte Rechnung wird
    nach Umstellung ihres Postfachs auf Gmail manuell genau einmal weitergeleitet; der Marker
    wird "sent" ohne den alten Grund."""
    admin = bearer(login(client, world, "mpdadminb"))
    tenant = world.tenant_b
    sender = f"nsg{RUN}@lieferant.example.com"
    _enable_forwarding(client, admin, sender)
    box = _mailbox(client, admin, f"rechnung-nsg-{RUN}@example.com")
    msg_id = f"<nsg-{RUN}@x>"
    raw = _invoice_eml(sender, f"Rechnung {RUN} Umstellung", msg_id, "rechnung@x")
    _ingest_direct(database, redis_url, tenant, raw, [box["id"]])
    _run_forward_queue(database, redis_url, tenant)
    (row,) = _rows(database, tenant, msg_id)
    assert row.forward == "not_sent"

    _ok(
        client.patch(
            f"{M}/mailboxes/{box['id']}", json={"kind": "gmail", "secret": "rt"}, headers=admin
        )
    )
    _ok(_forward_manually(client, admin, str(row.id)))
    assert len(gmail_sends.sent) == 1
    forward = _invoice_forward(client, admin, str(row.id))
    assert (forward["status"], forward["forwarded_to"]) == ("sent", "buchhaltung@inbox.example.com")
    assert "error" not in forward


class _FakeGmail:
    """Gmail client double for ``sync_mailbox``: a fixed inbox and an optional hook that runs
    before a message is fetched (orders two parallel syncs)."""

    def __init__(self, raws: dict[str, bytes], hooks: dict[str, Any] | None = None) -> None:
        self.raws, self.hooks = raws, hooks or {}

    async def profile_history_id(self) -> str:
        return "100"

    async def history_since(self, history_id: str) -> list[tuple[int, str]]:
        return []

    async def list_inbox(self, limit: int) -> list[str]:
        return list(self.raws)

    async def raw_message_with_thread(self, mid: str) -> tuple[bytes, str | None]:
        hook = self.hooks.get(mid)
        if hook is not None:
            await hook()
        return self.raws[mid], None


def _sql_rows(database: Database, tenant: Any, statement: str, **params: Any) -> list[Any]:
    engine = sa.create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant)},
            )
            return list(conn.execute(sa.text(statement), params).all())
    finally:
        engine.dispose()


def test_deadlock_of_mail_lock_and_ticket_number_goes_to_the_retry_queue(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Nachprüfung zu Befund 2: Die Mailsperre (lock_mail) und die Zeile der Ticketnummer
    (number_sequence, FOR UPDATE) bleiben bis zum Ende eines Abrufs gesperrt. Hat der Abruf
    von brink@ schon ein Ticket angelegt und hält der Abruf von info@ die Sperre einer
    gemeinsamen Mail, meldet PostgreSQL einen Deadlock. Das Opfer verliert nur diese Mail an
    den Savepoint: sie steht in mailbox_sync_retry und wird im nächsten Lauf aufgenommen, als
    verknüpfte Kopie mit einem Ticket, ohne Dublette."""
    import asyncio
    import uuid

    from mhvp.communication.gmail import sync_mailbox
    from mhvp.communication.models import Mailbox
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore

    admin = bearer(login(client, world, "mpdadminb"))
    info = _mailbox(client, admin, f"info-dl-{RUN}@example.com")
    brink = _mailbox(client, admin, f"brink-dl-{RUN}@example.com")
    sender = f"dl{RUN}@example.com"
    date = "Sun, 27 Sep 2026 11:00:00 +0200"
    # An earlier ticket of the tenant: the ticket number row exists before the syncs.
    warm_up = _eml(sender, f"Vorlauf dl {RUN}", "Text", f"<dl-pre-{RUN}@x>", date, "x@x")
    assert _ingest(client, admin, warm_up, auto_ticket=True)["ticket_id"]
    own_mid, shared_mid = f"own-{RUN}", f"shared-{RUN}"
    own = _eml(sender, f"Nur brink {RUN}", "Text", f"<dl-own-{RUN}@x>", date, "brink@x")
    shared_id = f"<dl-shared-{RUN}@x>"
    shared = _eml(sender, f"Gemeinsam {RUN}", "Text", shared_id, date, "info@x, brink@x")
    settings = _settings(database, redis_url)

    async def sync(
        factory: Any,
        blobs: Any,
        mailbox_id: str,
        gmail: _FakeGmail,
        pids: dict[str, int] | None = None,
    ) -> Any:
        async with tenant_transaction(factory, world.tenant_b) as session:
            if pids is not None:  # backend of this sync, for the lock synchronisation
                pids[mailbox_id] = await session.scalar(sa.text("SELECT pg_backend_pid()"))
            box = await session.get(Mailbox, uuid.UUID(mailbox_id))
            assert box is not None
            return await sync_mailbox(session, blobs, settings, box, gmail)  # type: ignore[arg-type]

    async def parallel() -> dict[str, Any]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        blobs = BlobStore(settings)
        brink_has_ticket = asyncio.Event()
        info_fetched_shared = asyncio.Event()
        pids: dict[str, int] = {}
        # info@ holds an advisory lock (the mail lock of the shared mail) and waits for another
        # lock (the ticket number row that brink@ holds).
        info_waits_sql = sa.text(
            "SELECT coalesce(bool_or(locktype = 'advisory' AND granted) AND bool_or(NOT granted),"
            " false) FROM pg_locks WHERE pid = :pid"
        )

        async def info_holds_mail_lock_and_waits() -> None:
            while True:
                async with engine.connect() as conn:
                    if await conn.scalar(info_waits_sql, {"pid": pids[info["id"]]}):
                        return
                await asyncio.sleep(0.02)

        async def brink_before_shared() -> None:
            brink_has_ticket.set()  # own mail ingested: the ticket number row stays locked
            await info_fetched_shared.wait()
            # Explicit synchronisation instead of a fixed sleep: brink@ asks for the mail lock
            # only once info@ holds it and waits for the ticket number, so the deadlock occurs
            # deterministically, also under load.
            await asyncio.wait_for(info_holds_mail_lock_and_waits(), 30)

        async def info_before_shared() -> None:
            info_fetched_shared.set()

        try:
            first = asyncio.create_task(
                sync(
                    factory,
                    blobs,
                    brink["id"],
                    _FakeGmail(
                        {own_mid: own, shared_mid: shared}, {shared_mid: brink_before_shared}
                    ),
                )
            )
            await asyncio.wait_for(brink_has_ticket.wait(), 30)
            second = asyncio.create_task(
                sync(
                    factory,
                    blobs,
                    info["id"],
                    _FakeGmail({shared_mid: shared}, {shared_mid: info_before_shared}),
                    pids,
                )
            )
            by_brink, by_info = await asyncio.gather(first, second)
            return {brink["id"]: by_brink, info["id"]: by_info}
        finally:
            await engine.dispose()

    async def next_run(mailbox_id: str) -> Any:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            gmail = _FakeGmail({shared_mid: shared})
            return await sync(factory, BlobStore(settings), mailbox_id, gmail)
        finally:
            await engine.dispose()

    counts = asyncio.run(parallel())
    victims = [box for box, c in counts.items() if c["failed"]]
    assert len(victims) == 1, counts
    victim = victims[0]
    assert counts[victim]["errors"][0]["gmail_id"] == shared_mid
    assert "deadlock detected" in counts[victim]["errors"][0]["error"]
    retry_sql = "SELECT gmail_message_id, attempts FROM mailbox_sync_retry WHERE mailbox_id = :m"
    assert [tuple(r) for r in _sql_rows(database, world.tenant_b, retry_sql, m=victim)] == [
        (shared_mid, 1)
    ]
    error_sql = "SELECT last_error FROM mailbox WHERE id = :m"
    assert "deadlock detected" in _sql_rows(database, world.tenant_b, error_sql, m=victim)[0][0]
    assert len(_rows(database, world.tenant_b, shared_id)) == 1

    again = asyncio.run(next_run(victim))
    assert (again["retried"], again["created"], again["failed"]) == (1, 1, 0)
    rows = _rows(database, world.tenant_b, shared_id)
    assert len(rows) == 2
    assert [r.duplicate_of_id for r in rows].count(None) == 1
    leading = next(r for r in rows if r.duplicate_of_id is None)
    assert str(leading.mailbox_id) == brink["id"]  # personal mailbox leads
    assert len({r.ticket_id for r in rows}) == 1
    assert rows[0].ticket_id is not None
    assert _sql_rows(database, world.tenant_b, retry_sql, m=victim) == []
    assert _sql_rows(database, world.tenant_b, error_sql, m=victim)[0][0] is None
