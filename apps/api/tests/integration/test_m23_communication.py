"""M23: dispatch per channel (post, e-mail, portal), serial dispatch grouped by channel,
delivery only with evidence, portal inbox, complete communication history per contact,
calendar as ICS."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"cm-{RUN}", name=f"Komm {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m23admin"), display_name="admin", password=PASSWORD
        )
        world.users["m23admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_dispatch_history_and_calendar(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m23admin"))
    post = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Paul", "last_name": f"Post{RUN}"},
            headers=h,
        ),
        201,
    )
    mail = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Mia",
                "last_name": f"Mail{RUN}",
                "preferred_channel": "email",
                "emails": [{"email": f"mia{RUN}@example.com"}],
            },
            headers=h,
        ),
        201,
    )
    portal = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Pia",
                "last_name": f"Portal{RUN}",
                "preferred_channel": "portal",
            },
            headers=h,
        ),
        201,
    )
    doc = _ok(
        client.post(
            "/api/v1/documents",
            data={"title": "Rundschreiben"},
            files={"file": ("rund.txt", b"Rundschreiben", "text/plain")},
            headers=h,
        ),
        201,
    )["id"]
    internal = _ok(
        client.post(
            "/api/v1/documents",
            data={
                "title": "Intern",
                "links": f'[{{"entity_type": "contact", "entity_id": "{portal["id"]}"}}]',
            },
            files={"file": ("intern.txt", b"Intern", "text/plain")},
            headers=h,
        ),
        201,
    )["id"]

    res = _ok(
        client.post(
            "/api/v1/dispatches/serial",
            json={
                "items": [{"document_id": doc, "contact_id": c["id"]} for c in (post, mail, portal)]
            },
            headers=h,
        ),
        201,
    )
    assert res["counts"] == {"post": 1, "email": 1, "portal": 1}
    email_dispatch = res["by_channel"]["email"][0]
    assert email_dispatch["message_id"] is not None
    letter = res["by_channel"]["post"][0]
    assert letter["status"] == "prepared"
    assert (
        client.post(
            f"/api/v1/dispatches/{letter['id']}/evidence", json={"status": "delivered"}, headers=h
        ).status_code
        == 422
    )
    _ok(
        client.post(
            f"/api/v1/dispatches/{letter['id']}/evidence",
            json={
                "status": "sent",
                "evidence_kind": "registered_mail",
                "evidence_ref": "RR123456789DE",
            },
            headers=h,
        )
    )
    delivered = _ok(
        client.post(
            f"/api/v1/dispatches/{letter['id']}/evidence",
            json={
                "status": "delivered",
                "evidence_kind": "registered_mail",
                "evidence_ref": "RR123456789DE",
            },
            headers=h,
        )
    )
    assert delivered["delivered_at"] is not None
    assert (
        client.post(
            f"/api/v1/dispatches/{letter['id']}/evidence", json={"status": "failed"}, headers=h
        ).status_code
        == 409
    )

    # Portal inbox shows the dispatched letter, not internal documents linked to the contact.
    inv = _ok(
        client.post(
            "/api/v1/portal-admin/accounts",
            json={
                "contact_id": portal["id"],
                "email": world.email("m23portal"),
                "display_name": "Pia",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": inv["invitation_token"], "password": PASSWORD},
        )
    )
    pt = bearer(login(client, world, "m23portal"))
    inbox = {d["id"] for d in _ok(client.get("/api/v1/portal/documents", headers=pt))}
    assert inbox == {doc}
    assert internal not in inbox

    history = _ok(client.get(f"/api/v1/contacts/{mail['id']}/history", headers=h))
    assert {e["kind"] for e in history} == {"dispatch_email", "email_out"}

    _ok(
        client.post(
            "/api/v1/workspace/calendar",
            json={"title": "Begehung, Dach; Süd", "starts_on": "2026-10-05"},
            headers=h,
        ),
        201,
    )
    ics = client.get("/api/v1/workspace/calendar.ics", headers=h)
    assert ics.status_code == 200
    assert ics.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Begehung\\, Dach\\; Süd" in ics.text
    assert "DTSTART;VALUE=DATE:20261005" in ics.text
