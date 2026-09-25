"""M20-01 Gmail sync against a fake Gmail API (httpx MockTransport): first sync from the inbox
creates one ticket per mail, a reply in the thread attaches to the same ticket, a second sync
with an unchanged history adds nothing, an expired history (404) falls back to the inbox without
duplicates, and a failing token refresh is recorded on the mailbox."""

import base64
import json
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
        self.history: list[str] = []
        self.history_id = 1000
        self.token_ok = True
        self.expire_history = False

    def add(self, mid: str, raw: bytes) -> None:
        self.inbox[mid] = raw
        self.history.append(mid)
        self.history_id += 1

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
            added = self.history[max(0, since - 1000) :]
            return httpx.Response(
                200,
                json={"history": [{"messagesAdded": [{"message": {"id": m}}]} for m in added]},
            )
        mid = path.rsplit("/", 1)[-1]
        if mid not in self.inbox:
            return httpx.Response(404)
        raw = base64.urlsafe_b64encode(self.inbox[mid]).decode().rstrip("=")
        return httpx.Response(200, json={"id": mid, "raw": raw})


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


def test_gmail_sync_creates_tickets_and_threads(
    client: TestClient, world: World, fake: FakeGmail
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
    assert result == {"fetched": 2, "created": 2, "duplicates": 0}

    msgs = {m["subject"]: m for m in _ok(client.get(f"{M}/messages", headers=h))}
    first, second = msgs[f"Heizung defekt {RUN}"], msgs[f"Frage Abrechnung {RUN}"]
    assert first["ticket_id"]
    assert second["ticket_id"]
    assert first["ticket_id"] != second["ticket_id"]
    assert first["document_id"]  # raw mail stored as document

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
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h)) == {
        "fetched": 3,
        "created": 0,
        "duplicates": 3,
    }
    fake.expire_history = False

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
    subjects = lambda hdr: {m["subject"] for m in _ok(client.get(f"{M}/messages", headers=hdr))}  # noqa: E731
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

    # Removing the mailbox keeps the messages (mailbox_id becomes null).
    assert client.delete(f"{M}/mailboxes/{box['id']}", headers=h).status_code == 204
    assert address not in {b["address"] for b in _ok(client.get(f"{M}/mailboxes", headers=h))}


def test_oversized_headers_are_capped_and_sync_survives(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    """Regression (production 500): a mail whose From/Message-ID exceeded the column limits
    failed the insert; the flush in sync_mailbox's finally block then raised
    PendingRollbackError on this and every following sync attempt of the mailbox."""
    h = bearer(login(client, world, "gmadmin"))
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"grenz{RUN}@example.com", "kind": "gmail", "secret": "rt"},
            headers=h,
        ),
        201,
    )
    box = _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h))
    long_id = "<" + "m" * 1200 + f"-{RUN}@x>"
    fake.add("x1", _eml(("l" * 360) + "@example.com", f"Grenzwerte {RUN}", long_id))
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1
    listed = {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert listed[box["id"]]["last_error"] is None


def test_failed_ingest_raises_original_error_not_pending_rollback(
    database: Database, redis_url: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database error inside the ingest poisons the transaction. sync_mailbox must let the
    original error through instead of masking it with PendingRollbackError from its finally."""
    import asyncio

    from sqlalchemy import text as sql_text
    from sqlalchemy.exc import DBAPIError

    from mhvp.communication import services as comm_services
    from mhvp.communication.models import Mailbox
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore

    crypto.set_master_key(b"k" * 32)
    settings = _settings(database, redis_url)

    async def poisoned_ingest(session: Any, *args: Any, **kwargs: Any) -> Any:
        with pytest.raises(DBAPIError):
            await session.execute(sql_text("SELECT 1/0"))
        raise ValueError("Originalfehler")

    monkeypatch.setattr(comm_services, "ingest_raw", poisoned_ingest)
    fake = FakeGmail()
    fake.add("p1", _eml(f"p{RUN}@example.com", "Kaputt", f"<p1-{RUN}@x>"))
    gclient = gmail.GmailClient("cid", "cs", "rt", transport=httpx.MockTransport(fake.handler))

    async def run() -> None:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            with pytest.raises(ValueError, match="Originalfehler"):
                async with tenant_transaction(factory, world.tenant_a) as session:
                    box = Mailbox(
                        tenant_id=world.tenant_a,
                        address=f"poison{RUN}@example.com",
                        kind="gmail",
                        enabled=True,
                        secret="rt",
                    )
                    session.add(box)
                    await session.flush()
                    with mock_aws():
                        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
                        await gmail.sync_mailbox(
                            session, BlobStore(settings), settings, box, gclient
                        )
            await gclient.aclose()
        finally:
            await engine.dispose()

    asyncio.run(run())
