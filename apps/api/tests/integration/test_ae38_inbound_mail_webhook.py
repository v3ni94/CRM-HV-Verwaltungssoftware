"""AE38 / M20-04: inbound webhook for classified mails of the legacy mail program.

Expected values by hand (docs/integrations/inbound-mail-webhook.md):

* A valid delivery (API key with ``mail_inbound:ingest`` plus HMAC of the source) stores exactly
  one message and one ticket and answers 201; the same ``event_id`` with the same content again
  answers 200 with the stored ids and creates nothing (replay counter 1); another content under
  the same ``event_id`` is 409.
* A wrong, missing, stale (more than 300 s old or ahead) or non ASCII signature is 401, also
  with a valid key; a signature of another source of the same tenant is 401 as well.
* A key without the right is 403, a signed in user instead of a key is 403, an unknown or
  revoked key is 401.
* The source of another tenant is 404 for the key of this tenant and the other way round.
* A body above 1 MiB is 413, invalid JSON, a non object, unknown fields, a naive timestamp and
  a missing sender are 422.
* A reply (``in_reply_to`` of a delivered mail) joins the ticket of the first mail; a mail with
  a known Message-ID under a new ``event_id`` links the stored message instead of a second one.
"""

import asyncio
import json
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.communication import inbound_webhook as hook
from mhvp.core.auth.permissions import MAIL_INBOUND_INGEST
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
S = "/api/v1/mail/inbound/sources"
SLUG_A = f"ae38a-{RUN}"
SLUG_B = f"ae38b-{RUN}"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG_A, name=f"AE38 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=SLUG_B, name=f"AE38 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae38admin", a, "tenant_admin"),
            ("ae38reader", a, "read_only"),
            ("ae38other", b, "tenant_admin"),
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
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


class Setup:
    """Sources and keys of both tenants, created once per module."""

    def __init__(self) -> None:
        self.admin: dict[str, str] = {}
        self.other: dict[str, str] = {}
        self.reader: dict[str, str] = {}
        self.source_id = ""
        self.secret = ""
        self.second_id = ""
        self.second_secret = ""
        self.other_source_id = ""
        self.other_secret = ""
        self.key = ""
        self.key_id = ""
        self.other_key = ""
        self.weak_key = ""


def _create_key(client: TestClient, headers: dict[str, str], scopes: list[str], name: str) -> Any:
    return _ok(
        client.post(
            "/api/v1/tenant/api-keys", json={"name": name, "scopes": scopes}, headers=headers
        ),
        201,
    )


@pytest.fixture(scope="module")
def setup(database: Database, redis_url: str, world: World) -> Setup:
    state = Setup()
    with TestClient(create_app(base_settings(database, redis_url))) as client:
        state.admin = bearer(login(client, world, "ae38admin"))
        state.other = bearer(login(client, world, "ae38other"))
        state.reader = bearer(login(client, world, "ae38reader"))
        first = _ok(client.post(S, json={"name": f"Quelle {RUN}"}, headers=state.admin), 201)
        state.source_id, state.secret = first["id"], first["secret"]
        second = _ok(client.post(S, json={"name": f"Zweite {RUN}"}, headers=state.admin), 201)
        state.second_id, state.second_secret = second["id"], second["secret"]
        foreign = _ok(client.post(S, json={"name": f"Quelle B {RUN}"}, headers=state.other), 201)
        state.other_source_id, state.other_secret = foreign["id"], foreign["secret"]
        made = _create_key(client, state.admin, [MAIL_INBOUND_INGEST], f"ae38-{RUN}")
        state.key, state.key_id = made["key"], made["id"]
        state.other_key = _create_key(client, state.other, [MAIL_INBOUND_INGEST], f"ae38b-{RUN}")[
            "key"
        ]
        state.weak_key = _create_key(client, state.admin, ["communication:read"], f"weak-{RUN}")[
            "key"
        ]
    return state


def _mail_doc(event_id: str, **mail: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "message_id": f"<{event_id}@legacy.example.org>",
        "from_address": f"Mieter-{event_id}@Example.org",
        "to": ["info@example.com"],
        "subject": f"Heizung ausgefallen {event_id}",
        "body_text": "Guten Tag, die Heizung in der Wohnung ist seit gestern ausgefallen.",
        "received_at": "2026-09-30T08:15:00+02:00",
    }
    base.update(mail)
    return {
        "event_id": event_id,
        "source_ref": "legacy-4711",
        "classified_at": "2026-09-30T08:16:00+02:00",
        "mail": base,
        "classification": {
            "category": "Heizung",
            "urgency": "urgent",
            "summary": "Heizungsausfall gemeldet",
            "confidence": 0.9,
            "labels": ["technik"],
        },
    }


def _deliver(
    client: TestClient,
    key: str,
    source_id: str,
    document: Any,
    secret: str,
    *,
    timestamp: int | None = None,
    signature: str | bytes | None = None,
    raw: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    body = raw if raw is not None else json.dumps(document).encode()
    sig = (
        signature
        if signature is not None
        else hook.sign_delivery(secret, body, timestamp=timestamp)
    )
    headers = {"X-API-Key": key, "Content-Type": "application/json", hook.SIGNATURE_HEADER: sig}
    headers.update(extra_headers or {})
    return client.post(f"{S}/{source_id}/classified-mails", content=body, headers=headers)


def _event_id(label: str) -> str:
    return f"{label}-{RUN}-{uuid.uuid4().hex[:6]}"


# --- administration -------------------------------------------------------------------------


def test_source_administration(client: TestClient, world: World, setup: Setup) -> None:
    name = f"Verwaltung {RUN}"
    created = _ok(
        client.post(S, json={"name": name, "auto_ticket": False}, headers=setup.admin), 201
    )
    assert created["secret"]
    assert len(created["secret"]) >= 32
    assert created["active"] is True
    assert created["auto_ticket"] is False
    assert (
        created["delivery_path"] == f"/api/v1/mail/inbound/sources/{created['id']}/classified-mails"
    )
    listed = _ok(client.get(S, headers=setup.admin))
    assert name in [row["name"] for row in listed]
    assert all("secret" not in row for row in listed)  # the secret is shown once
    # unique name, validation, unknown field, permission, tenant separation
    assert client.post(S, json={"name": name}, headers=setup.admin).status_code == 409
    assert client.post(S, json={"name": ""}, headers=setup.admin).status_code == 422
    assert client.post(S, json={"name": "   "}, headers=setup.admin).status_code == 422
    assert client.post(S, json={"name": "x", "bogus": 1}, headers=setup.admin).status_code == 422
    assert (
        client.post(S, json={"name": "y", "mailbox_id": str(uuid.uuid4())}, headers=setup.admin)
    ).status_code == 404
    assert client.post(S, json={"name": "z"}, headers=setup.reader).status_code == 403
    assert client.get(S, headers=setup.reader).status_code == 200
    assert client.get(f"{S}?bogus=1", headers=setup.admin).status_code == 422
    assert client.get(S).status_code == 401
    assert name not in [row["name"] for row in _ok(client.get(S, headers=setup.other))]
    assert (
        client.patch(
            f"{S}/{created['id']}", json={"active": False}, headers=setup.other
        ).status_code
        == 404
    )
    assert client.post(f"{S}/{created['id']}/rotate-secret", headers=setup.other).status_code == 404
    assert client.get(f"{S}/{created['id']}/events", headers=setup.other).status_code == 404
    # change and switch off
    patched = _ok(
        client.patch(
            f"{S}/{created['id']}",
            json={"name": f"{name} neu", "active": False},
            headers=setup.admin,
        )
    )
    assert patched["name"] == f"{name} neu"
    assert patched["active"] is False
    assert (
        client.patch(f"{S}/{created['id']}", json={"name": f"Zweite {RUN}"}, headers=setup.admin)
    ).status_code == 409
    assert (
        client.patch(
            f"{S}/{created['id']}", json={"name": None, "bogus": 1}, headers=setup.admin
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{S}/{created['id']}", json={"active": True}, headers=setup.reader
        ).status_code
        == 403
    )


# --- delivery -------------------------------------------------------------------------------


def test_delivery_creates_message_and_ticket_then_replays(
    client: TestClient, world: World, setup: Setup
) -> None:
    event_id = _event_id("first")
    document = _mail_doc(event_id)
    first = _deliver(client, setup.key, setup.source_id, document, setup.secret)
    body = _ok(first, 201)
    assert body["replayed"] is False
    assert body["message_created"] is True
    assert body["event_id"] == event_id
    assert body["message_id"]
    assert body["ticket_id"]

    message = _ok(client.get(f"/api/v1/mail/messages/{body['message_id']}", headers=setup.admin))
    assert message["from_address"] == f"mieter-{event_id}@example.org"
    assert message["subject"] == f"Heizung ausgefallen {event_id}"
    assert message["ticket_id"] == body["ticket_id"]
    classification = message["classification"]
    assert classification["external"]["category"] == "Heizung"
    assert classification["external"]["urgency"] == "urgent"
    assert classification["external"]["labels"] == ["technik"]
    assert classification["source"]["kind"] == "inbound_webhook"
    assert classification["source"]["source_id"] == setup.source_id
    assert classification["source"]["event_id"] == event_id
    # the platform keeps its own classification (rules), the external one is only a proposal
    assert classification["method"] == "rules"
    ticket = _ok(client.get(f"/api/v1/tickets/{body['ticket_id']}", headers=setup.admin))
    assert ticket["title"] == f"Heizung ausgefallen {event_id}"

    # the same delivery again (fresh timestamp, same content): stored result, nothing new
    again = _deliver(client, setup.key, setup.source_id, document, setup.secret)
    replay = _ok(again, 200)
    assert replay["replayed"] is True
    assert (replay["message_id"], replay["ticket_id"]) == (body["message_id"], body["ticket_id"])
    # key order and whitespace do not make it another delivery
    reordered = json.dumps(dict(reversed(list(document.items()))), indent=2).encode()
    assert (
        _deliver(client, setup.key, setup.source_id, None, setup.secret, raw=reordered).status_code
        == 200
    )

    events = _ok(client.get(f"{S}/{setup.source_id}/events", headers=setup.admin))
    mine = [e for e in events if e["event_id"] == event_id]
    assert len(mine) == 1
    assert mine[0]["replay_count"] == 2
    assert mine[0]["message_created"] is True
    assert mine[0]["message_id"] == body["message_id"]
    source = next(r for r in _ok(client.get(S, headers=setup.admin)) if r["id"] == setup.source_id)
    assert source["last_received_at"] is not None


def test_same_event_id_with_other_content_is_conflict(
    client: TestClient, world: World, setup: Setup
) -> None:
    event_id = _event_id("conflict")
    assert (
        _deliver(client, setup.key, setup.source_id, _mail_doc(event_id), setup.secret).status_code
        == 201
    )
    changed = _mail_doc(event_id, subject="Etwas ganz anderes")
    conflict = _deliver(client, setup.key, setup.source_id, changed, setup.secret)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "MHVP-HOOK-0005"
    # the same event_id in another source of the tenant is a different delivery
    other = _deliver(client, setup.key, setup.second_id, _mail_doc(event_id), setup.second_secret)
    assert other.status_code == 201, other.text


def test_wrong_missing_and_stale_signatures_are_unauthorized(
    client: TestClient, world: World, setup: Setup
) -> None:
    document = _mail_doc(_event_id("sig"))
    raw = json.dumps(document).encode()
    now = int(time.time())
    good = hook.sign_delivery(setup.secret, raw, timestamp=now)
    cases: dict[str, str | bytes] = {
        "wrong secret": hook.sign_delivery("not-the-secret", raw, timestamp=now),
        "other source": hook.sign_delivery(setup.second_secret, raw, timestamp=now),
        "tampered body": hook.sign_delivery(setup.secret, raw + b" ", timestamp=now),
        "stale": hook.sign_delivery(setup.secret, raw, timestamp=now - 3600),
        "ahead": hook.sign_delivery(setup.secret, raw, timestamp=now + 3600),
        "garbage": "t=abc,v1=00",
        "no timestamp": good.split(",", 1)[1],
        "non ascii": "t=1,v1=äöü".encode("latin-1"),
        "empty": "",
        "oversized": "x" * 5000,
    }
    for label, signature in cases.items():
        response = _deliver(
            client, setup.key, setup.source_id, None, "", raw=raw, signature=signature
        )
        assert response.status_code == 401, (label, response.text)
        assert response.json()["code"] == "MHVP-HOOK-0002", label
    # no header at all
    response = client.post(
        f"{S}/{setup.source_id}/classified-mails",
        content=raw,
        headers={"X-API-Key": setup.key, "Content-Type": "application/json"},
    )
    assert response.status_code == 401
    # a signature from just inside the window is accepted
    edge = _deliver(
        client,
        setup.key,
        setup.source_id,
        None,
        "",
        raw=raw,
        signature=hook.sign_delivery(setup.secret, raw, timestamp=now - 240),
    )
    assert edge.status_code == 201, edge.text
    # nothing was stored by the rejected attempts
    events = _ok(client.get(f"{S}/{setup.source_id}/events?limit=200", headers=setup.admin))
    assert [e["event_id"] for e in events].count(document["event_id"]) == 1


def test_key_rights_and_tenant_binding(client: TestClient, world: World, setup: Setup) -> None:
    document = _mail_doc(_event_id("auth"))
    # no key, forged key, key without the right, user token instead of key
    raw = json.dumps(document).encode()
    path = f"{S}/{setup.source_id}/classified-mails"
    signed = {hook.SIGNATURE_HEADER: hook.sign_delivery(setup.secret, raw)}
    assert client.post(path, content=raw, headers=signed).status_code == 401
    forged = setup.key[:-4] + "0000"
    assert _deliver(client, forged, setup.source_id, document, setup.secret).status_code == 401
    assert (
        _deliver(client, setup.weak_key, setup.source_id, document, setup.secret).status_code == 403
    )
    as_user = client.post(path, content=raw, headers={**signed, **setup.admin})
    assert as_user.status_code == 403, as_user.text
    # tenant binding: sources of the other tenant do not exist for this key and vice versa
    assert (
        _deliver(client, setup.key, setup.other_source_id, document, setup.other_secret).status_code
        == 404
    )
    assert (
        _deliver(client, setup.other_key, setup.source_id, document, setup.secret).status_code
        == 404
    )
    assert _deliver(client, setup.key, str(uuid.uuid4()), document, setup.secret).status_code == 404
    # the other tenant delivers into its own source
    own = _deliver(client, setup.other_key, setup.other_source_id, document, setup.other_secret)
    assert own.status_code == 201, own.text
    # the mail of tenant B is invisible for tenant A
    assert (
        client.get(
            f"/api/v1/mail/messages/{own.json()['message_id']}", headers=setup.admin
        ).status_code
        == 404
    )


def test_revoked_key_is_unauthorized(client: TestClient, world: World, setup: Setup) -> None:
    made = _create_key(client, setup.admin, [MAIL_INBOUND_INGEST], f"revoke-{RUN}")
    document = _mail_doc(_event_id("revoke"))
    assert _deliver(client, made["key"], setup.source_id, document, setup.secret).status_code == 201
    assert (
        client.delete(f"/api/v1/tenant/api-keys/{made['id']}", headers=setup.admin).status_code
        == 204
    )
    fresh = _mail_doc(_event_id("revoke2"))
    assert _deliver(client, made["key"], setup.source_id, fresh, setup.secret).status_code == 401


def test_size_limit_and_validation(client: TestClient, world: World, setup: Setup) -> None:
    big = _mail_doc(_event_id("big"), body_text="x" * 90000)
    big["padding"] = "y" * (hook.MAX_BODY_BYTES + 10)
    response = _deliver(client, setup.key, setup.source_id, big, setup.secret)
    assert response.status_code == 413, response.status_code
    assert response.json()["code"] == "MHVP-HOOK-0004"

    def post(raw: bytes) -> Any:
        return _deliver(client, setup.key, setup.source_id, None, setup.secret, raw=raw)

    assert post(b"not json").status_code == 422
    assert post(b"[1, 2]").status_code == 422
    assert post(b"[" * 5000 + b"]" * 5000).status_code == 422
    assert post(json.dumps({"event_id": "x"}).encode()).status_code == 422
    unknown = _mail_doc(_event_id("unk"))
    unknown["extra"] = 1
    assert post(json.dumps(unknown).encode()).status_code == 422
    naive = _mail_doc(_event_id("naive"), received_at="2026-09-30T08:15:00")
    assert post(json.dumps(naive).encode()).status_code == 422
    no_sender = _mail_doc(_event_id("nosender"))
    del no_sender["mail"]["from_address"]
    assert post(json.dumps(no_sender).encode()).status_code == 422
    bad_address = _mail_doc(_event_id("badaddr"), from_address="kein-at-zeichen")
    assert post(json.dumps(bad_address).encode()).status_code == 422
    bad_event = _mail_doc("has space")
    assert post(json.dumps(bad_event).encode()).status_code == 422
    bad_urgency = _mail_doc(_event_id("urg"))
    bad_urgency["classification"]["urgency"] = "sofort"
    assert post(json.dumps(bad_urgency).encode()).status_code == 422
    error = post(json.dumps(no_sender).encode()).json()
    assert error["status"] == 422
    assert any(item["field"] == "mail.from_address" for item in error["errors"])
    # nothing of the rejected deliveries was kept as an event
    kept = _ok(client.get(f"{S}/{setup.source_id}/events?limit=200", headers=setup.admin))
    assert not {e["event_id"] for e in kept} & {
        no_sender["event_id"],
        naive["event_id"],
        bad_address["event_id"],
        unknown["event_id"],
    }


def test_inactive_source_and_rotated_secret(client: TestClient, world: World, setup: Setup) -> None:
    created = _ok(client.post(S, json={"name": f"Rotation {RUN}"}, headers=setup.admin), 201)
    sid, secret = created["id"], created["secret"]
    document = _mail_doc(_event_id("rot"))
    assert _deliver(client, setup.key, sid, document, secret).status_code == 201
    _ok(client.patch(f"{S}/{sid}", json={"active": False}, headers=setup.admin))
    off = _deliver(client, setup.key, sid, _mail_doc(_event_id("off")), secret)
    assert off.status_code == 409
    assert off.json()["code"] == "MHVP-HOOK-0006"
    # without the secret an inactive source reveals nothing: signature first
    probe = _deliver(client, setup.key, sid, _mail_doc(_event_id("probe")), "wrong-secret")
    assert probe.status_code == 401
    _ok(client.patch(f"{S}/{sid}", json={"active": True}, headers=setup.admin))
    rotated = _ok(client.post(f"{S}/{sid}/rotate-secret", headers=setup.admin))
    assert rotated["secret"] != secret
    assert rotated["secret_rotated_at"] is not None
    stale = _deliver(client, setup.key, sid, _mail_doc(_event_id("old")), secret)
    assert stale.status_code == 401
    fresh = _deliver(client, setup.key, sid, _mail_doc(_event_id("new")), rotated["secret"])
    assert fresh.status_code == 201, fresh.text


def test_reply_joins_ticket_and_known_message_is_linked(
    client: TestClient, world: World, setup: Setup
) -> None:
    first_id = _event_id("thread")
    first = _ok(
        _deliver(client, setup.key, setup.source_id, _mail_doc(first_id), setup.secret), 201
    )
    reply_doc = _mail_doc(
        _event_id("reply"),
        in_reply_to=f"<{first_id}@legacy.example.org>",
        subject=f"AW: Heizung ausgefallen {first_id}",
        from_address=f"mieter-{first_id}@example.org",
    )
    reply = _ok(_deliver(client, setup.key, setup.source_id, reply_doc, setup.secret), 201)
    assert reply["message_created"] is True
    assert reply["message_id"] != first["message_id"]
    assert reply["ticket_id"] == first["ticket_id"]

    # the same Message-ID under a new event_id: the stored message is linked, not duplicated
    again = _mail_doc(_event_id("known"), message_id=f"<{first_id}@legacy.example.org>")
    again["mail"]["from_address"] = f"mieter-{first_id}@example.org"
    again["mail"]["subject"] = f"Heizung ausgefallen {first_id}"
    again["mail"]["body_text"] = (
        "Guten Tag, die Heizung in der Wohnung ist seit gestern ausgefallen."
    )
    linked = _ok(_deliver(client, setup.key, setup.source_id, again, setup.secret), 201)
    assert linked["message_created"] is False
    assert linked["message_id"] == first["message_id"]


def test_auto_ticket_switch(client: TestClient, world: World, setup: Setup) -> None:
    created = _ok(
        client.post(
            S, json={"name": f"Ohne Ticket {RUN}", "auto_ticket": False}, headers=setup.admin
        ),
        201,
    )
    out = _ok(
        _deliver(client, setup.key, created["id"], _mail_doc(_event_id("nt")), created["secret"]),
        201,
    )
    assert out["message_created"] is True
    assert out["ticket_id"] is None
    message = _ok(client.get(f"/api/v1/mail/messages/{out['message_id']}", headers=setup.admin))
    assert message["ticket_id"] is None


def test_parallel_identical_deliveries_store_one_mail(
    client: TestClient, world: World, setup: Setup
) -> None:
    document = _mail_doc(_event_id("race"))
    raw = json.dumps(document).encode()

    def send(_: int) -> Any:
        return _deliver(client, setup.key, setup.source_id, None, setup.secret, raw=raw)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, range(4)))
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 200, 200, 201], codes
    assert len({r.json()["message_id"] for r in responses}) == 1
    events = _ok(client.get(f"{S}/{setup.source_id}/events?limit=200", headers=setup.admin))
    mine = [e for e in events if e["event_id"] == document["event_id"]]
    assert len(mine) == 1
    assert mine[0]["replay_count"] == 3
