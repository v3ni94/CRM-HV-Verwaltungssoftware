"""A69: outgoing webhooks ``contact.updated`` and ``invoice.issued`` (section 12). A change of
contact master data and the issue of a Verwalterhonorar invoice each create a signed
delivery to the tenant's subscribed URL; payloads carry identifiers and field names only (no
IBAN, no names); a subscriber of another tenant never receives the event."""

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
from mhvp.core.webhooks import EVENT_TYPES, verify
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _unit

pytestmark = pytest.mark.integration
IBAN = "DE02120300000000202051"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"wh-{RUN}", name=f"Hook A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"whb-{RUN}", name=f"Hook B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("whadmin", a), ("whother", b)]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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


class _Receiver(http.server.BaseHTTPRequestHandler):
    received: ClassVar[list[tuple[str, dict[str, str], bytes]]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Receiver.received.append((self.path, dict(self.headers), body))
        self.send_response(204)
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _subscribe(client: TestClient, h: dict[str, str], url: str, types: list[str]) -> str:
    created = _ok(
        client.post("/api/v1/tenant/webhooks", json={"url": url, "event_types": types}, headers=h),
        201,
    )
    return str(created["secret"])


def _events(path: str, event_type: str) -> list[tuple[dict[str, str], dict[str, Any]]]:
    return [
        (headers, json.loads(body))
        for p, headers, body in _Receiver.received
        if p == path and json.loads(body)["type"] == event_type
    ]


def test_event_catalogue_names_the_new_types() -> None:
    assert "contact.updated" in EVENT_TYPES
    assert "invoice.issued" in EVENT_TYPES


def test_contact_updated_delivers_signed_minimal_payload_per_tenant(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    h = bearer(login(client, world, "whadmin"))
    other = bearer(login(client, world, "whother"))
    secret_a = _subscribe(client, h, f"{receiver}/a-contact", ["contact.updated"])
    _subscribe(client, other, f"{receiver}/b-all", ["*"])

    person = {
        "kind": "person",
        "first_name": "Erika",
        "last_name": f"Hook{RUN}",
        "emails": [{"email": f"erika.hook.{RUN}@example.org"}],
    }
    created = _ok(client.post("/api/v1/contacts", json=person, headers=h), 201)
    contact_id = created["id"]
    changed = person | {
        "last_name": f"Hookneu{RUN}",
        "bank_accounts": [{"iban": IBAN, "valid_from": "2026-01-01", "holder": "Erika Hook"}],
    }
    _ok(
        client.put(
            f"/api/v1/contacts/{contact_id}",
            json=changed,
            headers=h | {"If-Match": f'"{created["version"]}"'},
        )
    )
    asyncio.run(dispatch_once(_settings(database, redis_url)))

    updates = [
        e for e in _events("/a-contact", "contact.updated") if e[1]["entity_id"] == contact_id
    ]
    assert len(updates) == 1
    headers_in, body = updates[0]
    raw = next(b for p, _, b in _Receiver.received if p == "/a-contact" and json.loads(b) == body)
    assert headers_in["X-MHVP-Event"] == "contact.updated"
    assert verify(secret_a, raw, headers_in["X-MHVP-Signature"], now=int(time.time()))
    assert not verify("wrong", raw, headers_in["X-MHVP-Signature"], now=int(time.time()))
    assert body["tenant_id"] == str(world.tenant_a)
    assert body["entity_type"] == "contact"
    assert {"bank_accounts", "last_name"} <= set(body["payload"]["fields"])
    # Minimal payload: field names only, no values, no IBAN, no person name.
    text = raw.decode()
    assert IBAN not in text
    assert "2020 51" not in text
    assert f"Hookneu{RUN}" not in text
    assert "Erika" not in text
    assert set(body["payload"]) == {"fields"}
    # Tenant separation: the catch-all subscriber of tenant B never sees tenant A's contact.
    assert all(e[1]["entity_id"] != contact_id for e in _events("/b-all", "contact.updated"))
    assert all(
        e[1]["tenant_id"] != str(world.tenant_a) for e in _events("/b-all", "contact.updated")
    )


def test_invoice_issued_delivers_identifiers_and_amounts_only(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    h = bearer(login(client, world, "whadmin"))
    other = bearer(login(client, world, "whother"))
    secret_a = _subscribe(client, h, f"{receiver}/a-invoice", ["invoice.issued"])
    _subscribe(client, other, f"{receiver}/b-invoice", ["invoice.issued"])

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "769",
                "name": "Hook Haus",
                "management_type": "hoa",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    for no in ("01", "02"):
        _unit(client, h, prop["id"], no)
    fee = _ok(
        client.post(
            "/api/v1/accounting/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "19",
                "amounts_per_unit_type": {"apartment": "30.00"},
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={"invoice_prefix": "HVM", "vat_status": "regelbesteuert", "vat_id": "DE123456789"},
            headers=h,
        )
    )
    issued = _ok(client.post(f"/api/v1/accounting/admin-fees/{fee['id']}/invoice-issue", headers=h))
    asyncio.run(dispatch_once(_settings(database, redis_url)))

    events = [
        e for e in _events("/a-invoice", "invoice.issued") if e[1]["entity_id"] == issued["id"]
    ]
    assert len(events) == 1
    headers_in, body = events[0]
    raw = next(b for p, _, b in _Receiver.received if p == "/a-invoice" and json.loads(b) == body)
    assert verify(secret_a, raw, headers_in["X-MHVP-Signature"], now=int(time.time()))
    payload = body["payload"]
    assert payload["number"] == issued["number"]
    assert payload["invoice_id"] == issued["id"]
    assert payload["property_id"] == prop["id"]
    assert payload["fee_setting_id"] == fee["id"]
    assert payload["gross"] == "71.40"
    assert payload["net"] == "60.00"
    assert payload["currency"] == "EUR"
    assert payload["xrechnung_url"] == issued["xrechnung_url"]
    assert "Hook Haus" not in raw.decode()
    assert "Rheinpromenade" not in raw.decode()
    assert not _events("/b-invoice", "invoice.issued")


def test_admin_endpoints_catalogue_last_delivery_delete_and_tenant_separation(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    """CRM settings page (Lückenliste A89): catalogue with descriptions, last delivery in the
    list, delivery log, delete with cascade; a foreign tenant neither sees nor deletes."""
    h = bearer(login(client, world, "whadmin"))
    other = bearer(login(client, world, "whother"))
    catalogue = _ok(client.get("/api/v1/tenant/webhooks/event-types", headers=h))
    assert {c["type"]: c["description"] for c in catalogue} == EVENT_TYPES

    created = _ok(
        client.post(
            "/api/v1/tenant/webhooks",
            json={"url": f"{receiver}/admin-ui", "event_types": ["webhook_subscription.created"]},
            headers=h,
        ),
        201,
    )
    hook_id = created["id"]
    listed = next(
        x for x in _ok(client.get("/api/v1/tenant/webhooks", headers=h)) if x["id"] == hook_id
    )
    assert listed["last_delivery_status"] is None
    assert listed["created_at"]
    # Another subscription of the same tenant triggers ``webhook_subscription.created``.
    _ok(
        client.post(
            "/api/v1/tenant/webhooks",
            json={"url": f"{receiver}/admin-ui-2", "event_types": ["contact.deleted"]},
            headers=h,
        ),
        201,
    )
    asyncio.run(dispatch_once(_settings(database, redis_url)))
    listed = next(
        x for x in _ok(client.get("/api/v1/tenant/webhooks", headers=h)) if x["id"] == hook_id
    )
    assert listed["last_delivery_status"] == "succeeded"
    assert listed["last_delivery_status_code"] == 204
    assert listed["last_delivery_at"]
    log = _ok(client.get(f"/api/v1/tenant/webhooks/{hook_id}/deliveries", headers=h))
    assert log
    assert log[0]["attempts"] == 1

    # Tenant separation: tenant B sees nothing of tenant A and cannot delete.
    assert hook_id not in {
        x["id"] for x in _ok(client.get("/api/v1/tenant/webhooks", headers=other))
    }
    assert client.delete(f"/api/v1/tenant/webhooks/{hook_id}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/tenant/webhooks/{hook_id}", headers=h).status_code == 204
    assert hook_id not in {x["id"] for x in _ok(client.get("/api/v1/tenant/webhooks", headers=h))}
    assert client.get(f"/api/v1/tenant/webhooks/{hook_id}/deliveries", headers=h).json() == []
