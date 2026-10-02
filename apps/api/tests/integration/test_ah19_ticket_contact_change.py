"""GAG-30: POST /tickets/{id}/proposals/contact-change (section 6.6, 14).

The endpoint computes a master data change proposal from the latest inbound mail of a ticket
on demand. The result is only a pending proposal (nothing is changed on the contact); the
decision runs through the existing accept and reject endpoints. Covered: creation from the
latest mail, idempotency per message, no proposal for an unrelated mail, conflict without an
inbound mail, rejection leaves the contact unchanged, acceptance applies the change, other
tenant 404, read only role 403, malformed id 422. The automatic proposal on mail intake is
switched off for this test (monkeypatched) so that the endpoint itself creates the proposal;
no provider is released, so only the deterministic stage runs (no network)."""

import asyncio
import uuid
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"
RUN = "9-" + uuid.uuid4().hex[:6]
ADMIN, READER, OTHER = f"ah19ta-{RUN}", f"ah19tr-{RUN}", f"ah19to-{RUN}"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ah19t-{RUN}", name=f"AH19 T {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ah19u-{RUN}", name=f"AH19 U {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            (ADMIN, "tenant_admin", a),
            (READER, "read_only", a),
            (OTHER, "tenant_admin", b),
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
def client(
    database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    async def _no_auto_proposal(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("mhvp.tickets.proposals.queue_for_message", _no_auto_proposal)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ingest(c: TestClient, h: dict[str, str], sender: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = f"Absender <{sender}>", "info@example.com", subject
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@ah19>"
    msg["Date"] = "Fri, 02 Oct 2026 09:00:00 +0200"
    msg.set_content(body)
    doc = _ok(
        c.post(
            "/api/v1/documents",
            files={"file": ("mail.eml", bytes(msg), "message/rfc822")},
            headers=h,
        ),
        201,
    )["id"]
    out = _ok(
        c.post("/api/v1/mail/ingest", json={"document_id": doc, "auto_ticket": True}, headers=h),
        201,
    )
    return str(out["ticket_id"])


def _contact(c: TestClient, h: dict[str, str], last: str, email: str) -> dict[str, Any]:
    return dict(
        _ok(
            c.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "salutation": "Frau",
                    "first_name": "Berta",
                    "last_name": last,
                    "emails": [{"email": email}],
                },
                headers=h,
            ),
            201,
        )
    )


def _name_change(c: TestClient, h: dict[str, str], tag: str) -> tuple[str, dict[str, Any]]:
    sender = f"berta.{tag}.{RUN}@example.org"
    contact = _contact(c, h, f"Alt{tag}", sender)
    ticket = _ingest(
        c,
        h,
        sender,
        "Namensänderung",
        f"Nach meiner Hochzeit hat sich mein Name von Berta Alt{tag} in Berta Neu{tag} geändert.",
    )
    return ticket, contact


def test_compute_creates_pending_proposal_once_and_reject_changes_nothing(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, ADMIN))
    ticket, contact = _name_change(client, h, "rj")
    assert _ok(client.get(f"{T}/{ticket}/proposals", headers=h)) == []

    created = _ok(client.post(f"{T}/{ticket}/proposals/contact-change", headers=h), 201)
    assert created["decision"] == "pending"
    assert created["proposed"]["contact_id"] == contact["id"]
    assert created["proposed"]["changes"][0]["new"] == "Neurj"
    # Only a proposal: the contact itself is unchanged.
    assert created["contact"]["last_name"] == "Altrj"

    again = _ok(client.post(f"{T}/{ticket}/proposals/contact-change", headers=h), 201)
    assert again["id"] == created["id"]
    assert len(_ok(client.get(f"{T}/{ticket}/proposals", headers=h))) == 1

    rejected = _ok(
        client.post(
            f"{T}/{ticket}/proposals/{created['id']}/reject",
            json={"reason": "nicht belegt"},
            headers=h,
        )
    )
    assert rejected["decision"] == "rejected"
    after = _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))
    assert after["last_name"] == "Altrj"


def test_compute_then_accept_applies_change(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, ADMIN))
    ticket, contact = _name_change(client, h, "ac")
    created = _ok(client.post(f"{T}/{ticket}/proposals/contact-change", headers=h), 201)
    accepted = _ok(client.post(f"{T}/{ticket}/proposals/{created['id']}/accept", headers=h))
    assert accepted["decision"] == "accepted"
    after = _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))
    assert after["last_name"] == "Neuac"


def test_compute_without_change_and_without_mail(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, ADMIN))
    plain = _ingest(
        client, h, f"plain.{RUN}@example.org", "Heizung", "Die Heizung im Keller ist kalt."
    )
    resp = client.post(f"{T}/{plain}/proposals/contact-change", headers=h)
    assert resp.status_code == 201, resp.text
    assert resp.json() is None
    assert _ok(client.get(f"{T}/{plain}/proposals", headers=h)) == []

    manual = _ok(client.post(T, json={"title": f"Ohne Mail {RUN}"}, headers=h), 201)
    conflict = client.post(f"{T}/{manual['id']}/proposals/contact-change", headers=h)
    assert conflict.status_code == 409, conflict.text


def test_compute_tenant_separation_permission_and_validation(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, ADMIN))
    ticket, _contact_row = _name_change(client, h, "rl")
    other = bearer(login(client, world, OTHER, tenant_id=world.tenant_b))
    assert client.post(f"{T}/{ticket}/proposals/contact-change", headers=other).status_code == 404
    reader = bearer(login(client, world, READER))
    assert client.post(f"{T}/{ticket}/proposals/contact-change", headers=reader).status_code == 403
    assert client.post(f"{T}/not-a-uuid/proposals/contact-change", headers=h).status_code == 422
    assert client.post(f"{T}/{ticket}/proposals/contact-change").status_code == 401
    # Nothing was created by the refused calls.
    assert _ok(client.get(f"{T}/{ticket}/proposals", headers=h)) == []
