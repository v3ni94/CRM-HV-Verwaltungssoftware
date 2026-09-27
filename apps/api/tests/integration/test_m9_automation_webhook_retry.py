"""M9 / A82 / M9-08: retries of the rule action ``webhook``.

A failed rule webhook is retried after the plan 1, 5, 15, 60 minutes, at most 5 attempts, then
the delivery goes ``dead`` and the rule owner gets an internal notification; every attempt is
signed, pinned to the checked address and carries a stable idempotency key; the delivery log
hangs on the run; manual redelivery needs ``tenant_settings:update``, stays within the tenant
and gives a dead row a fresh attempt budget; a delivery is never sent twice in one pass.
"""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from mhvp.automation.models import WEBHOOK_MAX_ATTEMPTS, WEBHOOK_RETRY_SCHEDULE_SECONDS
from mhvp.automation.tasks import process_events_once
from mhvp.core.config import Settings
from mhvp.core.webhooks import SIGNATURE_HEADER, verify
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/automation"
SECRET = "retry-secret-0123456789abcdef"


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"a82-{RUN}", name=f"A82 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"a82b-{RUN}", name=f"A82b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("r_admin", "tenant_admin", a),
            ("r_care", "caretaker", a),
            ("r_other", "tenant_admin", b),
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


class _Receiver(BaseHTTPRequestHandler):
    """Local target: answers with ``status`` and records every POST."""

    calls: ClassVar[list[dict[str, Any]]] = []
    status = 503

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        _Receiver.calls.append({"body": body, "headers": dict(self.headers)})
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
        yield f"http://127.0.0.1:{server.server_address[1]}/rule-hook"
    finally:
        server.shutdown()


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _run(client: TestClient, headers: dict[str, str], rule_id: str) -> dict[str, Any]:
    runs = _ok(client.get(f"{A}/runs", params={"rule_id": rule_id}, headers=headers))["items"]
    assert len(runs) == 1, runs
    return dict(runs[0])


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_webhook_retry_schedule_dead_and_redelivery(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "r_admin"))
    care = bearer(login(client, world, "r_care"))
    other = bearer(login(client, world, "r_other"))
    asyncio.run(process_events_once(settings))  # positions the watermark
    rule = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": f"Retry {RUN}",
                "active": True,
                "trigger_event_type": "ticket.created",
                "actions": [{"type": "webhook", "url": receiver, "secret": SECRET}],
            },
            headers=admin,
        ),
        201,
    )
    _ok(client.post("/api/v1/tickets", json={"title": "Retry"}, headers=admin), 201)

    # First attempt in the pass that runs the rule: target answers 503, run stays executed
    # (the action was enqueued), the delivery is pending with the first retry slot (1 minute).
    _Receiver.status = 503
    t0 = datetime.now(UTC) + timedelta(seconds=30)
    result = asyncio.run(process_events_once(settings, now=t0))
    # Totals span every active tenant of the database, so the receiver's calls are counted.
    assert result["failed"] == 0
    assert result["webhooks"] >= 1
    assert result["webhooks_failed"] >= 1
    assert len(_Receiver.calls) == 1
    run = _run(client, admin, rule["id"])
    assert run["status"] == "executed"
    assert run["actions"][0]["detail"] == "Webhook eingereiht."
    assert "_pending_delivery" not in run["actions"][0]
    assert len(run["webhook_deliveries"]) == 1
    delivery = run["webhook_deliveries"][0]
    assert run["actions"][0]["delivery_id"] == delivery["id"]
    assert delivery["status"] == "pending"
    assert delivery["attempts"] == 1
    assert delivery["max_attempts"] == WEBHOOK_MAX_ATTEMPTS == 5
    assert delivery["last_status_code"] == 503
    assert delivery["last_error"] == "HTTP 503"
    assert delivery["last_duration_ms"] is not None
    assert delivery["idempotency_key"]
    assert _at(delivery["next_attempt_at"]) == t0 + timedelta(
        seconds=WEBHOOK_RETRY_SCHEDULE_SECONDS[0]
    )

    # Every attempt is signed afresh, carries the delivery id and a stable idempotency key
    # across every retry (M9-08); the body is stable.
    call = _Receiver.calls[0]
    assert verify(SECRET, call["body"], call["headers"][SIGNATURE_HEADER], now=int(time.time()))
    assert call["headers"]["X-MHVP-Rule"] == rule["id"]
    assert call["headers"]["X-MHVP-Delivery"] == delivery["id"]
    assert call["headers"]["X-MHVP-Event"] == "ticket.created"
    assert call["headers"]["Idempotency-Key"] == delivery["idempotency_key"]
    assert json.loads(call["body"])["rule"]["id"] == rule["id"]

    # Not due yet: no call; the same pass twice never sends twice.
    early = t0 + timedelta(seconds=WEBHOOK_RETRY_SCHEDULE_SECONDS[0] - 1)
    asyncio.run(process_events_once(settings, now=early))
    assert len(_Receiver.calls) == 1

    # Walk the staged schedule (1, 5, 15, 60 minutes): each slot sends exactly once, with the
    # same idempotency key every time, then the delivery goes dead after 5 attempts.
    now = t0
    for attempt, delay in enumerate(WEBHOOK_RETRY_SCHEDULE_SECONDS, start=2):
        now = now + timedelta(seconds=delay)
        asyncio.run(process_events_once(settings, now=now))
        asyncio.run(process_events_once(settings, now=now))  # same moment: nothing twice
        assert len(_Receiver.calls) == attempt
        delivery = _run(client, admin, rule["id"])["webhook_deliveries"][0]
        assert delivery["attempts"] == attempt
        assert _Receiver.calls[-1]["headers"]["Idempotency-Key"] == delivery["idempotency_key"]
        if attempt <= len(WEBHOOK_RETRY_SCHEDULE_SECONDS):
            assert delivery["status"] == "pending"
            assert _at(delivery["next_attempt_at"]) == now + timedelta(
                seconds=WEBHOOK_RETRY_SCHEDULE_SECONDS[attempt - 1]
            )
        else:
            assert delivery["status"] == "dead"
            assert delivery["next_attempt_at"] is None
    assert json.loads(_Receiver.calls[-1]["body"]) == json.loads(_Receiver.calls[0]["body"])
    for call in _Receiver.calls:
        assert verify(SECRET, call["body"], call["headers"][SIGNATURE_HEADER], now=int(time.time()))

    # Exhausted: no further attempts even far in the future; the rule owner (admin, who saved
    # the rule) was notified exactly once that the delivery is dead.
    asyncio.run(process_events_once(settings, now=now + timedelta(days=3)))
    assert len(_Receiver.calls) == WEBHOOK_MAX_ATTEMPTS
    notifications = _ok(client.get("/api/v1/workspace/notifications", headers=admin))
    kinds = [n["kind"] for n in notifications]
    assert kinds.count("automation_webhook_dead") == 1

    # Manual redelivery: caretaker (no tenant_settings:update) 403, other tenant 404 (RLS),
    # admin 202; a dead row gets a fresh attempt budget, so the log stays meaningful.
    path = f"{A}/webhook-deliveries/{delivery['id']}/redeliver"
    assert client.post(path, headers=care).status_code == 403
    assert client.post(path, headers=other).status_code == 404
    _Receiver.status = 200
    assert client.post(path, headers=admin).status_code == 202
    delivery = _run(client, admin, rule["id"])["webhook_deliveries"][0]
    assert delivery["status"] == "pending"
    assert delivery["attempts"] == 0
    calls_before = len(_Receiver.calls)
    later = datetime.now(UTC) + timedelta(seconds=30)
    asyncio.run(process_events_once(settings, now=later))
    assert len(_Receiver.calls) == calls_before + 1
    delivery = _run(client, admin, rule["id"])["webhook_deliveries"][0]
    assert delivery["status"] == "succeeded"
    assert delivery["attempts"] == 1
    assert delivery["last_status_code"] == 200
    assert delivery["last_error"] is None
    assert delivery["delivered_at"] is not None
    assert delivery["next_attempt_at"] is None
    asyncio.run(process_events_once(settings, now=later))
    assert len(_Receiver.calls) == calls_before + 1

    # Tenant separation of the log: tenant B sees no runs and no deliveries of A.
    assert _ok(client.get(f"{A}/runs", headers=other))["total"] == 0
    assert client.delete(f"{A}/rules/{rule['id']}", headers=admin).status_code == 204


def test_dead_delivery_notifies_explicit_owner_before_last_editor(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    """M9-08 Kleinbefund 27.09.2026: an explicit ``owner_user_id`` is notified on a dead
    delivery, ahead of the last editor (here the admin who created and saved the rule)."""
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "r_admin"))
    care_id = str(world.users["r_care"])
    _Receiver.status = 503
    _Receiver.calls.clear()
    asyncio.run(process_events_once(settings))  # positions the watermark
    rule = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": f"Owner {RUN}",
                "active": True,
                "trigger_event_type": "ticket.created",
                "actions": [{"type": "webhook", "url": receiver, "secret": SECRET}],
                "owner_user_id": care_id,
            },
            headers=admin,
        ),
        201,
    )
    assert rule["owner_user_id"] == care_id
    _ok(client.post("/api/v1/tickets", json={"title": "Owner"}, headers=admin), 201)

    now = datetime.now(UTC) + timedelta(seconds=30)
    for delay in (0, *WEBHOOK_RETRY_SCHEDULE_SECONDS):
        now = now + timedelta(seconds=delay)
        asyncio.run(process_events_once(settings, now=now))
    delivery = _run(client, admin, rule["id"])["webhook_deliveries"][0]
    assert delivery["status"] == "dead"

    care = bearer(login(client, world, "r_care"))
    care_notifications = _ok(client.get("/api/v1/workspace/notifications", headers=care))
    assert any(
        n["kind"] == "automation_webhook_dead" and n["entity_id"] == rule["id"]
        for n in care_notifications
    )
    # The admin (who created and last saved the rule) is not the fallback recipient here,
    # because the rule carries an explicit owner: no notification of *this* rule for them.
    admin_notifications = _ok(client.get("/api/v1/workspace/notifications", headers=admin))
    assert not any(
        n["kind"] == "automation_webhook_dead" and n["entity_id"] == rule["id"]
        for n in admin_notifications
    )

    assert client.delete(f"{A}/rules/{rule['id']}", headers=admin).status_code == 204
