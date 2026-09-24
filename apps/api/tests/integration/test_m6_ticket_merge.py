"""Ticket merge (M6, docs/integrations/mail-optimierung.md decision 25.09.2026): two tickets
with a comment, an event and a mail attached via /mail/ingest are merged into a new ticket with
a new number; both sources close with merged_into_ticket_id, all events, comments and messages
move to the new ticket; merging an already merged ticket is refused, as is fewer than two ids or
a read-only role."""

import asyncio
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
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"
M = "/api/v1/mail"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"tm-{RUN}", name=f"Merge {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("tmadmin", "tenant_admin"),
            ("tmread", "read_only_master_data"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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


def _eml(sender: str, subject: str, msg_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Bitte um Rückmeldung zum Vorgang.")
    return bytes(msg)


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "message/rfc822")}, headers=h),
            201,
        )["id"]
    )


def test_ticket_merge(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "tmadmin"))
    reader = bearer(login(client, world, "tmread"))

    ticket_a = _ok(
        client.post(
            T,
            json={
                "title": f"Wasserschaden Bad {RUN}",
                "public_description": "Erste Meldung",
                "priority": "normal",
                "source": "phone",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{T}/{ticket_a['id']}/comments",
            json={"body": "Rückruf beim Mieter erledigt.", "internal": True},
            headers=h,
        ),
        201,
    )

    doc = _upload(
        client,
        h,
        "m1.eml",
        _eml(f"mieter{RUN}@example.com", "Wasserschaden erneut", f"<m1-{RUN}@x>"),
    )
    ingested = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "auto_ticket": True}, headers=h), 201
    )
    assert ingested["ticket_id"]
    ticket_b_id = ingested["ticket_id"]
    _ok(
        client.post(
            f"{T}/{ticket_b_id}/comments",
            json={"body": "Dienstleister informiert.", "internal": True},
            headers=h,
        ),
        201,
    )

    # Fewer than two ids.
    assert (
        client.post(f"{T}/merge", json={"ticket_ids": [ticket_a["id"]]}, headers=h).status_code
        == 422
    )

    # Read-only role cannot merge.
    assert (
        client.post(
            f"{T}/merge", json={"ticket_ids": [ticket_a["id"], ticket_b_id]}, headers=reader
        ).status_code
        == 403
    )

    merged = _ok(
        client.post(
            f"{T}/merge",
            json={"ticket_ids": [ticket_a["id"], ticket_b_id]},
            headers=h,
        ),
        201,
    )
    assert merged["number"] not in (ticket_a["number"],)
    assert set(merged["merged_ticket_ids"]) == {ticket_a["id"], ticket_b_id}
    assert merged["title"] == ticket_a["title"]  # oldest ticket wins
    assert merged["status"] == "new"

    detail = _ok(client.get(f"{T}/{merged['id']}", headers=h))
    bodies = {c["body"] for c in detail["comments"]}
    assert bodies == {"Rückruf beim Mieter erledigt.", "Dienstleister informiert."}
    kinds = [e["kind"] for e in detail["events"]]
    assert kinds.count("merged_from") == 2

    source_a = _ok(client.get(f"{T}/{ticket_a['id']}", headers=h))
    assert source_a["status"] == "closed"
    assert source_a["merged_into_ticket_id"] == merged["id"]
    assert any(e["kind"] == "merged_into" for e in source_a["events"])

    source_b = _ok(client.get(f"{T}/{ticket_b_id}", headers=h))
    assert source_b["status"] == "closed"
    assert source_b["merged_into_ticket_id"] == merged["id"]

    messages = _ok(client.get("/api/v1/mail/messages", headers=h))
    moved = next(m for m in messages if m["id"] == ingested["id"])
    assert moved["ticket_id"] == merged["id"]

    # Merging an already merged ticket is refused.
    third = _ok(
        client.post(T, json={"title": f"Weiteres Ticket {RUN}", "source": "manual"}, headers=h),
        201,
    )
    assert (
        client.post(
            f"{T}/merge",
            json={"ticket_ids": [ticket_a["id"], third["id"]]},
            headers=h,
        ).status_code
        == 409
    )
