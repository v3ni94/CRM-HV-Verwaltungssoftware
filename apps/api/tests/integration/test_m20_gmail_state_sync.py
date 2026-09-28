"""M20-08 Rückkanal Gmail zu Plattform (operator 28.09.2026): label changes in Gmail
(archive, trash, spam, delete, restore) are read per mailbox copy and, in mode ``done``,
complete the mail group when the authoritative copies (collective mailbox, otherwise every
personal copy) left the inbox; own platform archivings are recognised and never complete or
reopen anything. Fake Gmail per account (keyed by the refresh token of the mailbox) with
labels, history entries of every type, modify, untrash, minimal message and thread reads.

Also the fix 1.42.2: ``done`` applies to every copy of a mail group and hidden copies never
block the automatic ticket close (``open_mails``); ``align-copies`` repairs older rows."""

from __future__ import annotations

import asyncio
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
from sqlalchemy import text

from mhvp.communication import gmail
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
T = "/api/v1/tickets"
SETTINGS = "/api/v1/tenant/settings"
HISTORY_TYPES = {"messageAdded", "labelRemoved", "labelAdded", "messageDeleted"}


def _eml(sender: str, subject: str, msg_id: str, to: str = "info@example.com") -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        to,
        subject,
        msg_id,
    )
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Bitte um Rückmeldung.")
    return bytes(msg)


class Account:
    """Label state and history of one Gmail account."""

    def __init__(self) -> None:
        self.labels: dict[str, set[str]] = {}
        self.raw: dict[str, bytes] = {}
        self.threads: dict[str, str] = {}
        self.history: list[dict[str, Any]] = []
        self.modify_bodies: list[tuple[str, dict[str, Any]]] = []
        self.untrashed: list[str] = []
        self.calls: list[str] = []
        self.history_page_size: int | None = None
        self.fail_history_page: int | None = None
        self.expire_history = False
        self.modify_without_history_id = False


class StateFake:
    """Gmail API of several accounts behind one transport. The access token carries the
    refresh token of the mailbox, so every request is routed to its account."""

    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.history_id = 1000
        self.token_ok = True
        # Set once the client requests every history type (M20-08 back channel).
        self.strict_history = False

    def account(self, token: str) -> Account:
        return self.accounts.setdefault(token, Account())

    def next_id(self) -> int:
        self.history_id += 1
        return self.history_id

    def _entry(self, token: str, **parts: Any) -> int:
        hid = self.next_id()
        self.account(token).history.append({"id": str(hid), **parts})
        return hid

    def add(
        self,
        token: str,
        mid: str,
        raw: bytes,
        thread: str | None = None,
        labels: tuple[str, ...] = ("INBOX", "UNREAD"),
    ) -> int:
        acc = self.account(token)
        acc.raw[mid] = raw
        acc.labels[mid] = set(labels)
        acc.threads[mid] = thread or f"thread-{mid}"
        return self._entry(
            token, messagesAdded=[{"message": {"id": mid, "labelIds": sorted(labels)}}]
        )

    def add_label(self, token: str, mid: str, label: str) -> int:
        self.account(token).labels.setdefault(mid, set()).add(label)
        return self._entry(token, labelsAdded=[{"message": {"id": mid}, "labelIds": [label]}])

    def remove_label(self, token: str, mid: str, label: str) -> int:
        self.account(token).labels.setdefault(mid, set()).discard(label)
        return self._entry(token, labelsRemoved=[{"message": {"id": mid}, "labelIds": [label]}])

    def archive(self, token: str, mid: str) -> int:
        return self.remove_label(token, mid, "INBOX")

    def restore(self, token: str, mid: str) -> int:
        return self.add_label(token, mid, "INBOX")

    def trash(self, token: str, mid: str, *, two_entries: bool = False) -> int:
        acc = self.account(token)
        acc.labels.setdefault(mid, set()).discard("INBOX")
        acc.labels[mid].add("TRASH")
        if two_entries:
            self._entry(token, labelsRemoved=[{"message": {"id": mid}, "labelIds": ["INBOX"]}])
            return self._entry(token, labelsAdded=[{"message": {"id": mid}, "labelIds": ["TRASH"]}])
        return self._entry(
            token,
            labelsRemoved=[{"message": {"id": mid}, "labelIds": ["INBOX"]}],
            labelsAdded=[{"message": {"id": mid}, "labelIds": ["TRASH"]}],
        )

    def untrash(self, token: str, mid: str, *, inbox: bool = True) -> int:
        acc = self.account(token)
        acc.labels.setdefault(mid, set()).discard("TRASH")
        if inbox:
            acc.labels[mid].add("INBOX")
        parts: dict[str, Any] = {"labelsRemoved": [{"message": {"id": mid}, "labelIds": ["TRASH"]}]}
        if inbox:
            parts["labelsAdded"] = [{"message": {"id": mid}, "labelIds": ["INBOX"]}]
        return self._entry(token, **parts)

    def spam(self, token: str, mid: str) -> int:
        acc = self.account(token)
        acc.labels.setdefault(mid, set()).discard("INBOX")
        acc.labels[mid].add("SPAM")
        return self._entry(
            token,
            labelsRemoved=[{"message": {"id": mid}, "labelIds": ["INBOX"]}],
            labelsAdded=[{"message": {"id": mid}, "labelIds": ["SPAM"]}],
        )

    def delete(self, token: str, mid: str) -> int:
        acc = self.account(token)
        acc.labels.pop(mid, None)
        acc.raw.pop(mid, None)
        return self._entry(token, messagesDeleted=[{"message": {"id": mid}}])

    def noise(self, token: str, mid: str, label: str = "UNREAD") -> int:
        return self._entry(token, labelsRemoved=[{"message": {"id": mid}, "labelIds": [label]}])

    # HTTP -------------------------------------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            if not self.token_ok:
                return httpx.Response(400, json={"error": "invalid_grant"})
            refresh = str(httpx.QueryParams(request.content.decode()).get("refresh_token"))
            return httpx.Response(200, json={"access_token": f"at:{refresh}", "expires_in": 3600})
        auth = request.headers.get("Authorization", "")
        assert auth.startswith("Bearer at:"), auth
        acc = self.account(auth[len("Bearer at:") :])
        acc.calls.append(f"{request.method} {path}?{request.url.query.decode()}")
        params = request.url.params
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": str(self.history_id)})
        if path.endswith("/labels/INBOX"):
            total = sum(1 for labels in acc.labels.values() if "INBOX" in labels)
            return httpx.Response(200, json={"messagesTotal": total})
        if path.endswith("/messages") and request.method == "GET":
            if params.get("q"):
                return httpx.Response(200, json={"messages": []})
            ids = [m for m in reversed(list(acc.labels)) if "INBOX" in acc.labels[m]]
            limit = int(params.get("maxResults", "500"))
            start = int(params.get("pageToken", "0"))
            page = ids[start : start + limit]
            body: dict[str, Any] = {"messages": [{"id": m} for m in page]}
            if start + limit < len(ids):
                body["nextPageToken"] = str(start + limit)
            return httpx.Response(200, json=body)
        if path.endswith("/history"):
            if acc.expire_history:
                return httpx.Response(404, json={"error": "expired"})
            if self.strict_history:
                assert set(params.get_list("historyTypes")) == HISTORY_TYPES, params
                assert "labelId" not in params
            since = int(params["startHistoryId"])
            entries = [h for h in acc.history if int(h["id"]) > since]
            size = acc.history_page_size or max(len(entries), 1)
            page_no = int(params.get("pageToken", "0"))
            if acc.fail_history_page is not None and page_no + 1 == acc.fail_history_page:
                return httpx.Response(500, json={"error": "backend"})
            page = entries[page_no * size : (page_no + 1) * size]
            body = {"history": page, "historyId": str(self.history_id)}
            if (page_no + 1) * size < len(entries):
                body["nextPageToken"] = str(page_no + 1)
            return httpx.Response(200, json=body)
        if path.endswith("/modify"):
            mid = path.rsplit("/", 2)[-2]
            if mid not in acc.labels:
                return httpx.Response(404)
            payload = json.loads(request.content)
            acc.modify_bodies.append((mid, payload))
            removed = [lab for lab in payload.get("removeLabelIds", []) if lab in acc.labels[mid]]
            added = [lab for lab in payload.get("addLabelIds", []) if lab not in acc.labels[mid]]
            acc.labels[mid] -= set(removed)
            acc.labels[mid] |= set(added)
            parts: dict[str, Any] = {}
            if removed:
                parts["labelsRemoved"] = [{"message": {"id": mid}, "labelIds": removed}]
            if added:
                parts["labelsAdded"] = [{"message": {"id": mid}, "labelIds": added}]
            hid = self._entry(acc_token(auth), **parts) if parts else self.history_id
            body = {"id": mid, "labelIds": sorted(acc.labels[mid])}
            if not acc.modify_without_history_id:
                body["historyId"] = str(hid)
            return httpx.Response(200, json=body)
        if path.endswith("/untrash"):
            mid = path.rsplit("/", 2)[-2]
            if mid not in acc.labels:
                return httpx.Response(404)
            acc.untrashed.append(mid)
            acc.labels[mid].discard("TRASH")
            hid = self._entry(
                acc_token(auth), labelsRemoved=[{"message": {"id": mid}, "labelIds": ["TRASH"]}]
            )
            return httpx.Response(
                200, json={"id": mid, "labelIds": sorted(acc.labels[mid]), "historyId": str(hid)}
            )
        if "/threads/" in path:
            tid = path.rsplit("/", 1)[-1]
            messages = [
                {"id": m, "labelIds": sorted(acc.labels.get(m, set()))}
                for m, thread in acc.threads.items()
                if thread == tid and m in acc.labels
            ]
            if not messages:
                return httpx.Response(404)
            return httpx.Response(200, json={"id": tid, "messages": messages})
        mid = path.rsplit("/", 1)[-1]
        if mid not in acc.labels:
            return httpx.Response(404)
        if params.get("format") == "minimal":
            return httpx.Response(
                200,
                json={
                    "id": mid,
                    "labelIds": sorted(acc.labels[mid]),
                    "historyId": str(self.history_id),
                },
            )
        raw = base64.urlsafe_b64encode(acc.raw[mid]).decode().rstrip("=")
        return httpx.Response(
            200,
            json={
                "id": mid,
                "threadId": acc.threads[mid],
                "labelIds": sorted(acc.labels[mid]),
                "raw": raw,
            },
        )


def acc_token(auth: str) -> str:
    return auth[len("Bearer at:") :]


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"gs-{RUN}", name=f"Sync {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"gsb-{RUN}", name=f"Sync B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("gsadmin", "tenant_admin", a),
            ("gsclerk", "standard", a),
            ("gsreader", "read_only_master_data", a),
            ("gsbadmin", "tenant_admin", b),
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
def fake() -> StateFake:
    return StateFake()


@pytest.fixture
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url).model_copy(
        update={
            "google_client_id": "cid",
            "google_client_secret": SecretStr("csecret"),
            "ai_inline": True,
        }
    )


@pytest.fixture
def client(settings: Any, fake: StateFake, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _sql(settings: Any, tenant_id: Any, stmt: str, params: dict[str, Any] | None = None) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def run() -> Any:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as s:
                return (await s.execute(text(stmt), params or {})).all()
        finally:
            await engine.dispose()

    return asyncio.run(run())


class Case:
    """Tenant with a collective mailbox ``info`` and a personal mailbox ``timo`` (optionally
    more) and helpers to ingest the same mail into several mailboxes."""

    def __init__(
        self,
        client: TestClient,
        settings: Any,
        world: World,
        fake: StateFake,
        tag: str,
        *,
        collective: tuple[str, ...] = ("info",),
        personal: tuple[str, ...] = ("timo",),
        user: str = "gsadmin",
    ) -> None:
        self.client, self.settings, self.world, self.fake, self.tag = (
            client,
            settings,
            world,
            fake,
            tag,
        )
        self.h = bearer(login(client, world, user))
        self.boxes: dict[str, dict[str, Any]] = {}
        self.tokens: dict[str, str] = {}
        for name in collective + personal:
            token = f"rt-{name}-{tag}-{RUN}"
            box = _ok(
                client.post(
                    f"{M}/mailboxes",
                    json={
                        "address": f"{name}{tag}{RUN}@example.com",
                        "kind": "gmail",
                        "secret": token,
                    },
                    headers=self.h,
                ),
                201,
            )
            box = _ok(
                client.patch(
                    f"{M}/mailboxes/{box['id']}",
                    json={"enabled": True, "is_collective": name in collective},
                    headers=self.h,
                )
            )
            self.boxes[name], self.tokens[name] = box, token
            self.sync(name)  # sets the cursor
        self.counter = 0

    def address(self, name: str) -> str:
        return str(self.boxes[name]["address"])

    def sync(self, name: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            _ok(self.client.post(f"{M}/mailboxes/{self.boxes[name]['id']}/sync", headers=self.h)),
        )

    def sync_all(self) -> None:
        for name in self.boxes:
            self.sync(name)

    def mail(
        self, subject: str, *, boxes: tuple[str, ...] | None = None, thread: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """Adds one mail (same Message-ID) to the given accounts, syncs them in the given
        order and returns the stored row per mailbox name."""
        self.counter += 1
        names = boxes or tuple(self.boxes)
        msg_id = f"<{self.tag}-{self.counter}-{RUN}@x>"
        gids: dict[str, str] = {}
        for name in names:
            gid = f"{self.tag}{self.counter}{name}"
            self.fake.add(
                self.tokens[name],
                gid,
                _eml(f"{self.tag}{RUN}@example.com", subject, msg_id, to=self.address(name)),
                thread=thread,
            )
            gids[name] = gid
        for name in names:
            self.sync(name)
        return {name: self.row(gids[name]) for name in names}

    def row(self, gmail_id: str) -> dict[str, Any]:
        found = _sql(
            self.settings,
            self.world.tenant_a,
            "SELECT id FROM message WHERE gmail_message_id = :g AND direction = 'in'",
            {"g": gmail_id},
        )
        assert len(found) == 1, gmail_id
        return self.message(str(found[0][0]))

    def message(self, message_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any], _ok(self.client.get(f"{M}/messages/{message_id}", headers=self.h))
        )

    def events(self, message_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            _ok(self.client.get(f"{M}/messages/{message_id}/sync-events", headers=self.h)),
        )

    def ticket(self, ticket_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], _ok(self.client.get(f"{T}/{ticket_id}", headers=self.h)))

    def ticket_events(self, ticket_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        rows = _sql(
            self.settings,
            self.world.tenant_a,
            "SELECT kind, data, user_id FROM ticket_event WHERE ticket_id = :t ORDER BY created_at, id",
            {"t": ticket_id},
        )
        out = [{"kind": k, "data": d, "user_id": u} for k, d, u in rows]
        return [e for e in out if kind is None or e["kind"] == kind]

    def comments(self, ticket_id: str) -> list[dict[str, Any]]:
        rows = _sql(
            self.settings,
            self.world.tenant_a,
            "SELECT body, internal, author_user_id FROM ticket_comment WHERE ticket_id = :t "
            "ORDER BY created_at, id",
            {"t": ticket_id},
        )
        return [{"body": b, "internal": i, "author_user_id": a} for b, i, a in rows]

    def domain_events(self, event_type: str, entity_ids: list[str]) -> list[dict[str, Any]]:
        rows = _sql(
            self.settings,
            self.world.tenant_a,
            "SELECT payload FROM domain_event WHERE type = :t AND entity_id::text = ANY(:ids) "
            "ORDER BY occurred_at, id",
            {"t": event_type, "ids": entity_ids},
        )
        return [r[0] for r in rows]

    def patch_settings(self, **fields: Any) -> dict[str, Any]:
        return cast(dict[str, Any], _ok(self.client.patch(SETTINGS, json=fields, headers=self.h)))

    def mode(self, mode: str, **fields: Any) -> None:
        if mode == "done":
            _ok(
                self.client.post(
                    f"{SETTINGS}/gmail-spike-confirm",
                    json={"protocol_ref": "docs/integrations/gmail.md#spike-test"},
                    headers=self.h,
                )
            )
        self.patch_settings(gmail_done_sync_mode=mode, gmail_settle_seconds=0, **fields)


@pytest.fixture
def reset_settings(client: TestClient, world: World) -> Iterator[None]:
    yield
    h = bearer(login(client, world, "gsadmin"))
    client.patch(
        SETTINGS,
        json={
            "gmail_done_sync_mode": "record_only",
            "gmail_done_closes_ticket": False,
            "gmail_done_on_trash": True,
            "gmail_reopen_on_unarchive": True,
            "gmail_restore_inbox_on_reopen": False,
            "gmail_settle_seconds": 600,
            "gmail_reconcile_grace_seconds": 300,
            "gmail_keep_open_labels": [],
            "gmail_close_assigned_tickets": False,
            "ticket_reopen_window_days": 30,
        },
        headers=h,
    )


# Fix 1.42.2: done applies to every copy -------------------------------------------------


def test_done_applies_to_every_copy_and_hidden_copies_never_block_auto_close(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "fx")
    rows = case.mail(f"Kopien erledigt {RUN}")
    lead, copy = rows["timo"], rows["info"]
    assert lead["duplicate_of_id"] is None
    assert copy["duplicate_of_id"] == lead["id"]
    assert lead["ticket_id"] == copy["ticket_id"]
    ticket_id = str(lead["ticket_id"])

    done = _ok(client.patch(f"{M}/messages/{lead['id']}", json={"status": "done"}, headers=case.h))
    assert done["status"] == "done"
    after_copy = case.message(copy["id"])
    assert after_copy["status"] == "done"
    # Both copies leave the inbox (own platform archiving, inline job).
    assert {mid for mid, _ in fake.account(case.tokens["timo"]).modify_bodies} == {
        lead["gmail_message_id"]
    }
    assert {mid for mid, _ in fake.account(case.tokens["info"]).modify_bodies} == {
        copy["gmail_message_id"]
    }
    assert after_copy["archive_status"] == "archived"
    # The hidden copy never counted as an open mail: the ticket closed with the last mail.
    assert case.ticket(ticket_id)["status"] == "done"
    status_events = case.ticket_events(ticket_id, "status")
    assert status_events[-1]["data"].get("auto_close") is True


def test_align_copies_repairs_older_rows_idempotently(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "al")
    rows = case.mail(f"Angleichen {RUN}")
    lead, copy = rows["timo"], rows["info"]
    # Older state: the leading copy is done, the copy stayed assigned (before the fix).
    _sql(
        settings,
        world.tenant_a,
        "UPDATE message SET status = 'done' WHERE id = :id RETURNING id",
        {"id": lead["id"]},
    )
    reader = bearer(login(client, world, "gsreader"))
    assert client.post(f"{M}/maintenance/align-copies", headers=reader).status_code == 403
    first = _ok(client.post(f"{M}/maintenance/align-copies", headers=case.h))
    assert first["changed"] >= 1
    assert case.message(copy["id"])["status"] == "done"
    events = case.domain_events("message.copy_aligned", [copy["id"]])
    assert events == [
        {"previous_status": "assigned", "status": "done", "leading_message_id": lead["id"]}
    ]
    again = _ok(client.post(f"{M}/maintenance/align-copies", headers=case.h))
    assert again["changed"] == 0
    assert len(case.domain_events("message.copy_aligned", [copy["id"]])) == 1
