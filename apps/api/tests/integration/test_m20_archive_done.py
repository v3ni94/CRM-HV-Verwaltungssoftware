"""Erledigt archiviert Mail (operator report 27.09.2026): every close path writes back to
Gmail. A mail set to done (single or bulk), a ticket closed by status (done, closed,
rejected), by bulk status or by merge archives the linked Gmail messages (INBOX and UNREAD
removed) including mails that joined the thread later; the outcome is recorded on the
message (``archive_status``); a consent without ``gmail.modify`` marks the mailbox
(``archive_scope_missing``) and the reconnect catches up; the beat job retries open jobs;
the manual endpoint is idempotent."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import text

from mhvp.communication import gmail
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_gmail import FakeGmail, M, _eml, _mailbox, _ok

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"


class ArchiveFake(FakeGmail):
    """FakeGmail plus the label payload of every modify call and switchable 403 answers."""

    def __init__(self) -> None:
        super().__init__()
        self.modify_bodies: list[dict[str, Any]] = []
        self.forbidden_reason: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/modify"):
            if self.forbidden_reason:
                return httpx.Response(
                    403,
                    json={
                        "error": {
                            "code": 403,
                            "message": "Insufficient Permission",
                            "errors": [{"reason": self.forbidden_reason}],
                        }
                    },
                )
            self.modify_bodies.append(json.loads(request.content))
        return super().handler(request)


@pytest.fixture
def fake() -> ArchiveFake:
    return ArchiveFake()


async def _world(settings: Any) -> World:
    """Own tenant and users (slug ``ga``) so the module runs beside ``test_m20_gmail``."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ga-{RUN}", name=f"Archiv {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("gaadmin", "tenant_admin"), ("gaclerk", "standard")]:
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
def client(
    database: Database, redis_url: str, fake: ArchiveFake, monkeypatch: pytest.MonkeyPatch
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


def _inline(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    state = client.app.state  # type: ignore[attr-defined]
    monkeypatch.setattr(state, "settings", state.settings.model_copy(update={"ai_inline": True}))


def _ingest(
    client: TestClient,
    h: dict[str, str],
    box: dict[str, Any],
    fake: FakeGmail,
    gid: str,
    subject: str,
) -> dict[str, Any]:
    fake.add(gid, _eml(f"{gid}{RUN}@example.com", subject, f"<{gid}-{RUN}@x>"))
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1
    return next(m for m in _ok(client.get(f"{M}/messages", headers=h)) if m["subject"] == subject)


def _message(client: TestClient, h: dict[str, str], message_id: str) -> dict[str, Any]:
    return dict(_ok(client.get(f"{M}/messages/{message_id}", headers=h)))


def _sql(
    world: World, database: Database, redis_url: str, stmt: str, params: dict[str, Any]
) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def run() -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), world.tenant_a) as s:
                return (await s.execute(text(stmt), params)).scalar()
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_mail_done_archives_and_records_status(
    client: TestClient, world: World, fake: ArchiveFake, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    box = _mailbox(client, h, f"done{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    mail = _ingest(client, h, box, fake, "d1", f"Erledigt eins {RUN}")
    assert mail["archive_status"] is None

    done = _ok(client.patch(f"{M}/messages/{mail['id']}", json={"status": "done"}, headers=h))
    assert done["status"] == "done"
    assert fake.archived == ["d1"]
    # INBOX and UNREAD leave the message (operator: archived and read).
    assert fake.modify_bodies[-1] == {"removeLabelIds": ["INBOX", "UNREAD"]}
    after = _message(client, h, mail["id"])
    assert after["archive_status"] == "archived"
    assert after["archived_at"]
    assert after["archive_attempted_at"]
    assert after["archive_error"] is None

    # Idempotent: done again and the manual endpoint do not call Gmail twice.
    _ok(client.patch(f"{M}/messages/{mail['id']}", json={"status": "done"}, headers=h))
    manual = _ok(client.post(f"{M}/messages/{mail['id']}/archive", headers=h))
    assert manual["result"] == {"archived": 0, "skipped": 0, "failed": 0}
    assert fake.archived == ["d1"]


def test_bulk_done_archives_every_mail(
    client: TestClient, world: World, fake: ArchiveFake, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    box = _mailbox(client, h, f"bulk{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    one = _ingest(client, h, box, fake, "b1", f"Bulk eins {RUN}")
    two = _ingest(client, h, box, fake, "b2", f"Bulk zwei {RUN}")
    result = _ok(
        client.post(
            f"{M}/messages/bulk", json={"ids": [one["id"], two["id"]], "action": "done"}, headers=h
        )
    )
    assert sorted(result["changed"]) == sorted([one["id"], two["id"]])
    assert sorted(fake.archived) == ["b1", "b2"]
    assert {_message(client, h, m["id"])["archive_status"] for m in (one, two)} == {"archived"}


@pytest.mark.parametrize("status", ["done", "closed", "rejected"])
def test_ticket_closing_status_archives_linked_and_thread_mails(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    fake: ArchiveFake,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    """Ticket status via PATCH (also closed after done, and rejected): the ticket mails and a
    later mail of the same CRM thread that was never attached to the ticket are archived."""
    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    box = _mailbox(client, h, f"tk{status}{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    first = _ingest(client, h, box, fake, f"t{status}1", f"Ticket {status} eins {RUN}")
    later = _ingest(client, h, box, fake, f"t{status}2", f"Ticket {status} zwei {RUN}")
    # The second mail joined the thread of the first but lost its ticket link (manual
    # reassignment): it still belongs to the conversation and leaves the inbox with it.
    _sql(
        world,
        database,
        redis_url,
        "UPDATE message SET thread_id = :root, ticket_id = NULL WHERE id = :id RETURNING id",
        {"root": first["id"], "id": later["id"]},
    )
    ticket_id = first["ticket_id"]
    if status == "closed":
        _ok(
            client.patch(
                f"{T}/{ticket_id}",
                json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
                headers=h,
            )
        )
        fake.archived.clear()
        # Reset so the second close has something to archive again (idempotency is covered
        # elsewhere): pretend the mails came back into the inbox.
        _sql(
            world,
            database,
            redis_url,
            "UPDATE message SET archived_at = NULL, archive_status = NULL "
            "WHERE id IN (:a, :b) RETURNING 1",
            {"a": first["id"], "b": later["id"]},
        )
    body: dict[str, Any] = {"status": status}
    if status != "closed":
        body["resolution"] = {
            "kind": "kein_handlungsbedarf" if status == "rejected" else "auskunft_erteilt"
        }
    _ok(client.patch(f"{T}/{ticket_id}", json=body, headers=h))
    assert sorted(fake.archived) == sorted([f"t{status}1", f"t{status}2"])
    assert _message(client, h, later["id"])["archive_status"] == "archived"


def test_ticket_bulk_status_and_merge_archive_mails(
    client: TestClient, world: World, fake: ArchiveFake, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    box = _mailbox(client, h, f"bm{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    bulk_mail = _ingest(client, h, box, fake, "bm1", f"Bulk Ticket {RUN}")
    result = _ok(
        client.post(
            f"{T}/bulk-status",
            json={
                "ticket_ids": [bulk_mail["ticket_id"]],
                "status": "done",
                "resolution": {"kind": "auskunft_erteilt"},
            },
            headers=h,
        )
    )
    assert result["failed"] == []
    assert fake.archived == ["bm1"]

    # Merge: the source ticket is closed, its mail now belongs to the target (still open).
    source = _ingest(client, h, box, fake, "mg1", f"Merge Quelle {RUN}")
    target = _ingest(client, h, box, fake, "mg2", f"Merge Ziel {RUN}")
    _ok(
        client.post(
            f"{T}/merge",
            json={"ticket_ids": [source["ticket_id"]], "target_ticket_id": target["ticket_id"]},
            headers=h,
        ),
        201,
    )
    # The merge moves the source mail to the open target: nothing leaves the inbox yet.
    assert fake.archived == ["bm1"]
    assert _message(client, h, source["id"])["ticket_id"] == target["ticket_id"]
    assert _message(client, h, source["id"])["archive_status"] is None
    # Closing the target archives its own mail and the one assigned later by the merge.
    _ok(
        client.patch(
            f"{T}/{target['ticket_id']}",
            json={"status": "rejected", "resolution": {"kind": "kein_handlungsbedarf"}},
            headers=h,
        )
    )
    assert sorted(fake.archived) == ["bm1", "mg1", "mg2"]
    assert _message(client, h, source["id"])["archive_status"] == "archived"
    assert _message(client, h, target["id"])["archive_status"] == "archived"


def test_missing_scope_is_recorded_and_reconnect_catches_up(
    client: TestClient, world: World, fake: ArchiveFake, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Older consent without gmail.modify: Gmail answers 403 insufficientPermissions. The
    mailbox carries the notice, the mail is marked scope_missing, the retry job leaves the
    mailbox alone; reconnecting via OAuth clears the notice and archives the open mails."""
    from mhvp.communication.tasks import archive_retry_once

    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    address = f"scope{RUN}@example.com"
    box = _mailbox(client, h, address)
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    mail = _ingest(client, h, box, fake, "s1", f"Scope fehlt {RUN}")
    fake.forbidden_reason = "insufficientPermissions"
    _ok(client.patch(f"{M}/messages/{mail['id']}", json={"status": "done"}, headers=h))
    assert fake.archived == []
    after = _message(client, h, mail["id"])
    assert after["archive_status"] == "scope_missing"
    assert "gmail.modify" in (after["archive_error"] or "")
    boxes = {b["address"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert boxes[address]["archive_scope_missing"] is True

    # Retry job skips the mailbox while the scope is missing (no pointless 403 loop).
    state = client.app.state  # type: ignore[attr-defined]
    counts = asyncio.run(archive_retry_once(state.settings, world.tenant_a))
    assert counts["archived"] == 0
    assert _message(client, h, mail["id"])["archive_status"] == "scope_missing"

    # Reconnect: the consent URL forces the consent screen with incremental scopes.
    url = _ok(client.post(f"{M}/oauth/google/start", headers=h))["url"]
    params = httpx.URL(url).params
    assert params["prompt"] == "consent"
    assert params["include_granted_scopes"] == "true"
    assert "gmail.modify" in params["scope"]

    async def exchange(*_: Any) -> tuple[str, str]:
        return "rt", address

    monkeypatch.setattr(gmail, "exchange_code", exchange)
    fake.forbidden_reason = None
    r = client.get(
        f"{M}/oauth/google/callback",
        params={"state": params["state"], "code": "c0de"},
        follow_redirects=False,
    )
    assert r.status_code == 200, r.text
    boxes = {b["address"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert boxes[address]["archive_scope_missing"] is False
    # The catch up ran after the commit (inline without a worker).
    assert fake.archived == ["s1"]
    assert _message(client, h, mail["id"])["archive_status"] == "archived"


def test_rate_limit_403_is_a_retryable_failure(
    client: TestClient, world: World, fake: ArchiveFake, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.communication.tasks import archive_retry_once

    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    address = f"rate{RUN}@example.com"
    box = _mailbox(client, h, address)
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    mail = _ingest(client, h, box, fake, "r1", f"Rate limit {RUN}")
    fake.forbidden_reason = "userRateLimitExceeded"
    _ok(client.patch(f"{M}/messages/{mail['id']}", json={"status": "done"}, headers=h))
    after = _message(client, h, mail["id"])
    assert after["archive_status"] == "failed"
    assert "userRateLimitExceeded" in (after["archive_error"] or "")
    boxes = {b["address"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}
    assert boxes[address]["archive_scope_missing"] is False

    # The 15 minute beat job picks the failed mail up again.
    fake.forbidden_reason = None
    state = client.app.state  # type: ignore[attr-defined]
    counts = asyncio.run(archive_retry_once(state.settings, world.tenant_a))
    assert counts["archived"] >= 1
    assert fake.archived == ["r1"]
    assert _message(client, h, mail["id"])["archive_status"] == "archived"


def test_retry_job_catches_up_done_mails_without_record(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    fake: ArchiveFake,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mails set to done before this change (no archive_status) and a lost queue job
    (pending) are archived by the beat job; a mail older than 30 days is left alone."""
    from mhvp.communication.tasks import archive_retry_once

    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    box = _mailbox(client, h, f"retry{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    legacy = _ingest(client, h, box, fake, "l1", f"Alt erledigt {RUN}")
    lost = _ingest(client, h, box, fake, "l2", f"Verlorener Auftrag {RUN}")
    old = _ingest(client, h, box, fake, "l3", f"Zu alt {RUN}")
    _sql(
        world,
        database,
        redis_url,
        "UPDATE message SET status = 'done', archive_status = NULL WHERE id = :id RETURNING 1",
        {"id": legacy["id"]},
    )
    _sql(
        world,
        database,
        redis_url,
        "UPDATE message SET archive_status = 'pending' WHERE id = :id RETURNING 1",
        {"id": lost["id"]},
    )
    _sql(
        world,
        database,
        redis_url,
        "UPDATE message SET status = 'done', created_at = now() - interval '40 days' "
        "WHERE id = :id RETURNING 1",
        {"id": old["id"]},
    )
    state = client.app.state  # type: ignore[attr-defined]
    counts = asyncio.run(archive_retry_once(state.settings, world.tenant_a))
    assert counts["archived"] >= 2
    assert {"l1", "l2"} <= set(fake.archived)
    assert "l3" not in fake.archived
    assert _message(client, h, legacy["id"])["archive_status"] == "archived"
    assert _message(client, h, lost["id"])["archive_status"] == "archived"
    # Manual catch up for the old one works and is idempotent afterwards.
    assert (
        _ok(client.post(f"{M}/messages/{old['id']}/archive", headers=h))["result"]["archived"] == 1
    )
    assert (
        _ok(client.post(f"{M}/messages/{old['id']}/archive", headers=h))["result"]["archived"] == 0
    )


def test_archive_endpoint_rejects_outbound_and_foreign_access(
    client: TestClient, world: World, fake: ArchiveFake, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inline(client, monkeypatch)
    h = bearer(login(client, world, "gaadmin"))
    clerk = bearer(login(client, world, "gaclerk"))
    box = _mailbox(client, h, f"auth{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    mail = _ingest(client, h, box, fake, "a1", f"Zugriff {RUN}")
    # Non default mailbox without a grant: not visible, hence 404 (no inference).
    assert client.post(f"{M}/messages/{mail['id']}/archive", headers=clerk).status_code == 404
    draft = _ok(client.post(f"{M}/messages/{mail['id']}/reply-draft", headers=h), 201)
    assert client.post(f"{M}/messages/{draft['id']}/archive", headers=h).status_code == 422
    assert fake.archived == []
