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
