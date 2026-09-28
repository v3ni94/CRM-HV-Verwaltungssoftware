"""Claims adjuster link (rule INT-SDT-01) against the in-process fake server
(``tests/schadenstool_fake.py``): config secrets, AVV precondition, connection test, outbound
queue idempotency, comment and attachment push without echo, webhook HMAC and dedup, inbound
comments and attachments, pull reconciliation, takeover, tenant separation, roles and the
disabled flag."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.integrations.schadenstool import client as sdt_client
from mhvp.integrations.schadenstool import services as svc
from mhvp.integrations.schadenstool import tasks as sdt_tasks
from mhvp.integrations.schadenstool.models import (
    SchadenstoolEvent,
    SchadenstoolItemLink,
    SchadenstoolOutbox,
    SchadenstoolTicketLink,
)
from mhvp.integrations.schadenstool.signature import sign
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.tickets.models import TicketComment
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.schadenstool_fake import BASE, FakeSchadenstool

pytestmark = pytest.mark.integration
C = "/api/v1/integrations/schadenstool"
BUCKET = "mhvp-schadenstool"
HOOK_SECRET = "hook-secret-0123456789abcdef"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"sdt-a-{RUN}", name=f"SDT A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"sdt-b-{RUN}", name=f"SDT B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("sdtadmin", "tenant_admin", a),
            ("sdtcare", "caretaker", a),
            ("sdtread", "read_only", a),
            ("sdtadminb", "tenant_admin", b),
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
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeSchadenstool:
    server = FakeSchadenstool()
    monkeypatch.setattr(sdt_client, "TRANSPORT", server.transport())
    monkeypatch.setattr(sdt_tasks, "_send", lambda *a, **k: None)
    return server


@pytest.fixture
def settings(database: Database, redis_url: str) -> Settings:
    return _settings(database, redis_url)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def run_tenant(
    settings: Settings, tenant_id: uuid.UUID, work: Callable[[AsyncSession], Awaitable[Any]]
) -> Any:
    async def _go() -> Any:
        engine = create_async_engine(settings.database_url.get_secret_value(), poolclass=NullPool)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def process(settings: Settings, tenant_id: uuid.UUID) -> dict[str, int]:
    blobs = BlobStore(settings)

    async def _work(session: AsyncSession) -> dict[str, int]:
        sent = await svc.process_outbox(session, tenant_id, blobs=blobs)
        return sent

    out: dict[str, int] = run_tenant(settings, tenant_id, _work)

    async def _events(session: AsyncSession) -> dict[str, int]:
        return await svc.process_events(session, tenant_id, blobs=blobs, settings=settings)

    out.update({f"events_{k}": v for k, v in run_tenant(settings, tenant_id, _events).items()})
    return out


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _admin(client: TestClient, world: World, name: str = "sdtadmin") -> dict[str, str]:
    return bearer(login(client, world, name))


def _configure(
    client: TestClient, h: dict[str, str], fake: FakeSchadenstool, *, enabled: bool = True
) -> Any:
    return _ok(
        client.put(
            f"{C}/config",
            json={
                "base_url": BASE,
                "token": fake.token,
                "webhook_secret": HOOK_SECRET,
                "avv_confirmed_on": "2026-09-28",
                "avv_note": "AVV vom 28.09.2026",
                "enabled": enabled,
            },
            headers=h,
        )
    )


def _property_and_ticket(client: TestClient, h: dict[str, str], number: str) -> tuple[Any, Any]:
    prop_row = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Schadenhaus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={
                "title": "Wasserschaden Keller",
                "public_description": "Wasser tritt aus der Wand",
                "internal_description": "INTERN nicht senden",
                "property_id": prop_row["id"],
            },
            headers=h,
        ),
        201,
    )
    return prop_row, ticket


def _webhook(
    client: TestClient,
    path: str,
    event: dict[str, Any],
    *,
    secret: str = HOOK_SECRET,
    ts: int | None = None,
    signature: str | None = None,
) -> Any:
    raw = json.dumps(event).encode()
    stamp = ts if ts is not None else int(time.time())
    return client.post(
        path,
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Timestamp": str(stamp),
            "X-Signature": signature or sign(secret, raw, stamp),
        },
    )


def test_config_secrets_avv_and_connection(
    client: TestClient, world: World, fake: FakeSchadenstool, settings: Settings
) -> None:
    h = _admin(client, world)
    # Enabling without AVV confirmation is refused.
    refused = client.put(
        f"{C}/config",
        json={
            "base_url": BASE,
            "token": fake.token,
            "webhook_secret": HOOK_SECRET,
            "enabled": True,
        },
        headers=h,
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "MHVP-SDT-0005"
    out = _configure(client, h, fake)
    text = json.dumps(out)
    assert fake.token not in text
    assert HOOK_SECRET not in text
    assert out["token_set"]
    assert out["token_last4"] == fake.token[-4:]
    assert out["webhook_secret_set"]
    assert out["enabled"]
    assert out["avv_confirmed_by"] == str(world.users["sdtadmin"])
    assert out["webhook_path"].endswith(
        str(world.tenant_a) + "/" + out["webhook_path"].split("/")[-1]
    )
    again = _ok(client.get(f"{C}/config", headers=h))
    assert fake.token not in json.dumps(again)

    # Stored encrypted: the raw column is not the token.
    async def _raw(session: AsyncSession) -> Any:
        from sqlalchemy import text

        return await session.scalar(
            text("SELECT token FROM schadenstool_tenant_config WHERE tenant_id = :t"),
            {"t": world.tenant_a},
        )

    raw = run_tenant(settings, world.tenant_a, _raw)
    assert fake.token.encode() not in bytes(raw)
    tested = _ok(client.post(f"{C}/config/test", headers=h))
    assert tested["last_test_ok"] is True
    assert ("GET", "/api/integrations/hv/v1/tickets") in fake.requests
    good = fake.token
    fake.token = "other"
    bad = _ok(client.post(f"{C}/config/test", headers=h))
    assert bad["last_test_ok"] is False
    assert bad["last_test_message"] == "Token ungültig."
    assert bad["token_invalid"] is True
    assert good not in json.dumps(bad)
    fake.token = good
    _ok(client.post(f"{C}/config/test", headers=h))


def test_roles(client: TestClient, world: World, fake: FakeSchadenstool) -> None:
    care = bearer(login(client, world, "sdtcare"))
    read = bearer(login(client, world, "sdtread"))
    assert client.put(f"{C}/config", json={"enabled": False}, headers=care).status_code == 403
    fake_ticket = uuid.uuid4()
    assert (
        client.post(f"{C}/tickets/{fake_ticket}/handover", json={}, headers=read).status_code == 403
    )
    assert client.get(f"{C}/takeover", headers=read).status_code == 403


def test_outbound_create_comment_attachment_status(
    client: TestClient, world: World, fake: FakeSchadenstool, settings: Settings
) -> None:
    h = _admin(client, world)
    _configure(client, h, fake)
    _, ticket = _property_and_ticket(client, h, "701")
    # First attempt fails (503), the retry sends the same key; one remote ticket, one link.
    fake.fail_next.append((503, {}))
    queued = _ok(
        client.post(
            f"{C}/tickets/{ticket['id']}/handover",
            json={
                "reporter": "Herr Melder",
                "damage_date": "2026-09-27",
                "damage_type": "Leitungswasser",
            },
            headers=h,
        ),
        202,
    )
    assert (
        client.post(f"{C}/tickets/{ticket['id']}/handover", json={}, headers=h).status_code == 409
    )
    first = process(settings, world.tenant_a)
    assert first["retry"] == 1
    assert not fake.tickets

    async def _due(session: AsyncSession) -> None:
        from datetime import UTC, datetime

        for row in (await session.scalars(select(SchadenstoolOutbox))).all():
            row.next_attempt_at = datetime.now(UTC)

    run_tenant(settings, world.tenant_a, _due)
    second = process(settings, world.tenant_a)
    assert second["sent"] == 1
    assert len(fake.tickets) == 1
    remote = next(iter(fake.tickets.values()))
    assert remote["externalId"] == ticket["id"]
    received = remote["received"]
    assert received["objectExternalId"] == "701"
    assert received["damage"] == {"date": "2026-09-27", "type": "Leitungswasser"}
    assert "INTERN" not in json.dumps(received)
    key = f"mhvp-ticket-{ticket['id']}"
    assert fake.keys_seen.count(key) == 2
    panel = _ok(client.get(f"{C}/tickets/{ticket['id']}", headers=h))
    assert panel["linked"]
    assert panel["remote_id"] == remote["id"]
    assert panel["link_id"] == queued["link_id"]

    # Comment: only on explicit push; the webhook later returns it and nothing is imported.
    internal = _ok(
        client.post(
            f"/api/v1/tickets/{ticket['id']}/comments",
            json={"body": "Nur intern", "internal": True},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{C}/tickets/{ticket['id']}/comments",
            json={"body": "Bitte Gutachter schicken"},
            headers=h,
        ),
        202,
    )
    process(settings, world.tenant_a)
    process(settings, world.tenant_a)
    sent_comments = fake.comments[remote["id"]]
    assert [c["message"] for c in sent_comments] == ["Bitte Gutachter schicken"]
    assert all(c["message"] != "Nur intern" for c in sent_comments)
    assert internal["id"]

    # Attachment: explicitly selected document of the ticket.
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "foto.pdf",
                    b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n",
                    "application/pdf",
                )
            },
            data={
                "links": json.dumps(
                    [{"entity_type": "ticket", "entity_id": ticket["id"], "role": "attachment"}]
                )
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{C}/tickets/{ticket['id']}/attachments", json={"document_id": doc["id"]}, headers=h
        ),
        202,
    )
    process(settings, world.tenant_a)
    assert len(fake.attachments[remote["id"]]) == 1
    assert fake.attachments[remote["id"]][0]["externalAttachmentId"] == doc["id"]

    # Status: mapped statuses are queued for PATCH.
    _ok(client.patch(f"/api/v1/tickets/{ticket['id']}", json={"status": "in_progress"}, headers=h))
    process(settings, world.tenant_a)
    assert fake.tickets[remote["id"]]["status"] == "in_progress"

    # Webhook echo: comment and attachment we sent come back, nothing new locally.
    path = _ok(client.get(f"{C}/config", headers=h))["webhook_path"]
    before = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(select(func.count()).select_from(TicketComment)),
    )
    for kind in ("ticket.comment_added", "ticket.attachment_added"):
        r = _webhook(
            client,
            path,
            {
                "eventId": str(uuid.uuid4()),
                "eventType": kind,
                "entityType": "ticket",
                "entityId": remote["id"],
            },
        )
        assert r.status_code == 200, r.text
    result = process(settings, world.tenant_a)
    assert result["events_processed"] == 2
    after = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(select(func.count()).select_from(TicketComment)),
    )
    assert after == before
    links = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(select(func.count()).select_from(SchadenstoolItemLink)),
    )
    assert links == 2

    # Inbound: a remote comment and attachment are applied once, even if the event repeats.
    fake.add_remote_comment(remote["id"], "Gutachter kommt am Montag")
    fake.add_remote_attachment(remote["id"], b"%PDF-1.4\n%%EOF\n")
    event = {
        "eventId": str(uuid.uuid4()),
        "eventType": "ticket.comment_added",
        "entityType": "ticket",
        "entityId": remote["id"],
    }
    assert _webhook(client, path, event).status_code == 200
    assert _webhook(client, path, event).status_code == 200  # duplicate eventId
    process(settings, world.tenant_a)
    _webhook(client, path, {**event, "eventId": str(uuid.uuid4())})
    process(settings, world.tenant_a)
    detail = _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))
    bodies = [c["body"] for c in detail["comments"]]
    assert bodies.count("Gutachter kommt am Montag") == 1
    panel = _ok(client.get(f"{C}/tickets/{ticket['id']}", headers=h))
    inbound = [i for i in panel["items"] if i["direction"] == "inbound"]
    assert {i["kind"] for i in inbound} == {"comment", "attachment"}
    assert next(i for i in inbound if i["kind"] == "comment")["author_name"] == "Frau Gutachter"
    events = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(
            select(func.count()).where(SchadenstoolEvent.event_id == event["eventId"])
        ),
    )
    assert events == 1


def test_webhook_rejections_and_tenant_separation(
    client: TestClient, world: World, fake: FakeSchadenstool, settings: Settings
) -> None:
    h = _admin(client, world)
    _configure(client, h, fake)
    path = _ok(client.get(f"{C}/config", headers=h))["webhook_path"]
    event = {"eventId": str(uuid.uuid4()), "eventType": "ticket.updated", "entityId": "x"}
    assert _webhook(client, path, event, secret="wrong-secret-0123456789").status_code == 401
    assert _webhook(client, path, event, ts=int(time.time()) - 301).status_code == 401
    assert _webhook(client, path, event, signature="sha256=00").status_code == 401
    raw = json.dumps(event).encode()
    assert (
        client.post(path, content=raw, headers={"Content-Type": "application/json"}).status_code
        == 401
    )
    # Path of tenant A with tenant B's id: B has no config with that path id.
    other = path.replace(str(world.tenant_a), str(world.tenant_b))
    assert _webhook(client, other, event).status_code == 404
    # Tenant B cannot see A's links or config.
    hb = _admin(client, world, "sdtadminb")
    assert _ok(client.get(f"{C}/config", headers=hb))["token_set"] is False
    assert _ok(client.get(f"{C}/takeover", headers=hb)) == []
    count_b = run_tenant(
        settings,
        world.tenant_b,
        lambda s: s.scalar(select(func.count()).select_from(SchadenstoolTicketLink)),
    )
    assert count_b == 0


def test_pull_and_takeover(
    client: TestClient, world: World, fake: FakeSchadenstool, settings: Settings
) -> None:
    h = _admin(client, world)
    _configure(client, h, fake)
    prop, ticket = _property_and_ticket(client, h, "702")
    new_remote = fake.add_remote_ticket(objectExternalId="702", title="Sturmschaden Dach")
    match_remote = fake.add_remote_ticket(
        externalId=ticket["id"], objectExternalId="702", status="gutachten_angefordert"
    )
    fake.add_remote_ticket(objectExternalId="999", title="Fremdobjekt")

    async def _pull(session: AsyncSession) -> dict[str, int]:
        return await svc.pull(session, world.tenant_a, blobs=BlobStore(settings), settings=settings)

    counts = run_tenant(settings, world.tenant_a, _pull)
    assert counts["pages"] >= 2  # page size 2: cursor followed
    queue = _ok(client.get(f"{C}/takeover", headers=h))
    by_remote = {q["remote_id"]: q for q in queue}
    assert new_remote["id"] in by_remote
    assert match_remote["id"] in by_remote
    assert by_remote[new_remote["id"]]["proposed_property_id"] == prop["id"]
    assert by_remote[match_remote["id"]]["proposed_ticket_id"] == ticket["id"]
    assert by_remote[match_remote["id"]]["remote_status_label"] == "gutachten_angefordert"
    # No local ticket was created automatically.
    link_count = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(
            select(func.count()).where(SchadenstoolTicketLink.ticket_id.is_not(None))
        ),
    )
    fake.add_remote_comment(match_remote["id"], "Gutachten angefordert")
    linked = _ok(
        client.post(
            f"{C}/takeover/{by_remote[match_remote['id']]['id']}",
            json={"action": "link", "ticket_id": ticket["id"]},
            headers=h,
        )
    )
    assert linked["sync_status"] == "linked"
    assert linked["ticket_id"] == ticket["id"]
    created = _ok(
        client.post(
            f"{C}/takeover/{by_remote[new_remote['id']]['id']}",
            json={"action": "create", "property_id": prop["id"]},
            headers=h,
        )
    )
    assert created["ticket_id"]
    assert created["ticket_id"] != ticket["id"]
    new_ticket = _ok(client.get(f"/api/v1/tickets/{created['ticket_id']}", headers=h))
    assert new_ticket["title"] == "Sturmschaden Dach"
    again = client.post(
        f"{C}/takeover/{by_remote[new_remote['id']]['id']}", json={"action": "dismiss"}, headers=h
    )
    assert again.status_code == 409
    detail = _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))
    assert "Gutachten angefordert" in [c["body"] for c in detail["comments"]]
    after = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(
            select(func.count()).where(SchadenstoolTicketLink.ticket_id.is_not(None))
        ),
    )
    assert after == link_count + 2
    # Second pull with updatedSince: nothing new, no duplicate links.
    run_tenant(settings, world.tenant_a, _pull)
    total = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(select(func.count()).select_from(SchadenstoolTicketLink)),
    )
    fake.add_remote_ticket(objectExternalId="702", title="Neu nach Abgleich")
    run_tenant(settings, world.tenant_a, _pull)
    total2 = run_tenant(
        settings,
        world.tenant_a,
        lambda s: s.scalar(select(func.count()).select_from(SchadenstoolTicketLink)),
    )
    assert total2 == total + 1


def test_disabled_flag_blocks_everything(
    client: TestClient, world: World, fake: FakeSchadenstool, settings: Settings
) -> None:
    h = _admin(client, world)
    _configure(client, h, fake)
    _, ticket = _property_and_ticket(client, h, "703")
    _ok(client.post(f"{C}/tickets/{ticket['id']}/handover", json={}, headers=h), 202)
    path = _ok(client.get(f"{C}/config", headers=h))["webhook_path"]
    _ok(client.put(f"{C}/config", json={"enabled": False}, headers=h))
    fake.requests.clear()
    assert process(settings, world.tenant_a)["sent"] == 0

    async def _pull(session: AsyncSession) -> dict[str, int]:
        return await svc.pull(session, world.tenant_a)

    assert run_tenant(settings, world.tenant_a, _pull)["pages"] == 0
    assert fake.requests == []
    blocked = client.post(f"{C}/tickets/{ticket['id']}/comments", json={"body": "x"}, headers=h)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "MHVP-SDT-0001"
    event = {"eventId": str(uuid.uuid4()), "eventType": "ticket.updated", "entityId": "x"}
    assert _webhook(client, path, event).status_code == 404
    _, other = _property_and_ticket(client, h, "704")
    assert client.post(f"{C}/tickets/{other['id']}/handover", json={}, headers=h).status_code == 409

    # Jobs see no enabled tenant A.
    async def _enabled() -> list[uuid.UUID]:
        engine = create_async_engine(settings.database_url.get_secret_value(), poolclass=NullPool)
        try:
            return await sdt_tasks.enabled_tenants(create_session_factory(engine))
        finally:
            await engine.dispose()

    assert world.tenant_a not in asyncio.run(_enabled())
    _configure(client, h, fake)  # leave enabled for other tests running later


def test_rate_limit_and_invalid_token_in_queue(
    client: TestClient, world: World, fake: FakeSchadenstool, settings: Settings
) -> None:
    h = _admin(client, world)
    _configure(client, h, fake)
    _, ticket = _property_and_ticket(client, h, "705")
    process(settings, world.tenant_a)  # rows left by earlier tests go first
    _ok(client.post(f"{C}/tickets/{ticket['id']}/handover", json={}, headers=h), 202)
    fake.fail_next.append((429, {"Retry-After": "600"}))
    before = time.time()
    assert process(settings, world.tenant_a)["retry"] >= 1

    async def _row(session: AsyncSession) -> Any:
        return (
            await session.scalars(
                select(SchadenstoolOutbox).where(
                    SchadenstoolOutbox.idempotency_key == f"mhvp-ticket-{ticket['id']}"
                )
            )
        ).one()

    row = run_tenant(settings, world.tenant_a, _row)
    assert row.last_status_code == 429
    assert row.next_attempt_at.timestamp() - before >= 590

    async def _due(session: AsyncSession) -> None:
        from datetime import UTC, datetime

        for r in (await session.scalars(select(SchadenstoolOutbox))).all():
            r.next_attempt_at = datetime.now(UTC)

    # 401 marks the connection "Token ungültig" and stops the queue until a new token.
    run_tenant(settings, world.tenant_a, _due)
    good = fake.token
    fake.token = "revoked"
    process(settings, world.tenant_a)
    cfg = _ok(client.get(f"{C}/config", headers=h))
    assert cfg["token_invalid"] is True
    panel = _ok(client.get(f"{C}/tickets/{ticket['id']}", headers=h))
    assert panel["token_invalid"] is True
    fake.requests.clear()
    process(settings, world.tenant_a)
    assert fake.requests == []
    fake.token = good
    _configure(client, h, fake)
    assert _ok(client.get(f"{C}/config", headers=h))["token_invalid"] is False
    assert process(settings, world.tenant_a)["sent"] >= 1
