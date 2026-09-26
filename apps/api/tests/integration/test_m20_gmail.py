"""M20-01 Gmail sync against a fake Gmail API (httpx MockTransport): first sync from the inbox
creates one ticket per mail, a reply in the thread attaches to the same ticket, a second sync
with an unchanged history adds nothing, an expired history (404) falls back to the inbox without
duplicates, and a failing token refresh is recorded on the mailbox."""

import base64
import json
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any, cast

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.communication import gmail
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"


def _eml(sender: str, subject: str, msg_id: str, reply_to: str | None = None) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    if reply_to:
        msg["In-Reply-To"] = reply_to
    msg.set_content("Bitte um Rückmeldung.")
    return bytes(msg)


class FakeGmail:
    """Minimal Gmail API: profile, inbox list, history since cursor, raw message."""

    def __init__(self) -> None:
        self.inbox: dict[str, bytes] = {}
        # One history entry per added mail: (historyId, messageId), like Gmail's history.list.
        self.history: list[tuple[int, str]] = []
        self.history_id = 1000
        self.token_ok = True
        self.expire_history = False
        # Message ids whose raw fetch fails once with HTTP 500 (transient error).
        self.flaky: set[str] = set()
        self.raw_calls: dict[str, int] = {}
        self.threads: dict[str, str] = {}
        # Gmail ids whose INBOX label was removed (archive after ticket done, M15).
        self.archived: list[str] = []

    def add(self, mid: str, raw: bytes, thread: str | None = None) -> None:
        self.inbox[mid] = raw
        self.history_id += 1
        self.history.append((self.history_id, mid))
        self.threads[mid] = thread or f"thread-{mid}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            if not self.token_ok:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        assert request.headers.get("Authorization") == "Bearer t"
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": str(self.history_id)})
        if path.endswith("/messages"):
            return httpx.Response(
                200, json={"messages": [{"id": m} for m in reversed(list(self.inbox))]}
            )
        if path.endswith("/history"):
            if self.expire_history:
                return httpx.Response(404, json={"error": "expired"})
            since = int(request.url.params["startHistoryId"])
            added = [(hid, m) for hid, m in self.history if hid > since]
            return httpx.Response(
                200,
                json={
                    "history": [
                        {"id": str(hid), "messagesAdded": [{"message": {"id": m}}]}
                        for hid, m in added
                    ]
                },
            )
        if path.endswith("/modify"):
            self.archived.append(path.rsplit("/", 2)[-2])
            return httpx.Response(200, json={})
        mid = path.rsplit("/", 1)[-1]
        if mid not in self.inbox:
            return httpx.Response(404)
        self.raw_calls[mid] = self.raw_calls.get(mid, 0) + 1
        if mid in self.flaky:
            self.flaky.discard(mid)
            return httpx.Response(500, json={"error": "backend"})
        raw = base64.urlsafe_b64encode(self.inbox[mid]).decode().rstrip("=")
        return httpx.Response(200, json={"id": mid, "threadId": self.threads[mid], "raw": raw})


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"gm-{RUN}", name=f"Gmail {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("gmadmin", "tenant_admin"),
            ("gmread", "read_only_master_data"),
            ("gmclerk", "standard"),
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
    import asyncio

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
        assert (client_id, client_secret) in [("cid", "csecret"), ("tcid-0123456789", "tsecret")]
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


def _counts(result: dict[str, Any]) -> dict[str, int]:
    """The four classic counters of a sync result (the run also reports retried, remaining
    and the error list)."""
    return {k: result[k] for k in ("fetched", "created", "duplicates", "failed")}


def test_gmail_sync_creates_tickets_and_threads(
    client: TestClient, world: World, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = bearer(login(client, world, "gmadmin"))
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info{RUN}@example.com", "kind": "gmail", "secret": "rt"},
            headers=h,
        ),
        201,
    )
    assert "rt" not in json.dumps(box).replace("has_secret", "")  # token never returned
    assert box["has_secret"] is True
    box = _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h))
    assert box["enabled"] is True

    fake.add("g1", _eml(f"a{RUN}@example.com", f"Heizung defekt {RUN}", f"<g1-{RUN}@x>"))
    fake.add("g2", _eml(f"b{RUN}@example.com", f"Frage Abrechnung {RUN}", f"<g2-{RUN}@x>"))
    result = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert _counts(result) == {"fetched": 2, "created": 2, "duplicates": 0, "failed": 0}
    assert (result["retried"], result["remaining"], result["errors"]) == (0, 0, [])

    msgs = {m["subject"]: m for m in _ok(client.get(f"{M}/messages", headers=h))}
    first, second = msgs[f"Heizung defekt {RUN}"], msgs[f"Frage Abrechnung {RUN}"]
    assert first["ticket_id"]
    assert second["ticket_id"]
    assert first["ticket_id"] != second["ticket_id"]
    assert first["document_id"]  # raw mail stored as document
    # Gmail id is kept on ingest so "Erledigt archiviert Mail" can find the message (26.09.2026).
    assert first["gmail_message_id"]
    assert second["gmail_message_id"]
    # H6: a ticket from mail has an SLA clock like a manually created one.
    clock = _ok(client.get(f"/api/v1/sla/tickets/{first['ticket_id']}/sla", headers=h))
    assert clock["state"] == "running"

    # Unchanged history: nothing new, nothing duplicated.
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 0

    # Reply within the thread attaches to the existing ticket instead of opening a new one.
    fake.add("g3", _eml(f"a{RUN}@example.com", "AW: Heizung", f"<g3-{RUN}@x>", f"<g1-{RUN}@x>"))
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1
    reply = next(
        m for m in _ok(client.get(f"{M}/messages", headers=h)) if m["subject"] == "AW: Heizung"
    )
    assert reply["ticket_id"] == first["ticket_id"]
    assert reply["thread_id"] == first["id"]

    # Expired history: fallback to the inbox listing, deduplicated by Message-ID.
    fake.expire_history = True
    assert _counts(_ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))) == {
        "fetched": 3,
        "created": 0,
        "duplicates": 3,
        "failed": 0,
    }
    fake.expire_history = False

    # One unstorable mail (NUL byte survives parsing, ingest raises) does not roll back the
    # others: it is counted as failed, recorded on the mailbox, the rest is ingested.
    fake.add("g4", _eml(f"c{RUN}@example.com", f"Kaputt {RUN}", f"<g4-{RUN}@x>"))
    fake.add("g5", _eml(f"d{RUN}@example.com", f"Heil {RUN}", f"<g5-{RUN}@x>"))
    from mhvp.communication import services

    real_ingest = services.ingest_parsed

    async def broken(session: Any, *args: Any, parsed: Any, **kwargs: Any) -> Any:
        if parsed["subject"] == f"Kaputt {RUN}":
            from sqlalchemy import text

            await session.execute(text("select * from table_that_does_not_exist"))
        return await real_ingest(session, *args, parsed=parsed, **kwargs)

    monkeypatch.setattr(services, "ingest_parsed", broken)
    result = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert (result["created"], result["failed"]) == (1, 1)
    assert [e["gmail_id"] for e in result["errors"]] == ["g4"]
    listed = {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert "Nachricht g4" in (listed[box["id"]]["last_error"] or "")
    assert f"Heil {RUN}" in {m["subject"] for m in _ok(client.get(f"{M}/messages", headers=h))}

    # H1: the failed mail is retried on the next run (the cursor already moved past it) and
    # arrives once the failure is gone; nothing else is fetched twice.
    monkeypatch.setattr(services, "ingest_parsed", real_ingest)
    result = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert (result["retried"], result["created"], result["failed"]) == (1, 1, 0)
    assert f"Kaputt {RUN}" in {m["subject"] for m in _ok(client.get(f"{M}/messages", headers=h))}
    assert (listed := {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))})
    assert listed[box["id"]]["last_error"] is None
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["retried"] == 0

    # Failing token refresh: error recorded on the mailbox, no crash, no partial data.
    fake.token_ok = False
    assert client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h).status_code == 409
    listed = {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert "Token" in (listed[box["id"]]["last_error"] or "")

    # Read only role cannot manage mailboxes.
    r = bearer(login(client, world, "gmread"))
    assert client.post(f"{M}/mailboxes/{box['id']}/sync", headers=r).status_code == 403


def test_oauth_client_consent_and_mailbox_access(
    client: TestClient, world: World, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = bearer(login(client, world, "gmadmin"))
    clerk = bearer(login(client, world, "gmclerk"))

    # Environment client is the fallback until the tenant stores its own.
    status = _ok(client.get(f"{M}/oauth/google", headers=h))
    assert status["source"] == "environment"
    assert status["redirect_uri"].endswith("/api/v1/mail/oauth/google/callback")
    saved = _ok(
        client.put(
            f"{M}/oauth/google",
            json={"client_id": "tcid-0123456789", "client_secret": "tsecret"},
            headers=h,
        )
    )
    assert saved["source"] == "tenant"
    assert "tsecret" not in json.dumps(_ok(client.get(f"{M}/oauth/google", headers=h)))
    assert (
        client.put(f"{M}/oauth/google", json={"client_id": "x"}, headers=clerk).status_code == 403
    )

    # Consent: start returns the Google URL, the callback exchanges the code and creates the box.
    url = _ok(client.post(f"{M}/oauth/google/start", headers=h))["url"]
    assert url.startswith("https://accounts.google.com/")
    assert "client_id=tcid-0123456789" in url
    state = httpx.URL(url).params["state"]
    address = f"info-oauth-{RUN}@example.com"

    async def exchange(client_id: str, client_secret: str, code: str, *_: Any) -> tuple[str, str]:
        assert (client_id, client_secret, code) == ("tcid-0123456789", "tsecret", "c0de")
        return "rt", address

    monkeypatch.setattr(gmail, "exchange_code", exchange)
    r = client.get(
        f"{M}/oauth/google/callback",
        params={"state": state, "code": "c0de"},
        follow_redirects=False,
    )
    assert r.status_code == 200, r.text  # no web url configured: plain confirmation page
    assert address in r.text
    # State is single use.
    r = client.get(f"{M}/oauth/google/callback", params={"state": state, "code": "c0de"})
    assert r.status_code == 400

    boxes = {b["address"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    box = boxes[address]
    assert (box["kind"], box["enabled"], box["has_secret"]) == ("gmail", True, True)
    assert (box["is_default"], box["user_ids"]) == (False, [])

    # A mail in this box is invisible to a member without a grant.
    fake.add("o1", _eml(f"o{RUN}@example.com", f"OAuth Test {RUN}", f"<o1-{RUN}@x>"))
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1

    def subjects(hdr: dict[str, str]) -> set[str]:
        return {m["subject"] for m in _ok(client.get(f"{M}/messages", headers=hdr))}

    assert f"OAuth Test {RUN}" not in subjects(clerk)

    # Explicit grant makes it visible; removing the grant hides it again.
    granted = _ok(
        client.put(
            f"{M}/mailboxes/{box['id']}/users",
            json={"user_ids": [str(world.users["gmclerk"])]},
            headers=h,
        )
    )
    assert granted["user_ids"] == [str(world.users["gmclerk"])]
    assert f"OAuth Test {RUN}" in subjects(clerk)
    _ok(client.put(f"{M}/mailboxes/{box['id']}/users", json={"user_ids": []}, headers=h))
    assert f"OAuth Test {RUN}" not in subjects(clerk)

    # Default mailbox: every member sees it without a grant.
    assert _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"is_default": True}, headers=h))[
        "is_default"
    ]
    assert f"OAuth Test {RUN}" in subjects(clerk)

    # Removing the mailbox (M12): soft delete, the messages keep their mailbox binding and
    # are no longer visible to members without a grant (the box is no default any more);
    # the administrator still sees them, the box leaves the settings and cannot be synced.
    mail_id = next(
        m["id"]
        for m in _ok(client.get(f"{M}/messages", headers=h))
        if m["subject"] == f"OAuth Test {RUN}"
    )
    assert client.delete(f"{M}/mailboxes/{box['id']}", headers=h).status_code == 204
    assert address not in {b["address"] for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert f"OAuth Test {RUN}" not in subjects(clerk)
    assert client.get(f"{M}/messages/{mail_id}", headers=clerk).status_code == 404
    assert _ok(client.get(f"{M}/messages/{mail_id}", headers=h))["mailbox_id"] == box["id"]
    assert client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h).status_code == 404
    assert client.delete(f"{M}/mailboxes/{box['id']}", headers=h).status_code == 404


def _mailbox(client: TestClient, h: dict[str, str], address: str) -> dict[str, Any]:
    box = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": address, "kind": "gmail", "secret": "rt"}, headers=h
        ),
        201,
    )
    return cast(
        dict[str, Any],
        _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h)),
    )


def test_gmail_sync_batch_limit_keeps_every_mail(
    client: TestClient, world: World, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 26.09.2026, H1: three new mails with gmail_sync_batch=2 arrive over two runs; the
    cursor stops at the last processed history entry instead of skipping the third mail."""
    state = client.app.state  # type: ignore[attr-defined]
    monkeypatch.setattr(
        state, "settings", state.settings.model_copy(update={"gmail_sync_batch": 2})
    )
    h = bearer(login(client, world, "gmadmin"))
    box = _mailbox(client, h, f"batch{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))  # sets the cursor
    for i in range(3):
        fake.add(f"b{i}", _eml(f"b{i}{RUN}@example.com", f"Batch {i} {RUN}", f"<b{i}-{RUN}@x>"))

    first = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert (first["created"], first["remaining"]) == (2, 1)
    second = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert (second["created"], second["remaining"], second["duplicates"]) == (1, 0, 0)
    subjects = {m["subject"] for m in _ok(client.get(f"{M}/messages", headers=h))}
    assert {f"Batch {i} {RUN}" for i in range(3)} <= subjects
    third = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert (third["fetched"], third["created"]) == (0, 0)


def test_gmail_sync_transient_fetch_error_is_retried(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    """Review 26.09.2026, H1: a mail whose raw fetch fails once (HTTP 500) is recorded for a
    retry with the error text and ingested on the next run; the other mails of the batch are
    unaffected and never fetched twice."""
    h = bearer(login(client, world, "gmadmin"))
    box = _mailbox(client, h, f"flaky{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    fake.add("f1", _eml(f"f1{RUN}@example.com", f"Flaky eins {RUN}", f"<f1-{RUN}@x>"))
    fake.add("f2", _eml(f"f2{RUN}@example.com", f"Flaky zwei {RUN}", f"<f2-{RUN}@x>"))
    fake.flaky.add("f1")

    first = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert (first["created"], first["failed"]) == (1, 1)
    assert first["errors"][0]["gmail_id"] == "f1"
    assert "HTTP 500" in first["errors"][0]["error"]
    boxes = {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert "Nachricht f1" in (boxes[box["id"]]["last_error"] or "")

    second = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    assert (second["retried"], second["created"], second["failed"]) == (1, 1, 0)
    subjects = {m["subject"] for m in _ok(client.get(f"{M}/messages", headers=h))}
    assert {f"Flaky eins {RUN}", f"Flaky zwei {RUN}"} <= subjects
    assert fake.raw_calls["f2"] == 1
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["retried"] == 0


def test_gmail_ids_enable_archiving_and_thread_fallback(
    client: TestClient, world: World, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 26.09.2026, M15 and M7: a fetched mail stores its Gmail message and thread id;
    closing the ticket archives the mail at Gmail (INBOX label removed); a mail without any
    threading header but in the same Gmail thread joins the existing ticket."""
    state = client.app.state  # type: ignore[attr-defined]
    monkeypatch.setattr(state, "settings", state.settings.model_copy(update={"ai_inline": True}))
    h = bearer(login(client, world, "gmadmin"))
    box = _mailbox(client, h, f"ids{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    fake.add("i1", _eml(f"i1{RUN}@example.com", f"Ids eins {RUN}", f"<i1-{RUN}@x>"), thread="th-1")
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1
    first = next(
        m for m in _ok(client.get(f"{M}/messages", headers=h)) if m["subject"] == f"Ids eins {RUN}"
    )
    assert first["gmail_message_id"] == "i1"
    assert first["ticket_id"]

    # Same Gmail thread, no In-Reply-To or References (client dropped them): same ticket.
    fake.add("i2", _eml(f"i1{RUN}@example.com", "Nachtrag", f"<i2-{RUN}@x>"), thread="th-1")
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1
    second = next(
        m for m in _ok(client.get(f"{M}/messages", headers=h)) if m["subject"] == "Nachtrag"
    )
    assert second["ticket_id"] == first["ticket_id"]
    assert second["thread_id"] == first["id"]

    # Ticket done: both Gmail messages are archived (mailbox default archive_on_ticket_done).
    _ok(
        client.patch(
            f"/api/v1/tickets/{first['ticket_id']}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )
    assert sorted(fake.archived) == ["i1", "i2"]
