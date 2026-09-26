"""Review 26.09.2026 (docs/reviews/2026-09-26-review-tickets-mail.md), H6, H7 and M14:
closing a ticket via PATCH or bulk action stops its SLA clock and emits
``ticket.status_changed``; reopening restarts the clock; GET /tickets paginates with
``page``/``page_size`` and reports the total in ``X-Total-Count``; the SLA backfill starts
clocks for open tickets that were created without one.

Nachbearbeitung (M5, M6, M14 Rest, N1, N3, N4): ticket detail with comment authors,
``internal_description`` and bundled mail attachments; ``ticket.assigned`` from the service
layer with ``TicketAssignee.primary`` kept in sync; mail archiving runs only after the commit;
dangling references answer 404; a reply subject is folded to one line."""

import asyncio
from collections.abc import Iterator
from datetime import datetime
from typing import Any, cast

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
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rv-{RUN}", name=f"Review {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("rvadmin", "rvtech"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ticket(c: TestClient, h: dict[str, str], title: str) -> dict[str, Any]:
    return cast(dict[str, Any], _ok(c.post(T, json={"title": title}, headers=h), 201))


def _clock(c: TestClient, h: dict[str, str], ticket_id: str) -> dict[str, Any]:
    return cast(dict[str, Any], _ok(c.get(f"/api/v1/sla/tickets/{ticket_id}/sla", headers=h)))


def _events(c: TestClient, h: dict[str, str], ticket_id: str) -> list[dict[str, Any]]:
    rows = _ok(
        c.get(
            "/api/v1/tenant/events",
            params={"type": "ticket.status_changed", "page_size": 200},
            headers=h,
        )
    )
    return [e for e in rows if e["entity_id"] == ticket_id]


def test_patch_done_stops_clock_and_emits_status_event(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rvadmin"))
    ticket = _ticket(client, h, f"Uhr Patch {RUN}")
    assert _clock(client, h, ticket["id"])["state"] == "running"

    _ok(client.patch(f"{T}/{ticket['id']}", json={"status": "in_progress"}, headers=h))
    _ok(
        client.patch(
            f"{T}/{ticket['id']}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )
    clock = _clock(client, h, ticket["id"])
    assert clock["state"] == "done"
    assert clock["resolved_at"] is not None

    events = _events(client, h, ticket["id"])
    assert [(e["payload"]["from"], e["payload"]["to"]) for e in reversed(events)] == [
        ("new", "in_progress"),
        ("in_progress", "done"),
    ]
    detail = _ok(client.get(f"{T}/{ticket['id']}", headers=h))
    assert detail["resolved_at"] is not None

    # Reopening restarts the resolution clock.
    _ok(client.patch(f"{T}/{ticket['id']}", json={"status": "in_progress"}, headers=h))
    clock = _clock(client, h, ticket["id"])
    assert (clock["state"], clock["resolved_at"]) == ("running", None)
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["resolved_at"] is None

    # Closing without an Erledigungsnotiz changes nothing and emits nothing (also for the
    # admin bypass, which would allow in_progress to closed).
    assert (
        client.patch(f"{T}/{ticket['id']}", json={"status": "closed"}, headers=h).status_code == 422
    )
    assert len(_events(client, h, ticket["id"])) == 3


def test_bulk_status_stops_clocks_and_reports_failures(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rvadmin"))
    first = _ticket(client, h, f"Uhr Bulk 1 {RUN}")
    second = _ticket(client, h, f"Uhr Bulk 2 {RUN}")
    closed = _ticket(client, h, f"Uhr Bulk 3 {RUN}")
    _ok(
        client.patch(
            f"{T}/{closed['id']}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )
    _ok(
        client.patch(
            f"{T}/{closed['id']}",
            json={"status": "closed", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )

    result = _ok(
        client.post(
            f"{T}/bulk-status",
            json={
                "ticket_ids": [first["id"], second["id"], closed["id"]],
                "status": "rejected",
                "resolution": {"kind": "auskunft_erteilt"},
            },
            headers=h,
        )
    )
    # rvadmin is tenant_admin: the admin bypass allows closed to rejected as well.
    assert {c["id"] for c in result["changed"]} == {first["id"], second["id"], closed["id"]}
    assert result["failed"] == []
    assert _events(client, h, closed["id"])[0]["payload"]["to"] == "rejected"
    for ticket in (first, second):
        assert _clock(client, h, ticket["id"])["state"] == "done"
        events = _events(client, h, ticket["id"])
        assert events[0]["payload"] == {"from": "new", "to": "rejected", "number": ticket["number"]}


def test_list_tickets_paginates_and_stays_a_list(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rvadmin"))
    numbers = [_ticket(client, h, f"Seite {i} {RUN}")["number"] for i in range(5)]

    # Legacy call: plain list, first page, total in the header.
    legacy = client.get(T, params={"q": "Seite", "limit": 2}, headers=h)
    rows = _ok(legacy)
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert int(legacy.headers["x-total-count"]) >= 5
    assert (legacy.headers["x-page"], legacy.headers["x-page-size"]) == ("1", "2")

    page1 = client.get(T, params={"q": "Seite", "page": 1, "page_size": 2}, headers=h)
    page2 = client.get(T, params={"q": "Seite", "page": 2, "page_size": 2}, headers=h)
    page3 = client.get(T, params={"q": "Seite", "page": 3, "page_size": 2}, headers=h)
    total = int(page1.headers["x-total-count"])
    seen = [t["number"] for p in (page1, page2, page3) for t in _ok(p)]
    assert len(seen) == min(total, 6)
    assert len(set(seen)) == len(seen)  # no overlap between pages
    assert seen == sorted(seen, reverse=True)  # newest number first across pages
    page4 = _ok(client.get(T, params={"q": "Seite", "page": 4, "page_size": 2}, headers=h))
    assert set(numbers) <= set(seen) | {t["number"] for t in page4}
    assert client.get(T, params={"page": 0}, headers=h).status_code == 422
    assert client.get(T, params={"page_size": 501}, headers=h).status_code == 422


def test_sla_backfill_starts_clocks_for_open_tickets_without_one(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Tickets that bypassed start_clock (older rows, imports) get a clock from the SLA job,
    started at the ticket's creation time; closed tickets are left alone."""
    from sqlalchemy import text

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.sla.service import backfill_clocks

    h = bearer(login(client, world, "rvadmin"))
    open_ticket = _ticket(client, h, f"Nachlauf offen {RUN}")
    done_ticket = _ticket(client, h, f"Nachlauf erledigt {RUN}")
    _ok(
        client.patch(
            f"{T}/{done_ticket['id']}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )

    async def run() -> int:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                await session.execute(
                    text("DELETE FROM sla_clock WHERE ticket_id IN (:a, :b)"),
                    {"a": open_ticket["id"], "b": done_ticket["id"]},
                )
            async with tenant_transaction(factory, world.tenant_a) as session:
                return await backfill_clocks(session, world.tenant_a)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) >= 1
    clock = _clock(client, h, open_ticket["id"])
    assert clock["state"] == "running"
    assert datetime.fromisoformat(clock["started_at"]) == datetime.fromisoformat(
        open_ticket["created_at"]
    )
    assert client.get(f"/api/v1/sla/tickets/{done_ticket['id']}/sla", headers=h).status_code == 404


def _domain_events(
    c: TestClient, h: dict[str, str], ticket_id: str, kind: str
) -> list[dict[str, Any]]:
    rows = _ok(c.get("/api/v1/tenant/events", params={"type": kind, "page_size": 200}, headers=h))
    return [e for e in rows if e["entity_id"] == ticket_id]


def test_assign_via_patch_emits_event_and_moves_primary_mark(
    client: TestClient, world: World
) -> None:
    """M14 (rest) and N3: the primary assignee is set in the service layer with the domain
    event ``ticket.assigned``; the previous primary row in TicketAssignee loses its mark."""
    h = bearer(login(client, world, "rvadmin"))
    admin, tech = str(world.users["rvadmin"]), str(world.users["rvtech"])
    ticket = _ticket(client, h, f"Zuweisung {RUN}")

    _ok(client.patch(f"{T}/{ticket['id']}", json={"assignee_user_id": admin}, headers=h))
    _ok(client.patch(f"{T}/{ticket['id']}", json={"assignee_user_id": tech}, headers=h))
    # Unchanged assignee: no second event.
    _ok(client.patch(f"{T}/{ticket['id']}", json={"assignee_user_id": tech}, headers=h))

    rows = _ok(client.get(f"{T}/{ticket['id']}/assignees", headers=h))
    assert {(r["user_id"], r["primary"], r["reason"]) for r in rows} == {
        (admin, False, "manuell"),
        (tech, True, "manuell"),
    }
    events = _domain_events(client, h, ticket["id"], "ticket.assigned")
    assert [(e["payload"]["from"], e["payload"]["to"]) for e in reversed(events)] == [
        (None, admin),
        (admin, tech),
    ]
    detail = _ok(client.get(f"{T}/{ticket['id']}", headers=h))
    assert detail["assignee_user_id"] == tech
    assigned = [e for e in detail["events"] if e["kind"] == "assigned"]
    assert [(e["data"]["from"], e["data"]["to"]) for e in assigned] == [
        (None, admin),
        (admin, tech),
    ]
    # POST /assignees with primary goes the same way.
    _ok(
        client.post(
            f"{T}/{ticket['id']}/assignees",
            json={"user_id": admin, "reason": "Vertretung", "primary": True},
            headers=h,
        ),
        201,
    )
    rows = _ok(client.get(f"{T}/{ticket['id']}/assignees", headers=h))
    assert {(r["user_id"], r["primary"], r["reason"]) for r in rows} == {
        (admin, True, "Vertretung"),
        (tech, False, "manuell"),
    }
    assert len(_domain_events(client, h, ticket["id"], "ticket.assigned")) == 3


def test_mail_archiving_runs_after_the_status_commit(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M14 (rest): the archive consumer sees the committed status; a status change whose
    commit fails never reaches it."""
    from sqlalchemy import text

    from mhvp.communication import services as comm_services
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    seen: list[str | None] = []
    settings = _settings(database, redis_url)

    async def _fake(session: Any, _settings: Any, tenant_id: Any, ticket_id: Any) -> None:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as other:
                seen.append(
                    await other.scalar(
                        text("SELECT status::text FROM ticket WHERE id = :id"),
                        {"id": str(ticket_id)},
                    )
                )
        finally:
            await engine.dispose()

    monkeypatch.setattr(comm_services, "enqueue_archive_for_ticket", _fake)
    h = bearer(login(client, world, "rvadmin"))
    ticket = _ticket(client, h, f"Archiv nach Commit {RUN}")
    _ok(
        client.patch(
            f"{T}/{ticket['id']}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )
    assert seen == ["done"]

    # A failing transaction (unknown topic, checked after the status change in the same
    # request) rolls back and drops the consumer.
    seen.clear()
    other = _ticket(client, h, f"Archiv Rollback {RUN}")
    response = client.patch(
        f"{T}/{other['id']}",
        json={
            "status": "done",
            "topic": f"unbekannt-{RUN}",
            "resolution": {"kind": "auskunft_erteilt"},
        },
        headers=h,
    )
    assert response.status_code == 422, response.text
    assert seen == []
    assert _ok(client.get(f"{T}/{other['id']}", headers=h))["status"] == "new"


def test_detail_has_comment_authors_internal_description_and_mail_attachments(
    client: TestClient, world: World
) -> None:
    """M5 and M6: the ticket detail returns comments with id, author and document ids,
    ``internal_description`` (readable and patchable) and the inbound mail attachments with
    document metadata from one bundled query."""
    from email.message import EmailMessage

    h = bearer(login(client, world, "rvadmin"))
    sender = f"detail-{RUN}@example.org"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Max",
                "last_name": f"Detail{RUN}",
                "emails": [{"email": sender}],
            },
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post(T, json={"title": f"Detail {RUN}", "contact_id": contact["id"]}, headers=h),
        201,
    )
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("notiz.pdf", b"%PDF-1.4 notiz", "application/pdf")},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{T}/{ticket['id']}/comments",
            json={"body": "Rückruf erledigt", "internal": True, "document_ids": [doc["id"]]},
            headers=h,
        ),
        201,
    )
    _ok(client.patch(f"{T}/{ticket['id']}", json={"internal_description": "Nur intern"}, headers=h))
    box = _ok(
        client.post(
            "/api/v1/mail/mailboxes",
            json={"address": f"detail-{RUN}@example.com", "secret": "geheim"},
            headers=h,
        ),
        201,
    )
    mail = EmailMessage()
    mail["From"] = f"Mieter <{sender}>"
    mail["To"] = f"detail-{RUN}@example.com"
    mail["Subject"] = f"Wasserschaden TNR#{ticket['number']}"
    mail["Message-ID"] = f"<detail-{RUN}@example.test>"
    mail.set_content("Foto anbei.")
    mail.add_attachment(
        b"%PDF-1.4 foto", maintype="application", subtype="pdf", filename="foto.pdf"
    )
    eml = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("mail.eml", bytes(mail), "message/rfc822")},
            headers=h,
        ),
        201,
    )
    msg = _ok(
        client.post(
            "/api/v1/mail/ingest",
            json={"document_id": eml["id"], "mailbox_id": box["id"]},
            headers=h,
        ),
        201,
    )
    assert msg["ticket_id"] == ticket["id"]  # TNR#<nummer> im Betreff

    detail = _ok(client.get(f"{T}/{ticket['id']}", headers=h))
    assert detail["internal_description"] == "Nur intern"
    (comment,) = detail["comments"]
    assert comment["author_user_id"] == str(world.users["rvadmin"])
    assert comment["author_name"] == "rvadmin"
    assert comment["document_ids"] == [doc["id"]]
    assert comment["id"]
    attachments = detail["mail_attachments"]
    assert [(a["filename"], a["mime_type"], a["message_id"]) for a in attachments] == [
        ("foto.pdf", "application/pdf", msg["id"])
    ]
    assert attachments[0]["document_id"] == msg["attachment_document_ids"][0]
    assert (
        _ok(client.get(T, params={"q": f"Detail {RUN}"}, headers=h))[0]["internal_description"]
        == "Nur intern"
    )


def test_dangling_references_answer_404(client: TestClient, world: World) -> None:
    """N4: unknown contact, property, unit or comment document ids are rejected with 404
    instead of a foreign key error."""
    h = bearer(login(client, world, "rvadmin"))
    ghost = "0192abcd-0000-7000-8000-00000000dead"
    for field in ("contact_id", "property_id", "unit_id"):
        response = client.post(T, json={"title": "Geist", field: ghost}, headers=h)
        assert response.status_code == 404, (field, response.text)
    ticket = _ticket(client, h, f"Referenzen {RUN}")
    assert (
        client.patch(f"{T}/{ticket['id']}", json={"contact_id": ghost}, headers=h).status_code
        == 404
    )
    response = client.post(
        f"{T}/{ticket['id']}/comments", json={"body": "x", "document_ids": [ghost]}, headers=h
    )
    assert response.status_code == 404
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["comments"] == []


def test_reply_subject_is_folded_to_one_line() -> None:
    """N1: a subject with line breaks never reaches the mail header."""
    from pydantic import ValidationError

    from mhvp.tickets.routers import TicketReplyIn

    body = TicketReplyIn(subject="Antwort\r\nBcc: x@example.com", body="Text")
    assert body.subject == "Antwort Bcc: x@example.com"
    with pytest.raises(ValidationError):
        TicketReplyIn(subject="\r\n", body="Text")
