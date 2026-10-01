"""AD03 (GA02-06): data_sharing gates the transfer of contact data to third parties: the
resident's contact on a work order for the provider (tickets, portal) and the payload of the
webhook for contact.updated (automation). Granted, missing, revoked, policy, tenant separation."""

import asyncio
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.automation.tasks import process_events_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a55_a58_portal_attachments import _rental, _tenancy
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
SECRET = "ad03-secret-0123456789abcdef"
NOW = datetime.now(UTC)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ad3a-{RUN}", name=f"AD03 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ad3b-{RUN}", name=f"AD03 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("ad03admin", a), ("ad03adminb", b)):
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


class _Receiver(BaseHTTPRequestHandler):
    calls: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        _Receiver.calls.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_: Any) -> None:
        return


@pytest.fixture(scope="module")
def receiver() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/ad03"
    finally:
        server.shutdown()


def _grant(client: TestClient, h: dict[str, str], contact: str) -> str:
    return str(
        _ok(
            client.post(
                f"/api/v1/contacts/{contact}/consents",
                json={
                    "kind": "data_sharing",
                    "granted_at": (NOW - timedelta(minutes=1)).isoformat(),
                    "source": "Formular AD03",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def _events(client: TestClient, h: dict[str, str], etype: str, entity_id: str) -> list[Any]:
    rows = _ok(
        client.get("/api/v1/tenant/events", params={"type": etype, "page_size": 200}, headers=h)
    )
    return [e for e in rows if e["entity_id"] == entity_id]


def test_ad03_work_order_resident_contact(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ad03admin", tenant_id=world.tenant_a))
    hb = bearer(login(client, world, "ad03adminb", tenant_id=world.tenant_b))
    prop_id, _ = _rental(client, h, "903")
    tenancy = _tenancy(client, h, prop_id, "A")
    resident = _contact_of(client, h, tenancy["party_id"])
    ta = _portal_user(client, h, world, "ad03tenant", resident)
    provider_contact = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"Dach {RUN}"}, headers=h
        ),
        201,
    )["id"]
    pv = _portal_user(client, h, world, "ad03provider", provider_contact)
    ticket = _ok(
        client.post(
            f"{P}/tickets",
            json={"title": "Dach undicht", "description": "Tropft", "unit_id": tenancy["unit_id"]},
            headers=ta,
        ),
        201,
    )
    body = {
        "ticket_id": ticket["id"],
        "property_id": prop_id,
        "provider_contact_id": provider_contact,
        "description": "Ziegel ersetzen",
    }

    def provider_view(oid: str) -> dict[str, Any]:
        orders = _ok(client.get(f"{P}/work-orders", headers=pv))
        return dict(next(o for o in orders if o["id"] == oid)["resident_contact"])

    # Missing consent: the order goes out without personal fields, reason is logged.
    missing = _ok(client.post("/api/v1/work-orders", json=body, headers=h), 201)
    assert missing["contact_share"] == {"shared": False, "reason": "data_sharing_consent_missing"}
    view = provider_view(missing["id"])
    assert view["shared"] is False
    assert view["contact"] is None
    withheld = _events(client, h, "work_order.contact_data_withheld", missing["id"])
    assert withheld
    assert withheld[0]["payload"]["reason"] == "data_sharing_consent_missing"

    # Granted: name is shared.
    consent = _grant(client, h, resident)
    granted = _ok(client.post("/api/v1/work-orders", json=body, headers=h), 201)
    assert granted["contact_share"]["shared"] is True
    view = provider_view(granted["id"])
    assert view["shared"] is True
    assert view["contact"]["name"]
    assert _events(client, h, "work_order.contact_data_shared", granted["id"])

    # Revoked: the same order now shows no personal fields (check runs on every read).
    _ok(client.post(f"/api/v1/consents/{consent}/revoke", headers=h))
    view = provider_view(granted["id"])
    assert view["shared"] is False
    assert view["contact"] is None

    # Tenant policy consent_or_contract: contractual necessity suffices for the work order.
    _ok(
        client.put(
            "/api/v1/consent-policy",
            json={"email_delivery": "consent_only", "data_sharing": "consent_or_contract"},
            headers=h,
        )
    )
    try:
        assert provider_view(granted["id"])["shared"] is True
    finally:
        _ok(
            client.put(
                "/api/v1/consent-policy",
                json={"email_delivery": "consent_only", "data_sharing": "consent_only"},
                headers=h,
            )
        )
    assert provider_view(granted["id"])["shared"] is False

    # Tenant separation: tenant B neither sees the order nor is affected by A's consent.
    assert client.get(f"/api/v1/work-orders/{granted['id']}", headers=hb).status_code == 404


def test_ad03_webhook_contact_updated(
    client: TestClient, world: World, database: Database, redis_url: str, receiver: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "ad03admin", tenant_id=world.tenant_a))
    asyncio.run(process_events_once(settings))  # positions the watermark
    _ok(
        client.post(
            "/api/v1/automation/rules",
            json={
                "name": f"AD03 {RUN}",
                "active": True,
                "trigger_event_type": "contact.updated",
                "actions": [{"type": "webhook", "url": receiver, "secret": SECRET}],
            },
            headers=h,
        ),
        201,
    )
    contacts = {
        name: str(
            _ok(
                client.post(
                    "/api/v1/contacts",
                    json={"kind": "person", "first_name": "W", "last_name": f"{name}{RUN}"},
                    headers=h,
                ),
                201,
            )["id"]
        )
        for name in ("Ja", "Nein", "Wid")
    }
    _grant(client, h, contacts["Ja"])
    revoked = _grant(client, h, contacts["Wid"])
    _ok(client.post(f"/api/v1/consents/{revoked}/revoke", headers=h))
    for cid in contacts.values():
        _ok(client.patch(f"/api/v1/contacts/{cid}", json={"notes": "geändert"}, headers=h))
    _Receiver.calls.clear()
    t0 = datetime.now(UTC) + timedelta(seconds=30)
    asyncio.run(process_events_once(settings, now=t0))
    by_id = {c["event"]["entity_id"]: c for c in _Receiver.calls if c["event"]["entity_id"]}
    assert by_id[contacts["Ja"]]["entity"] is not None
    assert "personal_data_withheld" not in by_id[contacts["Ja"]]
    for name in ("Nein", "Wid"):
        sent = by_id[contacts[name]]
        assert sent["entity"] is None
        assert sent["event"]["payload"] is None
        assert sent["personal_data_withheld"] is True
        withheld = _events(client, h, "automation.webhook_data_withheld", contacts[name])
        assert withheld[0]["payload"]["reason"] == "data_sharing_consent_missing"
    assert not _events(client, h, "automation.webhook_data_withheld", contacts["Ja"])
