"""M23-02 Google Calendar: merged /workspace/calendar (internal entries plus the default
mailbox's and the user's own assigned mailbox's Google events, each tagged with source),
create/patch/delete proxied to a fake Google Calendar (httpx.MockTransport), a user without an
assigned mailbox sees only the default calendar, tenant separation, cache invalidation on write
via the manual refresh endpoint."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from mhvp.communication import gcal
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
W = "/api/v1/workspace"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"gcal-{RUN}", name=f"GCal {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"gcal2-{RUN}", name=f"GCal2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m23admin", a, "tenant_admin"),
            ("m23colleague", a, "standard"),
            ("m23other", b, "tenant_admin"),
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


class FakeGCal:
    """One event store per calendar id."""

    def __init__(self) -> None:
        self.events: dict[str, dict[str, dict[str, Any]]] = {}
        self._seq = 0
        self._etag_seq = 0
        self.send_updates_seen: list[str] = []

    def _next_etag(self) -> str:
        self._etag_seq += 1
        return f"etag-{self._etag_seq}"

    def add(self, calendar_id: str, event_id: str, summary: str, day: str) -> None:
        self.events.setdefault(calendar_id, {})[event_id] = {
            "id": event_id,
            "summary": summary,
            "start": {"date": day},
            "end": {"date": day},
            "etag": self._next_etag(),
        }

    def touch_externally(self, calendar_id: str, event_id: str) -> None:
        """Simulate a change made directly on Google's side (new etag, same id)."""
        self.events[calendar_id][event_id]["etag"] = self._next_etag()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        assert request.headers.get("Authorization") == "Bearer t"
        self.send_updates_seen.append(request.url.params.get("sendUpdates", ""))
        parts = path.split("/")
        # .../calendars/{cal}/events[/{event_id}]
        idx = parts.index("calendars")
        calendar_id = parts[idx + 1]
        rest = parts[idx + 3 :]
        store = self.events.setdefault(calendar_id, {})
        if request.method == "GET" and not rest:
            return httpx.Response(200, json={"items": list(store.values())})
        if request.method == "POST":
            self._seq += 1
            body = json.loads(request.content)
            eid = f"created-{self._seq}"
            store[eid] = {"id": eid, "etag": self._next_etag(), **body}
            return httpx.Response(200, json=store[eid])
        event_id = rest[0]
        if request.method == "GET":
            if event_id not in store:
                return httpx.Response(404)
            return httpx.Response(200, json=store[event_id])
        if request.method == "PATCH":
            if event_id not in store:
                return httpx.Response(404)
            body = json.loads(request.content)
            store[event_id].update(body)
            store[event_id]["etag"] = self._next_etag()
            return httpx.Response(200, json=store[event_id])
        if request.method == "DELETE":
            store.pop(event_id, None)
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {path}")


@pytest.fixture
def fake() -> FakeGCal:
    return FakeGCal()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    import asyncio

    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(
    database: Database, redis_url: str, fake: FakeGCal, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from mhvp.main import create_app

    settings = _settings(database, redis_url).model_copy(
        update={"google_client_id": "cid", "google_client_secret": SecretStr("csecret")}
    )
    original = gcal.GCalClient

    def patched(client_id: str, client_secret: str, refresh_token: str, **_: Any) -> Any:
        return original(
            client_id, client_secret, refresh_token, transport=httpx.MockTransport(fake.handler)
        )

    monkeypatch.setattr(gcal, "GCalClient", patched)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _mailbox(client: TestClient, headers: dict[str, str], address: str, calendar_id: str) -> Any:
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": address, "kind": "gmail", "secret": "rt"},
            headers=headers,
        ),
        201,
    )
    return _ok(
        client.patch(
            f"{M}/mailboxes/{box['id']}",
            json={"enabled": True, "calendar_enabled": True, "calendar_id": calendar_id},
            headers=headers,
        )
    )


def test_merged_calendar_authorization_and_tenant_separation(
    client: TestClient, world: World, fake: FakeGCal
) -> None:
    admin = bearer(login(client, world, "m23admin"))
    colleague = bearer(login(client, world, "m23colleague"))
    other_tenant = bearer(login(client, world, "m23other"))

    default_box = _mailbox(client, admin, f"info-cal-{RUN}@example.com", "primary")
    own_box = _mailbox(client, admin, f"own-cal-{RUN}@example.com", f"own-{RUN}")
    _ok(
        client.patch(f"{M}/mailboxes/{default_box['id']}", json={"is_default": True}, headers=admin)
    )
    _ok(
        client.put(
            f"{M}/mailboxes/{own_box['id']}/users",
            json={"user_ids": [str(world.users["m23admin"])]},
            headers=admin,
        )
    )

    today = datetime.now(UTC).date().isoformat()
    fake.add("primary", "d1", f"Standardtermin {RUN}", today)
    fake.add(f"own-{RUN}", "o1", f"Eigener Termin {RUN}", today)

    start, end = today, today

    # Admin has an assigned mailbox: sees both default and own Google events.
    out = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=admin))
    titles = {(i["title"], i["source"]) for i in out["items"]}
    assert (f"Standardtermin {RUN}", "default") in titles
    assert (f"Eigener Termin {RUN}", "own") in titles
    assert {n["source"] for n in out["notices"]} == {"default", "own"}
    assert all(n["connected"] for n in out["notices"])

    # Colleague has no assigned mailbox: sees only the default calendar.
    out2 = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=colleague))
    titles2 = {(i["title"], i["source"]) for i in out2["items"]}
    assert (f"Standardtermin {RUN}", "default") in titles2
    assert not any(t[1] == "own" for t in titles2)
    assert {n["source"] for n in out2["notices"]} == {"default"}

    # Tenant separation: a user of another tenant never sees these mailboxes' events.
    out3 = _ok(
        client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=other_tenant)
    )
    assert out3["notices"] == []
    assert all(i["source"] == "internal" for i in out3["items"])


def test_create_patch_delete_proxy_to_google_and_cache_invalidates(
    client: TestClient, world: World, fake: FakeGCal
) -> None:
    admin = bearer(login(client, world, "m23admin"))
    # Only one default mailbox at a time: clear any default set by an earlier test.
    for box_row in _ok(client.get(f"{M}/mailboxes", headers=admin)):
        if box_row["is_default"]:
            _ok(
                client.patch(
                    f"{M}/mailboxes/{box_row['id']}", json={"is_default": False}, headers=admin
                )
            )
    box = _mailbox(client, admin, f"solo-{RUN}-{uuid.uuid4().hex[:6]}@example.com", "primary")
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"is_default": True}, headers=admin))

    today = datetime.now(UTC).date().isoformat()
    start = end = today
    before = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=admin))
    assert before["items"] == [] or all(i["source"] != "default" for i in before["items"])

    created = _ok(
        client.post(
            f"{W}/calendar",
            json={"title": "Ortstermin", "starts_on": today, "target": "default"},
            headers=admin,
        ),
        201,
    )
    assert created["source"] == "default"
    event_id = created["google_event_id"]

    after = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=admin))
    assert any(i["title"] == "Ortstermin" for i in after["items"])

    patched = _ok(
        client.patch(
            f"{W}/calendar/google/default/{event_id}",
            json={"title": "Ortstermin verschoben"},
            headers=admin,
        )
    )
    assert patched["title"] == "Ortstermin verschoben"

    _ok(client.post(f"{W}/calendar/refresh", headers=admin))
    after_patch = _ok(
        client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=admin)
    )
    assert any(i["title"] == "Ortstermin verschoben" for i in after_patch["items"])

    _ok(client.delete(f"{W}/calendar/google/default/{event_id}", headers=admin), 204)
    after_delete = _ok(
        client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=admin)
    )
    assert not any(i.get("google_event_id") == event_id for i in after_delete["items"])


def _solo_default_mailbox(client: TestClient, admin: dict[str, str]) -> Any:
    for box_row in _ok(client.get(f"{M}/mailboxes", headers=admin)):
        if box_row["is_default"]:
            _ok(
                client.patch(
                    f"{M}/mailboxes/{box_row['id']}", json={"is_default": False}, headers=admin
                )
            )
    box = _mailbox(client, admin, f"invite-{RUN}-{uuid.uuid4().hex[:6]}@example.com", "primary")
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"is_default": True}, headers=admin))
    return box


def test_invitation_only_after_explicit_confirmation(
    client: TestClient, world: World, fake: FakeGCal
) -> None:
    """M23-02 rule 2 / M23-05: attendees are stored but never sent to Google until the staff
    user confirms "Einladung senden"; creation always uses sendUpdates=none."""
    admin = bearer(login(client, world, "m23admin"))
    _solo_default_mailbox(client, admin)
    today = datetime.now(UTC).date().isoformat()

    created = _ok(
        client.post(
            f"{W}/calendar",
            json={
                "title": "Ortstermin mit externem Teilnehmer",
                "starts_on": today,
                "target": "default",
                "attendees": [{"email": "extern@example.com", "name": "Extern"}],
            },
            headers=admin,
        ),
        201,
    )
    event_id = created["google_event_id"]
    # Created without sending attendee notifications.
    assert fake.send_updates_seen[-1] == "none"
    assert created["invite_status"] == "draft"
    # The stored Google event itself carries no attendees yet.
    box_default_cal = "primary"
    assert "attendees" not in fake.events[box_default_cal][event_id]

    # Cannot invite without an explicit confirmation.
    resp = client.post(
        f"{W}/calendar/google/default/{event_id}/invite", json={"confirm": False}, headers=admin
    )
    assert resp.status_code == 422

    invited = _ok(
        client.post(
            f"{W}/calendar/google/default/{event_id}/invite",
            json={"confirm": True},
            headers=admin,
        )
    )
    assert invited["invite_status"] == "invited"
    assert fake.send_updates_seen[-1] == "all"
    assert fake.events[box_default_cal][event_id]["attendees"] == [
        {"email": "extern@example.com", "name": "Extern"}
    ]

    # Cancelling an already-invited appointment notifies attendees (sendUpdates=all).
    _ok(client.delete(f"{W}/calendar/google/default/{event_id}", headers=admin), 204)
    assert fake.send_updates_seen[-1] == "all"


def test_stale_google_event_is_flagged_and_not_overwritten(
    client: TestClient, world: World, fake: FakeGCal
) -> None:
    """M23-02 rule 3: if the event changed on Google's side (etag differs), the CRM shows the
    Google version and marks its own copy stale instead of silently overwriting either side."""
    admin = bearer(login(client, world, "m23admin"))
    _solo_default_mailbox(client, admin)
    today = datetime.now(UTC).date().isoformat()

    created = _ok(
        client.post(
            f"{W}/calendar",
            json={"title": "Telefontermin", "starts_on": today, "target": "default"},
            headers=admin,
        ),
        201,
    )
    event_id = created["google_event_id"]
    assert created["is_stale"] is False

    # Someone changes the event directly in Google Calendar.
    fake.events["primary"][event_id]["summary"] = "Verschoben (extern)"
    fake.touch_externally("primary", event_id)
    _ok(client.post(f"{W}/calendar/refresh", headers=admin))

    out = _ok(client.get(f"{W}/calendar", params={"start": today, "end": today}, headers=admin))
    item = next(i for i in out["items"] if i.get("google_event_id") == event_id)
    assert item["is_stale"] is True
    assert item["title"] == "Verschoben (extern)"  # Google version shown, not overwritten.

    # The CRM refuses to patch a stale link rather than overwriting the external change.
    resp = client.patch(
        f"{W}/calendar/google/default/{event_id}",
        json={"title": "CRM-Version"},
        headers=admin,
    )
    assert resp.status_code == 409
