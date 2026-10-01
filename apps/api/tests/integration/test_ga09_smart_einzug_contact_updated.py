"""GA09-04 (13.3 smart-einzug): a change of an owner contact is mirrored to a subscribed
external target as signed ``contact.updated``; the payload carries identifiers and field names
only (no name, address, IBAN); after a failed delivery the retry keeps the idempotency key."""

import asyncio
import http.server
import json
import threading
import time
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from mhvp.core.webhook_tasks import dispatch_once
from mhvp.core.webhooks import verify
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_a69_webhooks import _world  # reuse tenant setup
from tests.integration.test_m2_platform import RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
IBAN = "DE02120300000000202051"


class _Receiver(http.server.BaseHTTPRequestHandler):
    calls: ClassVar[list[tuple[dict[str, str], bytes]]] = []
    status: ClassVar[int] = 500

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Receiver.calls.append((dict(self.headers), body))
        self.send_response(_Receiver.status)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return None


@pytest.fixture(scope="module")
def receiver() -> Iterator[str]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def test_owner_contact_update_is_delivered_signed_and_retried(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    h = bearer(login(client, world, "whadmin"))
    sub = client.post(
        "/api/v1/tenant/webhooks",
        json={"url": f"{receiver}/smart-einzug", "event_types": ["contact.updated"]},
        headers=h,
    )
    assert sub.status_code == 201, sub.text
    secret, hook_id = sub.json()["secret"], sub.json()["id"]

    person = {
        "kind": "person",
        "first_name": "Otto",
        "last_name": f"Eigner{RUN}",
        "roles": ["eigentuemer"],
        "emails": [{"email": f"otto.{RUN}@example.org"}],
    }
    created = client.post("/api/v1/contacts", json=person, headers=h)
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]
    changed = person | {
        "last_name": f"Eignerneu{RUN}",
        "bank_accounts": [{"iban": IBAN, "valid_from": "2026-01-01", "holder": "Otto Eigner"}],
    }
    put = client.put(
        f"/api/v1/contacts/{contact_id}",
        json=changed,
        headers=h | {"If-Match": f'"{created.json()["version"]}"'},
    )
    assert put.status_code == 200, put.text

    # First pass: the target answers 500, the delivery stays pending with one attempt.
    _Receiver.status = 500
    asyncio.run(dispatch_once(_settings(database, redis_url)))
    first = [
        (hd, b)
        for hd, b in _Receiver.calls
        if json.loads(b).get("entity_id") == contact_id
        and json.loads(b)["type"] == "contact.updated"
    ]
    assert len(first) == 1
    log = client.get(f"/api/v1/tenant/webhooks/{hook_id}/deliveries", headers=h).json()
    failed = next(d for d in log if d["attempts"] == 1 and d["status"] != "succeeded")
    assert failed["status"] == "pending"

    # Manual redelivery after the target recovered: same idempotency key, signed, minimal.
    _Receiver.status = 204
    redo = client.post(f"/api/v1/tenant/webhook-deliveries/{failed['id']}/redeliver", headers=h)
    assert redo.status_code == 202
    asyncio.run(dispatch_once(_settings(database, redis_url)))
    again = [
        (hd, b)
        for hd, b in _Receiver.calls
        if json.loads(b).get("entity_id") == contact_id
        and json.loads(b)["type"] == "contact.updated"
    ]
    assert len(again) == 2
    (h1, _b1), (h2, b2) = again
    assert h1["Idempotency-Key"] == h2["Idempotency-Key"] == failed["id"]
    assert verify(secret, b2, h2["X-MHVP-Signature"], now=int(time.time()))
    body: dict[str, Any] = json.loads(b2)
    assert body["entity_type"] == "contact"
    assert body["tenant_id"] == str(world.tenant_a)
    assert set(body["payload"]) == {"fields"}
    text = b2.decode()
    for secret_value in (IBAN, "Otto", f"Eignerneu{RUN}", f"otto.{RUN}@example.org"):
        assert secret_value not in text
    delivered = client.get(f"/api/v1/tenant/webhooks/{hook_id}/deliveries", headers=h).json()
    assert next(d for d in delivered if d["id"] == failed["id"])["status"] == "succeeded"
