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
        self.strict_history = True

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


# Rückkanal (M20-08) ---------------------------------------------------------------------------


def _states(
    case: Case, rows: dict[str, dict[str, Any]]
) -> dict[str, tuple[str | None, str | None, str]]:
    return {
        name: (m["gmail_state"], m["gmail_state_by"], m["status"])
        for name, m in ((n, case.message(r["id"])) for n, r in rows.items())
    }


def _effects(case: Case, message_id: str) -> list[str]:
    return [
        str(e["payload"]["effect"])
        for e in case.events(message_id)
        if e["type"] == "message.gmail_state_changed"
    ]


def test_personal_archive_notes_and_collective_archive_completes(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    """E01 then E03 in mode done: the personal copy only records, the collective copy
    completes the group; no ticket close while gmail_done_closes_ticket is off."""
    case = Case(client, settings, world, fake, "e1")
    case.mode("done")
    rows = case.mail(f"Sammelpostfach entscheidet {RUN}")
    lead, copy = rows["timo"], rows["info"]
    ticket_id = str(lead["ticket_id"])
    assert lead["gmail_sync"]["state"] == "synchron"

    fake.archive(case.tokens["timo"], lead["gmail_message_id"])
    case.sync("timo")
    states = _states(case, rows)
    assert states["timo"] == ("archived", "user", "assigned")
    assert states["info"] == ("inbox", "user", "assigned")
    detail = case.message(lead["id"])
    assert detail["gmail_sync"]["state"] == "abweichend"
    copies = {c["mailbox_address"]: c for c in detail["gmail_sync"]["copies"]}
    assert copies[case.address("info")]["authoritative"] is True
    assert copies[case.address("timo")]["authoritative"] is False
    assert _effects(case, lead["id"]) == ["ignored_personal"]
    assert case.ticket_events(ticket_id, "auto_close_skipped") == []

    fake.archive(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    states = _states(case, rows)
    assert states["timo"] == ("archived", "user", "done")
    assert states["info"] == ("archived", "user", "done")
    detail = case.message(lead["id"])
    assert detail["done_source"] == "gmail"
    assert detail["gmail_sync"]["state"] == "synchron"
    # The personal copy was already archived by the user: no own archiving for it.
    assert fake.account(case.tokens["timo"]).modify_bodies == []
    assert len(case.domain_events("message.completed", [lead["id"]])) == 1
    assert case.ticket(ticket_id)["status"] != "done"
    skipped = case.ticket_events(ticket_id, "auto_close_skipped")
    assert [e["data"]["reason"] for e in skipped] == ["ticket_close_disabled"]
    assert "done" in _effects(case, copy["id"])


def test_collective_first_archives_personal_copy_and_echo_is_own_action(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "e2")
    case.mode("done")
    rows = case.mail(f"Echo eigene Aktion {RUN}")
    lead, copy = rows["timo"], rows["info"]
    fake.archive(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    after = case.message(lead["id"])
    assert after["status"] == "done"
    # The personal copy left the inbox through the platform (inline job) with the history id.
    timo = fake.account(case.tokens["timo"])
    assert timo.modify_bodies == [
        (lead["gmail_message_id"], {"removeLabelIds": ["INBOX", "UNREAD"]})
    ]
    assert after["archive_status"] == "archived"
    assert after["gmail_expected_state"] == "archived"
    assert after["gmail_state"] == "archived"
    assert after["gmail_state_by"] == "platform"
    # The echo of that modify call in the next run is an own action, nothing changes.
    case.sync("timo")
    assert "ignored_own" in _effects(case, lead["id"])
    assert len(case.domain_events("message.completed", [lead["id"]])) == 1
    assert case.message(lead["id"])["gmail_sync"]["state"] == "synchron"


def test_without_collective_mailbox_every_personal_copy_must_be_archived(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    """E04 and E05: no collective mailbox, so both personal copies decide together."""
    case = Case(client, settings, world, fake, "e4", collective=(), personal=("timo", "kollege"))
    case.mode("done")
    rows = case.mail(f"Ohne Sammelpostfach {RUN}")
    fake.archive(case.tokens["timo"], rows["timo"]["gmail_message_id"])
    case.sync("timo")
    assert case.message(rows["timo"]["id"])["status"] != "done"
    assert _effects(case, rows["timo"]["id"]) == ["noted"]
    fake.archive(case.tokens["kollege"], rows["kollege"]["gmail_message_id"])
    case.sync("kollege")
    assert case.message(rows["timo"]["id"])["status"] == "done"
    assert case.message(rows["kollege"]["id"])["status"] == "done"

    single = case.mail(f"Einzige Kopie {RUN}", boxes=("timo",))
    fake.archive(case.tokens["timo"], single["timo"]["gmail_message_id"])
    case.sync("timo")
    assert case.message(single["timo"]["id"])["done_source"] == "gmail"


def test_two_collective_mailboxes_both_must_archive(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "e3", collective=("info", "post"))
    case.mode("done")
    rows = case.mail(f"Zwei Sammelpostfaecher {RUN}")
    fake.archive(case.tokens["info"], rows["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(rows["timo"]["id"])["status"] != "done"
    fake.archive(case.tokens["post"], rows["post"]["gmail_message_id"])
    case.sync("post")
    assert case.message(rows["timo"]["id"])["status"] == "done"
    # The personal copy left the inbox with the group (own action).
    assert [m for m, _ in fake.account(case.tokens["timo"]).modify_bodies] == [
        rows["timo"]["gmail_message_id"]
    ]


def test_record_only_and_off_never_change_status(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "ro")
    case.mode("record_only")
    rows = case.mail(f"Nur vermerken {RUN}")
    fake.archive(case.tokens["info"], rows["info"]["gmail_message_id"])
    case.sync("info")
    after = case.message(rows["info"]["id"])
    assert (after["gmail_state"], after["gmail_state_by"], after["status"]) == (
        "archived",
        "user",
        "assigned",
    )
    assert _effects(case, rows["info"]["id"]) == ["noted"]
    assert case.message(rows["timo"]["id"])["gmail_sync"]["state"] == "abweichend"

    case.mode("off")
    fake.archive(case.tokens["timo"], rows["timo"]["gmail_message_id"])
    result = case.sync("timo")
    assert result["state_events"] == 0
    assert case.message(rows["timo"]["id"])["gmail_state"] == "inbox"
    assert case.message(rows["timo"]["id"])["gmail_sync"]["state"] == "aus"
    # Switching on later does not apply the old event (cursor moved on).
    case.mode("done")
    case.sync("timo")
    assert case.message(rows["timo"]["id"])["status"] == "assigned"

    # Mode done without the confirmed spike is refused.
    _sql(
        settings,
        world.tenant_a,
        "UPDATE tenant_settings SET gmail_spike_confirmed_at = NULL, "
        "gmail_done_sync_mode = 'record_only' RETURNING 1",
    )
    refused = client.patch(SETTINGS, json={"gmail_done_sync_mode": "done"}, headers=case.h)
    assert refused.status_code == 422
    assert refused.json()["code"] == "MHVP-COMM-0007"


def test_mailbox_switch_off_only_records(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "sw")
    case.mode("done")
    box = case.boxes["info"]
    _ok(
        client.patch(
            f"{M}/mailboxes/{box['id']}", json={"sync_back_enabled": False}, headers=case.h
        )
    )
    rows = case.mail(f"Rueckkanal aus {RUN}")
    fake.archive(case.tokens["info"], rows["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(rows["info"]["id"])["gmail_state"] == "archived"
    assert case.message(rows["timo"]["id"])["status"] == "assigned"
    assert _effects(case, rows["info"]["id"]) == ["skipped_mailbox"]
    boxes = {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=case.h))}
    assert boxes[box["id"]]["sync_back_enabled"] is False
    assert boxes[box["id"]]["gmail_last_sync_at"]


def test_trash_spam_and_permanent_delete(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "tr")
    case.mode("done")
    # Trash in one entry completes the group (done_on_trash default true).
    one = case.mail(f"Papierkorb eins {RUN}")
    fake.trash(case.tokens["info"], one["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(one["info"]["id"])["gmail_state"] == "trashed"
    assert case.message(one["timo"]["id"])["done_source"] == "gmail"
    # Trash in two entries within one run: one folded event.
    two = case.mail(f"Papierkorb zwei {RUN}")
    fake.trash(case.tokens["info"], two["info"]["gmail_message_id"], two_entries=True)
    case.sync("info")
    events = [
        e["payload"]
        for e in case.events(two["info"]["id"])
        if e["type"] == "message.gmail_state_changed"
    ]
    assert len(events) == 1
    assert (events[0]["to"], events[0]["coalesced"]) == ("trashed", 2)
    assert case.message(two["timo"]["id"])["status"] == "done"
    # Untrash without INBOX: archived, nothing reopens; with INBOX: reopened.
    fake.untrash(case.tokens["info"], two["info"]["gmail_message_id"], inbox=False)
    case.sync("info")
    assert case.message(two["info"]["id"])["gmail_state"] == "archived"
    assert case.message(two["timo"]["id"])["status"] == "done"
    fake.restore(case.tokens["info"], two["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(two["timo"]["id"])["status"] == "assigned"
    assert case.message(two["timo"]["id"])["done_source"] is None

    # done_on_trash off: trash only notes.
    case.patch_settings(gmail_done_on_trash=False)
    three = case.mail(f"Papierkorb drei {RUN}")
    fake.trash(case.tokens["info"], three["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(three["timo"]["id"])["status"] == "assigned"
    assert _effects(case, three["info"]["id"]) == ["noted"]
    case.patch_settings(gmail_done_on_trash=True)

    # Spam never decides.
    four = case.mail(f"Spam {RUN}")
    fake.spam(case.tokens["info"], four["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(four["info"]["id"])["gmail_state"] == "spam"
    assert case.message(four["timo"]["id"])["status"] == "assigned"
    assert _effects(case, four["info"]["id"]) == ["ignored_spam"]

    # Permanent delete from the inbox: mail done, ticket never closed, comment K3, row kept.
    case.patch_settings(gmail_done_closes_ticket=True)
    five = case.mail(f"Geloescht {RUN}")
    fake.delete(case.tokens["info"], five["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(five["info"]["id"])["gmail_state"] == "deleted"
    assert case.message(five["timo"]["id"])["status"] == "done"
    ticket_id = str(five["timo"]["ticket_id"])
    assert case.ticket(ticket_id)["status"] != "done"
    assert any(c["body"].startswith("Hinweis: Die Mail") for c in case.comments(ticket_id))
    assert case.message(five["info"]["id"])["document_id"]
    # Delete of an already trashed copy only changes the state.
    fake.delete(case.tokens["info"], one["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(one["info"]["id"])["gmail_state"] == "deleted"
    assert len(case.domain_events("message.completed", [one["timo"]["id"]])) == 1


def test_ticket_auto_close_and_refusals(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "tc")
    case.mode("done", gmail_done_closes_ticket=True)
    rows = case.mail(f"Ticket schliessen {RUN}", thread="th-close")
    lead, copy = rows["timo"], rows["info"]
    ticket_id = str(lead["ticket_id"])
    # A sent reply in the Gmail thread without a stored row: K1 carries the hint.
    fake.add(
        case.tokens["info"],
        "sent-reply",
        _eml("info@example.com", "AW", f"<sent-{RUN}@x>"),
        thread="th-close",
        labels=("SENT",),
    )
    fake.archive(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    ticket = case.ticket(ticket_id)
    assert ticket["status"] == "done"
    assert ticket["resolved_by"] is None
    status_events = case.ticket_events(ticket_id, "status")
    last = status_events[-1]
    assert last["user_id"] is None
    assert last["data"]["source"] == "gmail"
    assert last["data"]["auto_close"] is True
    assert last["data"]["mailbox_address"] == case.address("info")
    comments = case.comments(ticket_id)
    k1 = next(c for c in comments if c["body"].startswith("Automatisch erledigt"))
    assert k1["internal"] is True
    assert k1["author_user_id"] is None
    assert "1 gesendete Antworten" in k1["body"]
    events = case.domain_events("ticket.status_changed", [ticket_id])
    assert events[-1]["source"] == "gmail"

    # Refusals: assigned ticket with notification, waiting status, open mails, keep open label.
    assigned = case.mail(f"Zugewiesen {RUN}")
    t_assigned = str(assigned["timo"]["ticket_id"])
    _ok(
        client.patch(
            f"{T}/{t_assigned}",
            json={"assignee_user_id": str(world.users["gsclerk"])},
            headers=case.h,
        )
    )
    fake.archive(case.tokens["info"], assigned["info"]["gmail_message_id"])
    case.sync("info")
    assert case.ticket(t_assigned)["status"] != "done"
    assert case.message(assigned["timo"]["id"])["status"] == "done"
    reasons = [e["data"]["reason"] for e in case.ticket_events(t_assigned, "auto_close_skipped")]
    assert reasons == ["assigned_in_progress"]
    notified = _sql(
        settings,
        world.tenant_a,
        "SELECT kind FROM notification WHERE user_id = :u AND entity_id = :t",
        {"u": world.users["gsclerk"], "t": t_assigned},
    )
    assert ("ticket.auto_close_blocked",) in [tuple(r) for r in notified]

    waiting = case.mail(f"Wartet {RUN}")
    t_waiting = str(waiting["timo"]["ticket_id"])
    _ok(client.patch(f"{T}/{t_waiting}", json={"status": "in_progress"}, headers=case.h))
    _ok(client.patch(f"{T}/{t_waiting}", json={"status": "waiting"}, headers=case.h))
    fake.archive(case.tokens["info"], waiting["info"]["gmail_message_id"])
    case.sync("info")
    assert [e["data"]["reason"] for e in case.ticket_events(t_waiting, "auto_close_skipped")] == [
        "status_waiting"
    ]

    first = case.mail(f"Zwei Mails {RUN}", thread="th-two")
    t_two = str(first["timo"]["ticket_id"])
    second = case.mail(f"Zwei Mails Nachtrag {RUN}", thread="th-two")
    assert second["timo"]["ticket_id"] == first["timo"]["ticket_id"]
    fake.archive(case.tokens["info"], first["info"]["gmail_message_id"])
    case.sync("info")
    assert [e["data"]["reason"] for e in case.ticket_events(t_two, "auto_close_skipped")] == [
        "open_mails"
    ]
    # Both remaining copies archived in one run: exactly one status event, no refusal.
    fake.archive(case.tokens["info"], second["info"]["gmail_message_id"])
    case.sync("info")
    assert case.ticket(t_two)["status"] == "done"
    assert len(case.ticket_events(t_two, "auto_close_skipped")) == 1

    case.patch_settings(gmail_keep_open_labels=["Warten"])
    labelled = case.mail(f"Arbeitslabel {RUN}")
    t_label = str(labelled["timo"]["ticket_id"])
    fake.add_label(case.tokens["info"], labelled["info"]["gmail_message_id"], "Warten")
    fake.archive(case.tokens["info"], labelled["info"]["gmail_message_id"])
    case.sync("info")
    after = case.message(labelled["info"]["id"])
    assert after["gmail_state"] == "archived"
    assert after["gmail_keep_open_label"] == "Warten"
    assert case.message(labelled["timo"]["id"])["status"] == "assigned"
    assert case.ticket(t_label)["status"] != "done"
    assert _effects(case, labelled["info"]["id"]) == ["ignored_keep_open"]


def test_reopen_from_gmail_inside_and_outside_window(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "rw")
    case.mode("done", gmail_done_closes_ticket=True)
    rows = case.mail(f"Wieder oeffnen {RUN}")
    lead, copy = rows["timo"], rows["info"]
    ticket_id = str(lead["ticket_id"])
    fake.archive(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    assert case.ticket(ticket_id)["status"] == "done"
    assert case.message(lead["id"])["archive_status"] == "archived"

    fake.restore(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    after = case.message(lead["id"])
    assert (
        after["status"],
        after["done_source"],
        after["archive_status"],
        after["archived_at"],
    ) == ("assigned", None, None, None)
    assert after["gmail_reopened_at"]
    reopened = case.domain_events("message.reopened", [lead["id"]])
    assert reopened[-1]["previous_status"] == "done"
    assert reopened[-1]["previous_done_source"] == "gmail"
    assert reopened[-1]["previous_archive_status"] == "archived"
    assert case.ticket(ticket_id)["status"] == "in_progress"
    ev = case.ticket_events(ticket_id, "reopened")[-1]
    assert ev["data"]["reason"] == "gmail_unarchive"
    assert any(c["body"].startswith("Automatisch wieder ge") for c in case.comments(ticket_id))
    # The personal copy is still archived (platform never writes back on Gmail events).
    assert case.message(lead["id"])["gmail_state"] == "archived"
    assert fake.account(case.tokens["timo"]).untrashed == []
    # Done again archives again; the reopened ticket is in progress and therefore protected
    # (assigned_in_progress) until gmail_close_assigned_tickets is on.
    fake.archive(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    assert case.message(lead["id"])["status"] == "done"
    assert case.ticket(ticket_id)["status"] == "in_progress"
    assert case.ticket_events(ticket_id, "auto_close_skipped")[-1]["data"]["reason"] == (
        "assigned_in_progress"
    )

    # Outside the window: ticket stays closed, mail visible in the default list.
    _ok(
        client.patch(
            f"{T}/{ticket_id}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=case.h,
        )
    )
    _sql(
        settings,
        world.tenant_a,
        "UPDATE ticket SET resolved_at = now() - interval '40 days' WHERE id = :t RETURNING 1",
        {"t": ticket_id},
    )
    fake.restore(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    assert case.ticket(ticket_id)["status"] == "done"
    skipped = case.ticket_events(ticket_id, "reopen_skipped")[-1]
    assert skipped["data"]["reason"] == "window_elapsed"
    assert any(c["body"].startswith("Hinweis: Die Mail") for c in case.comments(ticket_id))
    listed = {m["id"] for m in _ok(client.get(f"{M}/messages", headers=case.h))}
    assert lead["id"] in listed
    assert case.message(lead["id"])["status"] == "assigned"

    # Reopen switch off: only a note.
    case.patch_settings(gmail_reopen_on_unarchive=False)
    fake.archive(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    fake.restore(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    assert case.message(lead["id"])["status"] == "done"
    # A restore of a personal copy never reopens (E11).
    case.patch_settings(gmail_reopen_on_unarchive=True)
    fake.archive(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    fake.restore(case.tokens["timo"], lead["gmail_message_id"])
    case.sync("timo")
    assert case.message(lead["id"])["status"] == "done"
    assert _effects(case, lead["id"])[-1] == "ignored_personal"


def test_settle_period_waits_for_a_stable_state(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    from mhvp.communication.gmail_done import settle_due
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    def run_settle() -> dict[str, int]:
        async def run() -> dict[str, int]:
            engine = create_app_engine(settings)
            try:
                factory = create_session_factory(engine)
                async with tenant_transaction(factory, world.tenant_a) as s:
                    return await settle_due(s, settings)
            finally:
                await engine.dispose()

        return asyncio.run(run())

    case = Case(client, settings, world, fake, "st")
    case.mode("done")
    case.patch_settings(gmail_settle_seconds=600)
    rows = case.mail(f"Beruhigung {RUN}")
    fake.archive(case.tokens["info"], rows["info"]["gmail_message_id"])
    case.sync("info")
    lead = case.message(rows["timo"]["id"])
    assert lead["status"] == "assigned"
    assert lead["gmail_settle_until"]
    assert lead["gmail_sync"]["state"] == "ausstehend"
    assert _effects(case, rows["info"]["id"]) == ["settle_pending"]
    assert run_settle()["done"] == 0
    assert case.message(rows["timo"]["id"])["status"] == "assigned"
    _sql(
        settings,
        world.tenant_a,
        "UPDATE message SET gmail_settle_until = now() - interval '1 second' "
        "WHERE id = :id RETURNING 1",
        {"id": lead["id"]},
    )
    assert run_settle()["done"] == 1
    assert case.message(rows["timo"]["id"])["done_source"] == "gmail"

    # Undo before the period ends: nothing closes.
    other = case.mail(f"Beruhigung Undo {RUN}")
    fake.archive(case.tokens["info"], other["info"]["gmail_message_id"])
    case.sync("info")
    fake.restore(case.tokens["info"], other["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(other["timo"]["id"])["gmail_settle_until"] is None
    _sql(
        settings,
        world.tenant_a,
        "UPDATE message SET gmail_settle_until = now() - interval '1 second' "
        "WHERE id = :id RETURNING 1",
        {"id": other["timo"]["id"]},
    )
    counts = run_settle()
    assert (counts["done"], counts["noted"]) == (0, 1)
    assert case.message(other["timo"]["id"])["status"] == "assigned"


def test_replay_is_ignored_and_push_uses_the_same_path(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    from mhvp.communication.tasks import gmail_push_sync_once

    case = Case(client, settings, world, fake, "rp")
    case.mode("done")
    rows = case.mail(f"Replay {RUN}")
    before = _sql(
        settings,
        world.tenant_a,
        "SELECT gmail_history_id FROM mailbox WHERE id = :id",
        {"id": case.boxes["info"]["id"]},
    )[0][0]
    fake.archive(case.tokens["info"], rows["info"]["gmail_message_id"])
    # Push job (labelsRemoved only) walks the same path as the beat sync.
    totals = asyncio.run(gmail_push_sync_once(settings, case.address("info"), "1"))
    assert totals["mailboxes"] == 1
    assert case.message(rows["timo"]["id"])["status"] == "done"
    # Cursor set back: the same entry again is a replay.
    _sql(
        settings,
        world.tenant_a,
        "UPDATE mailbox SET gmail_history_id = :h WHERE id = :id RETURNING 1",
        {"h": before, "id": case.boxes["info"]["id"]},
    )
    case.sync("info")
    assert _effects(case, rows["info"]["id"]) == ["done", "ignored_replay"]
    assert len(case.domain_events("message.completed", [rows["timo"]["id"]])) == 1
    # Budget: noise entries do not consume the batch; a label event behind them is applied.
    state = client.app.state  # type: ignore[attr-defined]
    state.settings = state.settings.model_copy(update={"gmail_sync_batch": 2})
    try:
        noisy = case.mail(f"Rauschen {RUN}")
        for _ in range(5):
            fake.noise(case.tokens["info"], noisy["info"]["gmail_message_id"])
        fake.archive(case.tokens["info"], noisy["info"]["gmail_message_id"])
        result = case.sync("info")
        assert result["remaining"] == 0
        assert case.message(noisy["timo"]["id"])["status"] == "done"
    finally:
        state.settings = state.settings.model_copy(update={"gmail_sync_batch": 50})


def test_ingest_initial_state_and_late_copy_of_done_group(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "in")
    case.mode("done")
    # A mail that a filter moved past the inbox: never fetched (no INBOX in messagesAdded).
    fake.add(
        case.tokens["info"],
        "filtered",
        _eml("x@example.com", "Gefiltert", f"<f-{RUN}@x>"),
        labels=("Ablage",),
    )
    assert case.sync("info")["created"] == 0
    # Late copy of a done group leaves the inbox with the group.
    rows = case.mail(f"Verspaetete Kopie {RUN}", boxes=("timo",))
    fake.archive(case.tokens["timo"], rows["timo"]["gmail_message_id"])
    case.sync("timo")
    assert case.message(rows["timo"]["id"])["status"] == "done"
    gid = f"late{RUN}"
    fake.add(
        case.tokens["info"],
        gid,
        _eml(
            f"in{RUN}@example.com",
            f"Verspaetete Kopie {RUN}",
            f"<in-1-{RUN}@x>",
            to=case.address("info"),
        ),
    )
    case.sync("info")
    late = case.row(gid)
    assert late["duplicate_of_id"] == rows["timo"]["id"]
    assert late["status"] == "done"
    assert late["done_source"] == "gmail"
    assert late["archive_status"] == "archived"
    assert [m for m, _ in fake.account(case.tokens["info"]).modify_bodies] == [gid]


def test_reconcile_after_expired_history_and_preview(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "rc")
    case.mode("done")
    case.patch_settings(gmail_reconcile_grace_seconds=60)
    rows = case.mail(f"Abgleich {RUN}")
    gone = case.mail(f"Abgleich geloescht {RUN}")
    back = case.mail(f"Abgleich zurueck {RUN}")
    info = fake.account(case.tokens["info"])
    # Changes without history entries: archived in Gmail, deleted in Gmail, and a copy the
    # platform archived that came back into the inbox.
    info.labels[rows["info"]["gmail_message_id"]].discard("INBOX")
    del info.labels[gone["info"]["gmail_message_id"]]
    _ok(client.patch(f"{M}/messages/{back['timo']['id']}", json={"status": "done"}, headers=case.h))
    info.labels[back["info"]["gmail_message_id"]].add("INBOX")
    _sql(
        settings,
        world.tenant_a,
        "UPDATE message SET created_at = now() - interval '10 minutes', "
        "gmail_state_at = now() - interval '10 minutes', archive_attempted_at = NULL "
        "WHERE mailbox_id = :b RETURNING 1",
        {"b": case.boxes["info"]["id"]},
    )
    reader = bearer(login(client, world, "gsreader"))
    assert (
        client.post(
            f"{M}/mailboxes/{case.boxes['info']['id']}/reconcile-state",
            json={"preview": True},
            headers=reader,
        ).status_code
        == 403
    )
    preview = _ok(
        client.post(
            f"{M}/mailboxes/{case.boxes['info']['id']}/reconcile-state",
            json={"preview": True},
            headers=case.h,
        )
    )
    assert (preview["would_archive"], preview["would_delete"], preview["would_reopen"]) == (
        1,
        1,
        1,
    )
    assert {s["action"] for s in preview["samples"]} == {"archived", "deleted", "returned"}
    assert case.message(rows["timo"]["id"])["status"] == "assigned"  # preview wrote nothing

    info.expire_history = True
    calls_before = len(info.calls)
    case.sync("info")
    info.expire_history = False
    calls = info.calls[calls_before:]
    # Stamp (profile) before the listing of the reconcile.
    profile = next(i for i, c in enumerate(calls) if c.startswith("GET") and "/profile" in c)
    listing = next(i for i, c in enumerate(calls) if "labelIds=INBOX" in c)
    assert profile < listing
    assert case.message(rows["timo"]["id"])["done_source"] == "reconcile"
    assert case.message(rows["info"]["id"])["gmail_state_by"] == "reconcile"
    assert case.message(gone["info"]["id"])["gmail_state"] == "deleted"
    assert case.message(back["timo"]["id"])["status"] == "assigned"
    boxes = {b["id"]: b for b in _ok(client.get(f"{M}/mailboxes", headers=case.h))}
    box = boxes[case.boxes["info"]["id"]]
    assert box["gmail_state_reconcile_status"] == "done"
    assert box["gmail_state_reconciled_at"]
    assert box["gmail_state_reconcile_counts"]["archived"] == 1


def test_restore_inbox_and_revert_decision(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "rs")
    case.mode("done", gmail_done_closes_ticket=True)
    rows = case.mail(f"Zuruecklegen {RUN}")
    lead, copy = rows["timo"], rows["info"]
    ticket_id = str(lead["ticket_id"])
    fake.trash(case.tokens["info"], copy["gmail_message_id"])
    case.sync("info")
    assert case.ticket(ticket_id)["status"] == "done"
    # Switch off: endpoint refuses, PATCH back to assigned touches Gmail not at all.
    refused = client.post(f"{M}/messages/{lead['id']}/restore-inbox", headers=case.h)
    assert refused.status_code == 422
    assert refused.json()["code"] == "MHVP-COMM-0006"
    _ok(client.patch(f"{M}/messages/{lead['id']}", json={"status": "assigned"}, headers=case.h))
    assert case.message(copy["id"])["status"] == "assigned"
    assert fake.account(case.tokens["info"]).untrashed == []
    # Switch on: revert restores the copies (untrash for the trashed one, INBOX for both).
    _ok(client.patch(f"{M}/messages/{lead['id']}", json={"status": "done"}, headers=case.h))
    case.patch_settings(gmail_restore_inbox_on_reopen=True)
    result = _ok(
        client.post(f"{M}/messages/{lead['id']}/revert-gmail-decision", json={}, headers=case.h)
    )
    assert result == {"message_reopened": True, "ticket_reopened": True}
    assert case.ticket(ticket_id)["status"] == "in_progress"
    assert case.ticket_events(ticket_id, "reverted")[-1]["data"]["message_id"] == lead["id"]
    assert fake.account(case.tokens["info"]).untrashed == [copy["gmail_message_id"]]
    assert (copy["gmail_message_id"], {"addLabelIds": ["INBOX"]}) in fake.account(
        case.tokens["info"]
    ).modify_bodies
    after = case.message(copy["id"])
    assert (after["archive_status"], after["gmail_state"], after["gmail_expected_state"]) == (
        "restored",
        "inbox",
        "inbox",
    )
    # The echo of the restore is an own action.
    case.sync("info")
    assert _effects(case, copy["id"])[-1] == "ignored_own"
    assert case.message(lead["id"])["status"] == "assigned"
    # Nothing automatic to revert: 422.
    _ok(client.patch(f"{M}/messages/{lead['id']}", json={"status": "done"}, headers=case.h))
    again = client.post(f"{M}/messages/{lead['id']}/revert-gmail-decision", json={}, headers=case.h)
    assert again.status_code == 422
    assert again.json()["code"] == "MHVP-COMM-0009"


def test_tenant_separation_and_copy_visibility(
    client: TestClient, settings: Any, world: World, fake: StateFake, reset_settings: None
) -> None:
    case = Case(client, settings, world, fake, "ts")
    case.mode("done")
    rows = case.mail(f"Rechte {RUN}")
    lead = rows["timo"]
    # Same Gmail id in a mailbox of another tenant: untouched by the event of tenant A.
    hb = bearer(login(client, world, "gsbadmin"))
    other = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": case.address("info"), "kind": "gmail", "secret": f"rt-b-{RUN}"},
            headers=hb,
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{other['id']}", json={"enabled": True}, headers=hb))
    _ok(client.post(f"{M}/mailboxes/{other['id']}/sync", headers=hb))
    fake.add(
        f"rt-b-{RUN}",
        rows["info"]["gmail_message_id"],
        _eml(f"b{RUN}@example.com", f"Mandant B {RUN}", f"<b-{RUN}@x>"),
    )
    _ok(client.post(f"{M}/mailboxes/{other['id']}/sync", headers=hb))
    fake.archive(case.tokens["info"], rows["info"]["gmail_message_id"])
    case.sync("info")
    assert case.message(lead["id"])["status"] == "done"
    b_rows = _ok(client.get(f"{M}/messages", headers=hb))
    b_row = next(m for m in b_rows if m["subject"] == f"Mandant B {RUN}")
    assert b_row["status"] != "done"
    assert b_row["gmail_state"] == "inbox"
    # A member without access to timo@ sees the collective copy in detail and timo@ hidden.
    clerk = bearer(login(client, world, "gsclerk"))
    _ok(
        client.patch(
            f"{M}/mailboxes/{case.boxes['info']['id']}", json={"is_default": True}, headers=case.h
        )
    )
    seen = _ok(client.get(f"{M}/messages/{rows['info']['id']}", headers=clerk))
    copies = {c["mailbox_address"]: c for c in seen["gmail_sync"]["copies"]}
    assert copies[case.address("info")]["visible"] is True
    assert copies[case.address("timo")] == {
        "mailbox_address": case.address("timo"),
        "visible": False,
    }
    assert client.get(f"{M}/messages/{lead['id']}/sync-events", headers=clerk).status_code == 404
    assert client.get(f"{M}/messages/{lead['id']}/sync-events", headers=hb).status_code == 404
    assert len(case.events(lead["id"])) >= 1


def test_gmail_tenant_settings_validation_and_event(
    client: TestClient, settings: Any, world: World, reset_settings: None
) -> None:
    admin = bearer(login(client, world, "gsadmin"))
    reader = bearer(login(client, world, "gsreader"))
    current = _ok(client.get(SETTINGS, headers=admin))
    assert current["gmail_done_sync_mode"] == "record_only"
    assert current["gmail_settle_seconds"] == 600
    assert current["gmail_reconcile_grace_seconds"] == 300
    assert current["gmail_keep_open_labels"] == []
    for bad in (
        {"gmail_settle_seconds": 3601},
        {"gmail_reconcile_grace_seconds": 59},
        {"gmail_keep_open_labels": ["INBOX"]},
        {"gmail_keep_open_labels": ["CATEGORY_UPDATES"]},
        {"gmail_keep_open_labels": [f"L{i}" for i in range(21)]},
        {"gmail_done_sync_mode": "maybe"},
    ):
        assert client.patch(SETTINGS, json=bad, headers=admin).status_code == 422, bad
    assert (
        client.patch(SETTINGS, json={"gmail_settle_seconds": 0}, headers=reader).status_code == 403
    )
    out = _ok(
        client.patch(
            SETTINGS,
            json={"gmail_settle_seconds": 0, "gmail_keep_open_labels": ["Warten", "Rückfrage"]},
            headers=admin,
        )
    )
    assert out["gmail_settle_seconds"] == 0
    assert out["gmail_keep_open_labels"] == ["Warten", "Rückfrage"]
    changes = _sql(
        settings,
        world.tenant_a,
        "SELECT a.changes FROM audit_log a JOIN domain_event e ON e.id = a.event_id "
        "WHERE e.type = 'tenant_settings.updated' ORDER BY e.occurred_at DESC, e.id DESC LIMIT 1",
    )[0][0]
    assert changes["gmail_settle_seconds"] == {"old": 600, "new": 0}
    assert changes["gmail_keep_open_labels"]["new"] == ["Warten", "Rückfrage"]
