"""M9 / A39: rule engine stage 2.

Actions ``webhook`` (signed, target check), ``mail_draft`` (draft only, never sent),
``letter_draft`` (document on the letterhead) and ``ai_task`` (queued proposal); trigger
kind ``schedule`` with one run per due moment; webhook secret never returned; permissions and
tenant separation as in stage 1.
"""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.automation.tasks import process_events_once
from mhvp.core.config import Settings
from mhvp.core.webhooks import SIGNATURE_HEADER, verify
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as _base_settings
from tests.integration.test_m6_documents import COMPANY

pytestmark = pytest.mark.integration
A = "/api/v1/automation"
BUCKET = f"mhvp-auto-{RUN}"
SECRET = "webhook-secret-0123456789"


def _settings(database: Database, redis_url: str, **overrides: Any) -> Settings:
    return _base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        **overrides,
    )


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aut2-{RUN}", name=f"Aut2 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aut2b-{RUN}", name=f"Aut2b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("a2admin", "tenant_admin", a),
            ("a2care", "caretaker", a),
            ("a2other", "tenant_admin", b),
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


@pytest.fixture(scope="module")
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


class _Receiver(BaseHTTPRequestHandler):
    """Local webhook target recording body and headers of every POST."""

    calls: ClassVar[list[dict[str, Any]]] = []
    status = 200

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        _Receiver.calls.append({"path": self.path, "body": body, "headers": dict(self.headers)})
        self.send_response(_Receiver.status)
        self.end_headers()

    def log_message(self, *_: Any) -> None:
        return


@pytest.fixture(scope="module")
def receiver() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/hook"
    finally:
        server.shutdown()


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _later(seconds: int = 30) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _contact(client: TestClient, h: dict[str, str], last: str) -> Any:
    return _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "salutation": "Frau",
                "first_name": "Erika",
                "last_name": f"{last}{RUN}",
                "addresses": [
                    {
                        "street": "Rheinpromenade",
                        "house_number": "1",
                        "postal_code": "40789",
                        "city": "Monheim am Rhein",
                    }
                ],
                "emails": [{"email": f"erika.{last.lower()}.{RUN}@example.org"}],
            },
            headers=h,
        ),
        201,
    )


def test_stage_two_actions(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "a2admin"))
    care = bearer(login(client, world, "a2care"))
    other = bearer(login(client, world, "a2other"))
    asyncio.run(process_events_once(settings))  # positions the watermark

    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=admin))
    contact = _contact(client, admin, "Regel")
    reply_tpl = _ok(
        client.post(
            "/api/v1/tickets/reply-templates",
            json={
                "name": f"Eingang {RUN}",
                "subject": "Ihr Anliegen {ticketnummer}",
                "body": "{anrede},\n\nwir haben Ihr Anliegen {tickettitel} aufgenommen.",
            },
            headers=admin,
        ),
        201,
    )
    letter_tpl = next(
        t
        for t in _ok(client.get("/api/v1/document-templates", headers=admin))
        if t["code"] == "free_letter"
    )

    body: dict[str, Any] = {
        "name": f"Stufe 2 {RUN}",
        "trigger_event_type": "ticket.created",
        "conditions": {"field": "entity.category", "op": "eq", "value": "Wasserschaden"},
        "actions": [
            {"type": "webhook", "url": receiver, "secret": SECRET, "extra": {"source": "mhvp"}},
            {"type": "mail_draft", "reply_template_id": reply_tpl["id"]},
            {
                "type": "letter_draft",
                "template_id": letter_tpl["id"],
                "fields": {
                    "betreff": "Eingangsbestätigung {entity.title}",
                    "text": "Wir haben Ihre Meldung erhalten.",
                },
                "reference": "T-{payload.number}",
            },
            {
                "type": "ai_task",
                "task": "summarize",
                "instruction": "Fasse {entity.title} zusammen.",
            },
        ],
    }
    # Validation (422): secret missing, money related AI task, ticket action on a schedule.
    no_secret = {**body, "actions": [{"type": "webhook", "url": receiver}]}
    assert client.post(f"{A}/rules", json=no_secret, headers=admin).status_code == 422
    bad_ai = {
        **body,
        "actions": [{"type": "ai_task", "task": "propose_posting", "instruction": "x"}],
    }
    assert client.post(f"{A}/rules", json=bad_ai, headers=admin).status_code == 422
    bad_schedule = {
        "name": "Plan",
        "trigger_kind": "schedule",
        "schedule": {"frequency": "daily", "time": "07:30"},
        "actions": [{"type": "set_ticket_field", "field": "priority", "value": "high"}],
    }
    assert client.post(f"{A}/rules", json=bad_schedule, headers=admin).status_code == 422
    assert client.post(f"{A}/rules", json=body, headers=care).status_code == 403

    rule = _ok(client.post(f"{A}/rules", json=body, headers=admin), 201)
    assert rule["trigger_kind"] == "event"
    assert rule["actions"][0] == {
        "type": "webhook",
        "url": receiver,
        "extra": {"source": "mhvp"},
        "has_secret": True,
    }
    listed = _ok(client.get(f"{A}/rules", headers=care))
    for exposed in (json.dumps(rule), json.dumps(listed)):
        assert SECRET not in exposed
        assert "secret_enc" not in exposed

    # Dry run: previews for every action, nothing written anywhere.
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={
                "title": "Rohrbruch Bad",
                "category": "Wasserschaden",
                "contact_id": contact["id"],
            },
            headers=admin,
        ),
        201,
    )
    dry = _ok(
        client.post(
            f"{A}/rules/{rule['id']}/test",
            json={"type": "ticket.created", "entity_id": ticket["id"], "payload": {"number": 5}},
            headers=admin,
        )
    )
    assert dry["matched"] is True
    assert [a["type"] for a in dry["actions"]] == [
        "webhook",
        "mail_draft",
        "letter_draft",
        "ai_task",
    ]
    assert dry["actions"][1]["subject"] == f"Ihr Anliegen {ticket['number']}"
    assert dry["actions"][2]["subject"] == "Eingangsbestätigung Rohrbruch Bad"
    assert _Receiver.calls == []
    assert (
        _ok(client.get("/api/v1/mail/messages", params={"ticket_id": ticket["id"]}, headers=admin))
        == []
    )
    assert (
        _ok(client.get("/api/v1/documents", params={"q": "Eingangsbestätigung"}, headers=admin))[
            "total"
        ]
        == 0
    )

    # Real run (the event of the sample ticket is consumed while the rule is still inactive).
    asyncio.run(process_events_once(settings, now=_later()))
    _ok(client.post(f"{A}/rules/{rule['id']}/activate", json={"active": True}, headers=admin))
    live = _ok(
        client.post(
            "/api/v1/tickets",
            json={
                "title": "Rohrbruch Keller",
                "category": "Wasserschaden",
                "contact_id": contact["id"],
            },
            headers=admin,
        ),
        201,
    )
    result = asyncio.run(process_events_once(settings, now=_later()))
    assert result["failed"] == 0
    runs = _ok(client.get(f"{A}/runs", params={"rule_id": rule["id"]}, headers=admin))["items"]
    assert len(runs) == 1, runs
    run = runs[0]
    assert run["status"] == "executed", run
    assert [a["ok"] for a in run["actions"]] == [True, True, True, True]

    # Webhook: one signed call with the rule, the event and the entity.
    assert len(_Receiver.calls) == 1
    call = _Receiver.calls[0]
    assert verify(SECRET, call["body"], call["headers"][SIGNATURE_HEADER], now=int(time.time()))
    assert call["headers"]["X-MHVP-Event"] == "ticket.created"
    assert call["headers"]["X-MHVP-Rule"] == rule["id"]
    sent = json.loads(call["body"])
    assert sent["rule"]["id"] == rule["id"]
    assert sent["event"]["entity_id"] == live["id"]
    assert sent["entity"]["category"] == "Wasserschaden"
    assert sent["source"] == "mhvp"

    # Mail draft: status draft, recipient from the contact, no send, four eyes untouched.
    drafts = _ok(
        client.get("/api/v1/mail/messages", params={"ticket_id": live["id"]}, headers=admin)
    )
    assert len(drafts) == 1
    assert drafts[0]["status"] == "draft"
    assert drafts[0]["direction"] == "out"
    assert drafts[0]["subject"] == f"Ihr Anliegen {live['number']}"
    assert drafts[0]["to_addresses"] == [f"erika.regel.{RUN}@example.org"]
    assert drafts[0]["sent_at"] is None
    assert run["actions"][1]["entity_id"] == drafts[0]["id"]

    # Letter: generated document on the letterhead, linked to contact and ticket, not sent.
    docs = _ok(client.get("/api/v1/documents", params={"q": "Eingangsbestätigung"}, headers=admin))
    assert docs["total"] == 1
    assert docs["items"][0]["title"] == "Eingangsbestätigung Rohrbruch Keller"
    assert run["actions"][2]["entity_id"] == docs["items"][0]["id"]
    document = _ok(client.get(f"/api/v1/documents/{docs['items'][0]['id']}", headers=admin))
    assert document["source"] == "generated"
    assert document["mime_type"] == "application/pdf"
    links = {(link["entity_type"], link["entity_id"]) for link in document["links"]}
    assert ("contact", contact["id"]) in links
    assert ("ticket", live["id"]) in links

    # AI task: a queued run of the gateway (proposal only), nothing decided.
    ai_run = _ok(client.get(f"/api/v1/ai/runs/{run['actions'][3]['entity_id']}", headers=admin))
    assert ai_run["task"] == "summarize"
    assert ai_run["status"] in ("queued", "running", "failed", "blocked")

    # Idempotent: a second pass changes nothing.
    again = asyncio.run(process_events_once(settings, now=_later(60)))
    assert again["runs"] == 0
    assert len(_Receiver.calls) == 1
    assert _ok(client.get(f"{A}/runs", params={"rule_id": rule["id"]}, headers=admin))["total"] == 1

    # Patch without a new secret keeps the stored one; the API still hides it.
    patched = _ok(
        client.patch(
            f"{A}/rules/{rule['id']}",
            json={"actions": [{"type": "webhook", "url": receiver, "extra": {"source": "mhvp2"}}]},
            headers=admin,
        )
    )
    assert patched["actions"] == [
        {"type": "webhook", "url": receiver, "extra": {"source": "mhvp2"}, "has_secret": True}
    ]
    # Switching to another URL without a new secret is refused at save time.
    moved = client.patch(
        f"{A}/rules/{rule['id']}",
        json={"actions": [{"type": "webhook", "url": receiver + "2"}]},
        headers=admin,
    )
    assert moved.status_code == 422, moved.text
    assert "Geheimnis" in moved.json()["detail"]

    # Private targets are refused unless the setting allows them (SSRF guard of section 12).
    _ok(
        client.patch(
            f"{A}/rules/{rule['id']}",
            json={"actions": [{"type": "webhook", "url": receiver, "secret": SECRET}]},
            headers=admin,
        )
    )
    _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Privates Ziel", "category": "Wasserschaden"},
            headers=admin,
        ),
        201,
    )
    strict = _settings(database, redis_url, webhook_allow_private_targets=False)
    asyncio.run(process_events_once(strict, now=_later(120)))
    failed = _ok(
        client.get(f"{A}/runs", params={"rule_id": rule["id"], "status": "failed"}, headers=admin)
    )
    assert failed["total"] == 1
    assert "nicht zulässig" in failed["items"][0]["error"]
    assert len(_Receiver.calls) == 1

    # Tenant separation: tenant B cannot use A's reply template (RLS), sees no runs of A.
    b_rule = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": f"B {RUN}",
                "trigger_event_type": "ticket.created",
                "actions": [{"type": "mail_draft", "reply_template_id": reply_tpl["id"]}],
            },
            headers=other,
        ),
        201,
    )
    b_dry = _ok(
        client.post(
            f"{A}/rules/{b_rule['id']}/test",
            json={"type": "ticket.created", "entity": {"category": "x"}},
            headers=other,
        )
    )
    assert b_dry["matched"] is True
    assert b_dry["actions"] == []
    assert "Antwortvorlage nicht gefunden" in b_dry["error"]
    assert _ok(client.get(f"{A}/runs", headers=other))["total"] == 0
    assert client.get(f"{A}/rules/{rule['id']}", headers=other).status_code == 404

    for rid, h in ((rule["id"], admin), (b_rule["id"], other)):
        assert client.delete(f"{A}/rules/{rid}", headers=h).status_code == 204


def test_schedule_trigger(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "a2admin"))
    care = bearer(login(client, world, "a2care"))
    calls_before = len(_Receiver.calls)
    rule = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": f"Wochenstart {RUN}",
                "active": True,
                "trigger_kind": "schedule",
                "schedule": {"frequency": "daily", "time": "07:30"},
                "actions": [
                    {
                        "type": "notify",
                        "role_codes": ["caretaker"],
                        "title": "Tagesstart {payload.due_at}",
                    },
                    {"type": "webhook", "url": receiver, "secret": SECRET},
                ],
            },
            headers=admin,
        ),
        201,
    )
    assert rule["trigger_kind"] == "schedule"
    assert rule["trigger_event_type"] is None
    assert rule["schedule"] == {"frequency": "daily", "time": "07:30"}
    assert rule["last_scheduled_at"] is None

    # Dry run of a schedule rule works on a due moment.
    dry = _ok(
        client.post(
            f"{A}/rules/{rule['id']}/test",
            json={"type": "schedule.due", "due_at": "2026-09-26T05:30:00Z"},
            headers=admin,
        )
    )
    assert dry["matched"] is True
    assert dry["actions"][0]["title"] == "Tagesstart 2026-09-26T05:30:00+00:00"

    # First pass only positions the watermark (moments before activation are history).
    t0 = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)  # 08:00 Berlin, after 07:30
    first = asyncio.run(process_events_once(settings, now=t0))
    assert first["runs"] == 0
    positioned = _ok(client.get(f"{A}/rules/{rule['id']}", headers=admin))
    assert positioned["last_scheduled_at"] is not None
    assert _ok(client.get(f"{A}/runs", params={"rule_id": rule["id"]}, headers=admin))["total"] == 0

    # Not yet due the next morning at 07:29 Berlin; due at 07:30; once per window.
    early = datetime(2026, 9, 27, 5, 29, tzinfo=UTC)
    assert asyncio.run(process_events_once(settings, now=early))["runs"] == 0
    due = datetime(2026, 9, 27, 5, 31, tzinfo=UTC)
    fired = asyncio.run(process_events_once(settings, now=due))
    assert fired["runs"] == 1
    assert fired["failed"] == 0
    assert asyncio.run(process_events_once(settings, now=due + timedelta(minutes=5)))["runs"] == 0
    runs = _ok(client.get(f"{A}/runs", params={"rule_id": rule["id"]}, headers=admin))
    assert runs["total"] == 1
    assert runs["items"][0]["event_type"] == "schedule.due"
    assert runs["items"][0]["status"] == "executed"
    assert len(_Receiver.calls) == calls_before + 1
    sent = json.loads(_Receiver.calls[-1]["body"])
    assert sent["event"]["type"] == "schedule.due"
    assert sent["event"]["payload"]["due_at"] == "2026-09-27T05:30:00+00:00"
    notes = _ok(
        client.get("/api/v1/workspace/notifications", params={"unread": True}, headers=care)
    )
    assert [n for n in notes if n["title"] == "Tagesstart 2026-09-27T05:30:00+00:00"]
    updated = _ok(client.get(f"{A}/rules/{rule['id']}", headers=admin))
    assert updated["last_scheduled_at"].startswith("2026-09-27T05:30:00")

    # A changed schedule starts a fresh watermark; a deactivated rule never fires.
    changed = _ok(
        client.patch(
            f"{A}/rules/{rule['id']}",
            json={"schedule": {"frequency": "weekly", "time": "09:00", "weekday": 0}},
            headers=admin,
        )
    )
    assert changed["last_scheduled_at"] is None
    _ok(client.post(f"{A}/rules/{rule['id']}/activate", json={"active": False}, headers=admin))
    later = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)  # Monday 10:00 Berlin
    assert asyncio.run(process_events_once(settings, now=later))["runs"] == 0
    assert client.delete(f"{A}/rules/{rule['id']}", headers=admin).status_code == 204
