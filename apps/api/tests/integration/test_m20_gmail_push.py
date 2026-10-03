"""Gmail push, watch renewal, full inbox backfill and "Erledigt archiviert" per mail (operator
26.09.2026) against the fake Gmail API of ``test_m20_gmail`` extended by watch, label total and
paginated listing. Two tenants prove the tenant separation of the address mapping, the
backfill endpoint and the message completion."""

import asyncio
import base64
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.communication import gmail, gmail_push
from mhvp.communication.gmail_push import mailboxes_for_address
from mhvp.communication.tasks import gmail_push_sync_once, gmail_watch_renew_once
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_gmail import FakeGmail, _eml, _ok

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
PUSH = "/api/v1/integrations/gmail/push"
TOKEN = f"push-secret-{RUN}"
TOPIC = "projects/example-project/topics/mhvp-gmail"


class FakePushGmail(FakeGmail):
    """FakeGmail plus ``users.watch``, ``labels.get`` and paginated ``messages.list``."""

    def __init__(self) -> None:
        super().__init__()
        self.watch_calls: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, str]] = []
        self.fail_page_tokens: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/watch"):
            self.watch_calls.append(json.loads(request.content))
            expiration = int((datetime.now(UTC) + timedelta(days=7)).timestamp() * 1000)
            return httpx.Response(
                200, json={"historyId": str(self.history_id), "expiration": expiration}
            )
        if path.endswith("/labels/INBOX"):
            return httpx.Response(200, json={"id": "INBOX", "messagesTotal": len(self.inbox)})
        if path.endswith("/messages") and "q" not in request.url.params:
            params = dict(request.url.params)
            self.list_calls.append(params)
            token = params.get("pageToken")
            if token in self.fail_page_tokens:
                self.fail_page_tokens.discard(token)
                return httpx.Response(500, json={"error": "backend"})
            limit = int(params.get("maxResults", "100"))
            ids = list(reversed(list(self.inbox)))
            start = int(token) if token else 0
            page = ids[start : start + limit]
            body: dict[str, Any] = {"messages": [{"id": m} for m in page]}
            if start + limit < len(ids):
                body["nextPageToken"] = str(start + limit)
            return httpx.Response(200, json=body)
        return super().handler(request)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"gp-a-{RUN}", name=f"Push A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"gp-b-{RUN}", name=f"Push B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("gpadmin", a, "tenant_admin"),
            ("gpread", a, "read_only_master_data"),
            ("gpclerk", a, "standard"),
            ("gpadminb", b, "tenant_admin"),
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
def fake() -> FakePushGmail:
    return FakePushGmail()


@pytest.fixture
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url).model_copy(
        update={
            "google_client_id": "cid",
            "google_client_secret": SecretStr("csecret"),
            "gmail_pubsub_topic": TOPIC,
            "gmail_push_token": SecretStr(TOKEN),
            "ai_inline": True,
        }
    )


@pytest.fixture
def client(
    settings: Any, fake: FakePushGmail, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
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


def _envelope(address: str, history_id: int = 5) -> dict[str, Any]:
    data = base64.b64encode(
        json.dumps({"emailAddress": address, "historyId": history_id}).encode()
    ).decode()
    return {"message": {"data": data, "messageId": "m1"}, "subscription": "s"}


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


def _boxes(client: TestClient, h: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=h))}


def test_push_endpoint_refuses_without_secret_or_oversized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(gmail_push, "enqueue", lambda _s, a, h: calls.append((a, h)))
    body = _envelope(f"secure-{RUN}@example.com")
    assert client.post(PUSH, json=body).status_code == 401
    assert client.post(PUSH, json=body, params={"token": "wrong"}).status_code == 401
    assert client.post(PUSH, json=body, headers={"X-MHVP-Push-Token": "wrong"}).status_code == 401
    big = {"message": {"data": "A" * (gmail_push.MAX_BODY_BYTES + 10)}}
    r = client.post(PUSH, json=big, params={"token": TOKEN})
    assert r.status_code == 413
    # Malformed envelope with the right secret: 422, nothing queued.
    bad = client.post(PUSH, json={"message": {"data": "%%"}}, params={"token": TOKEN})
    assert bad.status_code == 422, bad.text
    assert calls == []
    # Right secret in the header or the query: accepted.
    assert client.post(PUSH, json=body, headers={"X-MHVP-Push-Token": TOKEN}).status_code == 204
    assert calls == [(f"secure-{RUN}@example.com", "5")]
    # With an audience configured, a missing OIDC token is refused before anything is queued.
    state = client.app.state  # type: ignore[attr-defined]
    monkeypatch.setattr(
        state, "settings", state.settings.model_copy(update={"gmail_push_audience": "aud"})
    )
    other = _envelope(f"oidc-{RUN}@example.com")
    assert client.post(PUSH, json=other, params={"token": TOKEN}).status_code == 401
    assert len(calls) == 1


def test_push_burst_enqueues_once_and_unknown_address_has_no_effect(
    client: TestClient, world: World, fake: FakePushGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(gmail_push, "enqueue", lambda _s, a, h: calls.append((a, h)))
    address = f"burst-{RUN}@example.com"
    for history in (10, 11, 12):
        assert (
            client.post(PUSH, json=_envelope(address, history), params={"token": TOKEN}).status_code
            == 204
        )
    assert calls == [(address, "10")]  # the flag collapses the burst
    # The job clears the flag; an unknown address maps to no mailbox and does nothing.
    settings = client.app.state.settings  # type: ignore[attr-defined]
    assert asyncio.run(gmail_push_sync_once(settings, address, "12")) == {
        "mailboxes": 0,
        "created": 0,
        "failed": 0,
    }
    assert (
        client.post(PUSH, json=_envelope(address, 13), params={"token": TOKEN}).status_code == 204
    )
    assert calls[-1] == (address, "13")


def test_push_job_maps_address_per_tenant_and_syncs(
    client: TestClient, world: World, fake: FakePushGmail
) -> None:
    ha = bearer(login(client, world, "gpadmin"))
    hb = bearer(login(client, world, "gpadminb"))
    shared = f"shared-{RUN}@example.com"
    only_b = f"onlyb-{RUN}@example.com"
    box_a = _mailbox(client, ha, shared)
    box_b = _mailbox(client, hb, shared)
    box_b2 = _mailbox(client, hb, only_b)
    settings = client.app.state.settings  # type: ignore[attr-defined]
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        found = asyncio.run(mailboxes_for_address(factory, shared.upper()))
        assert sorted(found) == sorted(
            [(world.tenant_a, uuid.UUID(box_a["id"])), (world.tenant_b, uuid.UUID(box_b["id"]))]
        )
        assert asyncio.run(mailboxes_for_address(factory, only_b)) == [
            (world.tenant_b, uuid.UUID(box_b2["id"]))
        ]
        assert asyncio.run(mailboxes_for_address(factory, f"nobody-{RUN}@example.com")) == []
    finally:
        asyncio.run(engine.dispose())

    fake.add("p1", _eml(f"p{RUN}@example.com", f"Push eins {RUN}", f"<p1-{RUN}@x>"))
    totals = asyncio.run(gmail_push_sync_once(settings, only_b, "1"))
    assert (totals["mailboxes"], totals["created"], totals["failed"]) == (1, 1, 0)
    # Only tenant B's mailbox for that address saw the push and the mail.
    assert _boxes(client, hb)[box_b2["id"]]["last_push_at"] is not None
    assert _boxes(client, hb)[box_b["id"]]["last_push_at"] is None
    assert _boxes(client, ha)[box_a["id"]]["last_push_at"] is None
    assert f"Push eins {RUN}" in {
        m["subject"] for m in _ok(client.get(f"{M}/messages", headers=hb))
    }
    assert f"Push eins {RUN}" not in {
        m["subject"] for m in _ok(client.get(f"{M}/messages", headers=ha))
    }


def test_watch_registered_by_sync_and_renewed_before_expiry(
    client: TestClient, world: World, fake: FakePushGmail
) -> None:
    from mhvp.communication.tasks import gmail_sync_all_once

    h = bearer(login(client, world, "gpadmin"))
    box = _mailbox(client, h, f"watch-{RUN}@example.com")
    settings = client.app.state.settings  # type: ignore[attr-defined]
    before = len(fake.watch_calls)
    asyncio.run(gmail_sync_all_once(settings))
    listed = _boxes(client, h)[box["id"]]
    assert listed["push_watch_expires_at"] is not None
    assert fake.watch_calls[-1]["topicName"] == TOPIC
    registered = len(fake.watch_calls)
    assert registered > before
    expires = datetime.fromisoformat(listed["push_watch_expires_at"])
    # Daily job: not due today, due one day before expiry, and again after expiry.
    assert asyncio.run(gmail_watch_renew_once(settings))["renewed"] == 0
    assert len(fake.watch_calls) == registered
    later = expires - timedelta(hours=20)
    result = asyncio.run(gmail_watch_renew_once(settings, now=later))
    assert result["renewed"] >= 1
    # The job walks every mailbox of the database; stale mailboxes of other test modules with
    # expired fake credentials count as failed there, so only this mailbox is asserted below.
    assert len(fake.watch_calls) > registered
    renewed = _boxes(client, h)[box["id"]]["push_watch_expires_at"]
    assert renewed is not None
    assert renewed != listed["push_watch_expires_at"]
    # Without a topic the job is a no-op.
    off = settings.model_copy(update={"gmail_pubsub_topic": None})
    assert (
        asyncio.run(gmail_watch_renew_once(off, now=expires + timedelta(days=1)))["mailboxes"] == 0
    )


def test_backfill_paginates_deduplicates_and_resumes(
    client: TestClient, world: World, fake: FakePushGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = client.app.state  # type: ignore[attr-defined]
    monkeypatch.setattr(
        state, "settings", state.settings.model_copy(update={"gmail_sync_batch": 2})
    )
    h = bearer(login(client, world, "gpadmin"))
    r = bearer(login(client, world, "gpread"))
    hb = bearer(login(client, world, "gpadminb"))
    for i in range(5):
        fake.add(
            f"bf{i}", _eml(f"bf{i}{RUN}@example.com", f"Backfill {i} {RUN}", f"<bf{i}-{RUN}@x>")
        )
    box = _mailbox(client, h, f"backfill-{RUN}@example.com")
    # The regular first sync is limited to the newest batch (here 2 of 5).
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 2

    # Permission and tenant separation of the endpoint.
    assert client.post(f"{M}/mailboxes/{box['id']}/backfill", headers=r).status_code == 403
    assert client.post(f"{M}/mailboxes/{box['id']}/backfill", headers=hb).status_code == 404

    fake.list_calls.clear()
    started = _ok(client.post(f"{M}/mailboxes/{box['id']}/backfill", headers=h), 202)
    assert started["backfill_status"] == "queued"
    done = _boxes(client, h)[box["id"]]  # ai_inline: the job ran after the commit
    assert (done["backfill_status"], done["backfill_done"], done["backfill_total"]) == (
        "done",
        5,
        5,
    )
    assert done["backfill_started_at"]
    assert done["backfill_finished_at"]
    assert [c.get("pageToken") for c in fake.list_calls] == [None, "2", "4"]
    subjects = {m["subject"] for m in _ok(client.get(f"{M}/messages", headers=h))}
    assert {f"Backfill {i} {RUN}" for i in range(5)} <= subjects
    # Dedup: the two mails of the first sync were not stored twice.
    assert sum(1 for s in subjects if s.startswith("Backfill")) == 5
    assert all(
        m["ticket_id"]
        for m in _ok(client.get(f"{M}/messages", headers=h))
        if m["subject"].startswith("Backfill")
    )

    # Resume after an abort: the second page fails once, the run stops as failed with its
    # page token; starting again continues at that page instead of the beginning.
    fake.add("bf5", _eml(f"bf5{RUN}@example.com", f"Backfill 5 {RUN}", f"<bf5-{RUN}@x>"))
    fake.fail_page_tokens.add("2")
    fake.list_calls.clear()
    _ok(client.post(f"{M}/mailboxes/{box['id']}/backfill", headers=h), 202)
    failed = _boxes(client, h)[box["id"]]
    assert failed["backfill_status"] == "failed"
    assert failed["backfill_done"] == 2
    assert "Vollabruf" in (failed["last_error"] or "")
    fake.list_calls.clear()
    _ok(client.post(f"{M}/mailboxes/{box['id']}/backfill", headers=h), 202)
    resumed = _boxes(client, h)[box["id"]]
    assert (resumed["backfill_status"], resumed["backfill_done"], resumed["backfill_total"]) == (
        "done",
        6,
        6,
    )
    assert [c.get("pageToken") for c in fake.list_calls] == ["2", "4"]
    assert f"Backfill 5 {RUN}" in {
        m["subject"] for m in _ok(client.get(f"{M}/messages", headers=h))
    }
    # A finished backfill starts over; a running one is refused.
    from mhvp.communication.backfill import request_backfill
    from mhvp.communication.models import Mailbox

    running = Mailbox(tenant_id=world.tenant_a, address="x", kind="gmail", enabled=True)
    running.backfill_status = "running"
    assert request_backfill(running) is False


def test_message_done_archives_and_closes_ticket(
    client: TestClient, world: World, fake: FakePushGmail
) -> None:
    h = bearer(login(client, world, "gpadmin"))
    hb = bearer(login(client, world, "gpadminb"))
    box = _mailbox(client, h, f"done-{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
    fake.add("d1", _eml(f"d{RUN}@example.com", f"Erledigt eins {RUN}", f"<d1-{RUN}@x>"))
    fake.add("d2", _eml(f"d{RUN}@example.com", "AW: Erledigt", f"<d2-{RUN}@x>", f"<d1-{RUN}@x>"))
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 2
    msgs = {m["subject"]: m for m in _ok(client.get(f"{M}/messages", headers=h))}
    first, second = msgs[f"Erledigt eins {RUN}"], msgs["AW: Erledigt"]
    assert first["ticket_id"] == second["ticket_id"]
    ticket_id = first["ticket_id"]

    # Tenant separation: the other tenant cannot complete this mail.
    assert (
        client.patch(f"{M}/messages/{first['id']}", json={"status": "done"}, headers=hb).status_code
        == 404
    )

    # First mail done: archived at Gmail, ticket stays open (one inbound mail still open).
    _ok(client.patch(f"{M}/messages/{first['id']}", json={"status": "done"}, headers=h))
    assert fake.archived == ["d1"]
    assert _ok(client.get(f"/api/v1/tickets/{ticket_id}", headers=h))["status"] != "done"

    # Last mail done: ticket closed automatically with resolution and event, remaining mails
    # archived through the ticket closing.
    _ok(client.patch(f"{M}/messages/{second['id']}", json={"status": "done"}, headers=h))
    ticket = _ok(client.get(f"/api/v1/tickets/{ticket_id}", headers=h))
    assert ticket["status"] == "done"
    assert ticket["resolution_kind"] == "auskunft_erteilt"
    assert ticket["resolution_note"] == "Per E-Mail erledigt"
    events = _ok(client.get(f"/api/v1/tickets/{ticket_id}", headers=h))["events"]
    status_events = [e for e in events if e["kind"] == "status" and e["data"].get("to") == "done"]
    assert status_events
    assert status_events[-1]["data"]["auto_close"] is True
    assert status_events[-1]["user_id"] == str(world.users["gpadmin"])
    assert "d2" in fake.archived


def test_message_done_keeps_ticket_open_with_work_order_or_disabled_kind(
    client: TestClient, world: World, fake: FakePushGmail
) -> None:
    h = bearer(login(client, world, "gpadmin"))
    box = _mailbox(client, h, f"open-{RUN}@example.com")
    _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))

    # Open work order on the ticket: the mail is archived, the ticket stays open.
    fake.add("w1", _eml(f"w{RUN}@example.com", f"Auftrag offen {RUN}", f"<w1-{RUN}@x>"))
    assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1
    mail = next(
        m
        for m in _ok(client.get(f"{M}/messages", headers=h))
        if m["subject"] == f"Auftrag offen {RUN}"
    )
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": str(100 + int(RUN[:4], 16) % 900),
                "name": f"Objekt {RUN}",
                "management_type": "rental",
                "street": "Weg",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim",
            },
            headers=h,
        ),
        201,
    )
    provider = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"Dach {RUN}"}, headers=h
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": mail["ticket_id"],
                "property_id": prop["id"],
                "provider_contact_id": provider["id"],
                "description": "Ziegel ersetzen",
            },
            headers=h,
        ),
        201,
    )
    _ok(client.patch(f"{M}/messages/{mail['id']}", json={"status": "done"}, headers=h))
    assert "w1" in fake.archived
    assert _ok(client.get(f"/api/v1/tickets/{mail['ticket_id']}", headers=h))["status"] != "done"

    # Disabled resolution kind: ticket stays open, a hint event is written.
    saved = _ok(
        client.patch(
            "/api/v1/tenant/settings",
            json={"resolution_kinds": {"disabled": ["auskunft_erteilt"], "custom": []}},
            headers=h,
        )
    )
    assert "auskunft_erteilt" in saved["resolution_kinds"]["disabled"]
    try:
        fake.add("k1", _eml(f"k{RUN}@example.com", f"Art aus {RUN}", f"<k1-{RUN}@x>"))
        assert _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))["created"] == 1
        mail = next(
            m
            for m in _ok(client.get(f"{M}/messages", headers=h))
            if m["subject"] == f"Art aus {RUN}"
        )
        _ok(client.patch(f"{M}/messages/{mail['id']}", json={"status": "done"}, headers=h))
        assert (
            _ok(client.get(f"/api/v1/tickets/{mail['ticket_id']}", headers=h))["status"] != "done"
        )
        events = _ok(client.get(f"/api/v1/tickets/{mail['ticket_id']}", headers=h))["events"]
        skipped = [e for e in events if e["kind"] == "auto_close_skipped"]
        assert skipped
        assert skipped[-1]["data"]["reason"] == "resolution_kind_disabled"
    finally:
        _ok(
            client.patch(
                "/api/v1/tenant/settings",
                json={"resolution_kinds": {"disabled": [], "custom": []}},
                headers=h,
            )
        )
