"""T12 (S15-06 Rest, M20-02 Rest, R09-02): own AI task ``reply_draft`` with provider schema,
approval and tenant separation; rule action ``set_record_field`` for work orders (status,
appointment, assignee of the ticket) and documents (category, property link). Fake provider,
no network.

Expected values by hand: without a released provider nothing is stored; with one, exactly one
run and an unapproved draft; the approval sets user and time once; the order flow draft ->
requested is allowed, requested -> in_progress is not (ORDER_FLOW needs approval first)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import ValidationError

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m7_ai import BUCKET, PROVIDER, FakeProvider, _settings, _upload, fake
from tests.integration.test_q11_workspace_w3 import _contact, _property, _with_session

pytestmark = pytest.mark.integration
__all__ = ["fake"]
M = "/api/v1/mail"
DRAFT = {
    "body": "{anrede}, vielen Dank für Ihre Nachricht zu {objekt}. Wir melden uns {kontakt}.",
    "tone": "freundlich",
    "placeholders": ["{anrede}", "{objekt}"],
    "open_questions": ["Termin abstimmen"],
}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"t12a-{RUN}", name=f"T12 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t12b-{RUN}", name=f"T12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("t12admin", a, "tenant_admin"),
            ("t12second", a, "tenant_admin"),
            ("t12reader", a, "read_only"),
            ("t12other", b, "tenant_admin"),
        ):
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _ingest(c: TestClient, h: dict[str, str], tag: str) -> dict[str, Any]:
    from tests.integration.test_m20_suggest import _eml

    raw = _eml(
        f"t12-{tag}-{RUN}@example.com",
        f"Heizung {tag} {RUN}",
        f"<t12-{tag}-{RUN}@x>",
        "Heizung kalt.",
    )
    doc = _upload(c, h, "t12.eml", raw, "message/rfc822")
    return _ok(c.post(f"{M}/ingest", json={"document_id": doc}, headers=h), 201)


def _release(c: TestClient, world: World) -> None:
    admin = bearer(login(c, world, "t12admin"))
    second = bearer(login(c, world, "t12second"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=admin,
        )
    )
    _ok(c.post("/api/v1/ai/providers/anthropic/release", headers=second))


# Unit ----------------------------------------------------------------------------------------


def test_reply_task_schema_and_payload() -> None:
    from mhvp.ai import tasks
    from mhvp.ai.models import AiTask
    from mhvp.communication.suggest import reply_task_payload

    assert tasks.SCHEMAS[AiTask.REPLY_DRAFT] is tasks.ReplyDraftResult
    assert tasks.SCHEMAS[AiTask.DRAFT_REPLY] is tasks.PlaybookDraft  # playbook draft unchanged
    assert tasks.prompt(AiTask.REPLY_DRAFT).version == "v1"
    assert "body" in tasks.json_schema(AiTask.REPLY_DRAFT)["properties"]
    payload = reply_task_payload(DRAFT, {"tone": "formell", "rules": "Immer siezen."}, model="m")
    assert payload is not None
    assert payload["tone"] == "freundlich"
    assert payload["style_tone"] == "formell"
    assert payload["style_rules"] == "Immer siezen."
    assert payload["placeholders"] == ["{anrede}", "{objekt}"]
    assert payload["unknown_placeholders"] == ["{kontakt}"]
    assert payload["approved"] is False
    assert reply_task_payload({"body": "  "}, None, model=None) is None


def test_record_field_action_closed_list() -> None:
    from mhvp.automation.schemas import parse_actions

    uid = str(uuid.uuid4())
    for ok in (
        {
            "type": "set_record_field",
            "target": "work_order",
            "field": "status",
            "value": "requested",
        },
        {
            "type": "set_record_field",
            "target": "work_order",
            "field": "assignee_user_id",
            "value": uid,
        },
        {
            "type": "set_record_field",
            "target": "work_order",
            "field": "scheduled_at",
            "value": "2026-10-05T09:00:00+02:00",
        },
        {"type": "set_record_field", "target": "document", "field": "category_id", "value": uid},
        {
            "type": "set_record_field",
            "target": "document",
            "field": "property_id",
            "value": "{entity.property_id}",
        },
    ):
        assert parse_actions([ok])[0].type == "set_record_field"  # type: ignore[union-attr]
    for bad in (
        {
            "type": "set_record_field",
            "target": "work_order",
            "field": "status",
            "value": "approved",
        },
        {
            "type": "set_record_field",
            "target": "work_order",
            "field": "status",
            "value": "cancelled",
        },
        {"type": "set_record_field", "target": "work_order", "field": "quote_amount", "value": "1"},
        {
            "type": "set_record_field",
            "target": "work_order",
            "field": "scheduled_at",
            "value": "2026-10-05T09:00:00",
        },
        {
            "type": "set_record_field",
            "target": "document",
            "field": "retention_until",
            "value": "x",
        },
        {"type": "set_record_field", "target": "document", "field": "category_id", "value": "kein"},
        {"type": "set_record_field", "target": "contact", "field": "notes", "value": "x"},
    ):
        with pytest.raises((ValidationError, ValueError)):
            parse_actions([bad])


# AI task reply_draft -------------------------------------------------------------------------


def test_reply_draft_task_approval_permissions_and_tenant(
    client: TestClient, world: World, fake: FakeProvider, migrator_engine: Any
) -> None:
    admin = bearer(login(client, world, "t12admin"))
    reader = bearer(login(client, world, "t12reader"))
    other = bearer(login(client, world, "t12other"))
    msg = _ingest(client, admin, "a")
    url = f"{M}/messages/{msg['id']}/reply-ai"

    # No released provider: skipped, nothing stored, compact keeps the template.
    skipped = _ok(client.post(url, headers=admin))
    assert skipped["status"] in {"skipped", "failed"}
    zero = {"draft_hash": "0" * 64}
    assert client.post(f"{url}/approve", headers=admin, json=zero).status_code == 404
    assert (
        _ok(client.get(f"{M}/messages/{msg['id']}/compact", headers=admin))["reply"]["source"]
        == "template"
    )

    # Permissions, tenant separation, validation.
    assert client.post(url, headers=reader).status_code == 403
    assert client.post(f"{url}/approve", headers=reader, json=zero).status_code == 403
    assert client.post(url, headers=other).status_code == 404
    assert client.post(f"{M}/messages/not-a-uuid/reply-ai", headers=admin).status_code == 422

    _release(client, world)
    fake.queue.append(DRAFT)
    calls = len(fake.calls)
    done = _ok(client.post(url, headers=admin))
    assert done["status"] == "ready"
    assert len(fake.calls) == calls + 1
    assert done["approved"] is False
    assert done["unknown_placeholders"] == ["{kontakt}"]
    sent = fake.calls[-1]["messages"][-1]["content"]
    assert "Stilvorgaben des Postfachs" in sent
    assert fake.calls[-1]["schema"]["title"] == "ReplyDraftResult" or "body" in str(
        fake.calls[-1]["schema"]
    )

    compact = _ok(client.get(f"{M}/messages/{msg['id']}/compact", headers=admin))
    assert compact["reply"]["source"] == "reply_task"
    assert compact["reply"]["approved"] is False
    assert compact["reply"]["draft"]["open_questions"] == ["Termin abstimmen"]

    seen = compact["reply"]["draft_hash"]
    assert seen == done["draft_hash"]
    # U15-01: missing or malformed hash is 422, a hash of another draft is 409.
    assert client.post(f"{url}/approve", headers=admin).status_code == 422
    assert client.post(f"{url}/approve", headers=admin, json={"draft_hash": "x"}).status_code == 422
    stale = client.post(f"{url}/approve", headers=admin, json=zero)
    assert stale.status_code == 409
    assert stale.json()["code"] == "MHVP-COMM-0010"
    approved = _ok(client.post(f"{url}/approve", headers=admin, json={"draft_hash": seen}))
    assert approved["approved"] is True
    assert approved["approved_by"] == str(world.users["t12admin"])
    first_time = approved["approved_at"]
    again = client.post(f"{url}/approve", headers=admin, json={"draft_hash": seen})
    assert _ok(again)["approved_at"] == first_time
    assert (
        _ok(client.get(f"{M}/messages/{msg['id']}/compact", headers=admin))["reply"]["approved"]
        is True
    )
    # A new draft resets the approval; the mail is never sent by this path.
    fake.queue.append(DRAFT)
    assert _ok(client.post(url, headers=admin))["approved"] is False
    # U15-01: a parallel regeneration with other content (simulated in the store) makes the
    # hash the approver has seen stale: 409.
    from sqlalchemy import text

    with migrator_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        conn.execute(
            text(
                "UPDATE message SET suggestion = jsonb_set(suggestion, '{reply_ai,body}',"
                " to_jsonb('Anderer Entwurf'::text)) WHERE id = :i"
            ),
            {"i": msg["id"]},
        )
    assert (
        client.post(f"{url}/approve", headers=admin, json={"draft_hash": seen}).status_code == 409
    )
    assert _ok(client.get(f"{M}/messages/{msg['id']}", headers=admin))["status"] != "sent"


# Rule action set_record_field ----------------------------------------------------------------


def test_set_record_field_work_order_and_document(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from sqlalchemy import select

    from mhvp.automation.models import AutomationRule
    from mhvp.automation.schemas import SetRecordFieldAction
    from mhvp.automation.services import ActionError, _set_record_field
    from mhvp.documents.models import (
        Document,
        DocumentCategory,
        DocumentLink,
        DocumentSource,
        StorageKind,
        TextStatus,
    )
    from mhvp.tickets.models import OrderStatus, Ticket, WorkOrder, WorkOrderEvent

    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "t12admin"))
    prop = _property(client, admin, "962")
    provider = _contact(client, admin, "T12 Dienstleister")
    property_id = uuid.UUID(prop["id"])
    assignee = world.users["t12second"]
    when = "2026-10-05T09:00:00+02:00"

    async def run(session: Any) -> dict[str, Any]:
        rule = AutomationRule(
            tenant_id=world.tenant_a,
            name="T12 Regel",
            trigger_kind="event",
            trigger_event_type="work_order.requested",
            conditions={},
            actions=[],
        )
        ticket = Ticket(
            tenant_id=world.tenant_a,
            number=uuid.uuid4().int % 1_000_000_000,
            category="damage",
            title="T12 Heizung",
            property_id=property_id,
        )
        session.add_all([rule, ticket])
        await session.flush()
        order = WorkOrder(
            tenant_id=world.tenant_a,
            ticket_id=ticket.id,
            property_id=property_id,
            provider_contact_id=uuid.UUID(provider["id"]),
            description="Heizung prüfen",
            status=OrderStatus.DRAFT,
        )
        doc = Document(
            tenant_id=world.tenant_a,
            title="T12 Beleg",
            filename="t12.pdf",
            mime_type="application/pdf",
            size=1,
            sha256="e" * 64,
            storage=StorageKind.MINIO,
            storage_ref=f"t12-{RUN}",
            text_status=TextStatus.NONE,
            source=DocumentSource.UPLOAD,
            visibility=[],
        )
        held = Document(
            tenant_id=world.tenant_a,
            title="T12 Sperre",
            filename="t12h.pdf",
            mime_type="application/pdf",
            size=1,
            sha256="f" * 64,
            storage=StorageKind.MINIO,
            storage_ref=f"t12h-{RUN}",
            text_status=TextStatus.NONE,
            source=DocumentSource.UPLOAD,
            visibility=[],
            retention_hold_reason="Verfahren",
        )
        cat = DocumentCategory(tenant_id=world.tenant_a, code=f"t12_{RUN}"[:60], name="T12")
        session.add_all([order, doc, held, cat])
        await session.flush()
        event_id = uuid.uuid4()

        async def act(target: str, field: str, value: str, entity: Any, dry: bool = False) -> Any:
            ctx = {"entity_type": target, "entity_id": str(entity.id), "entity": {}}
            return await _set_record_field(
                session,
                tenant_id=world.tenant_a,
                rule=rule,
                event_id=event_id,
                action=SetRecordFieldAction(
                    type="set_record_field", target=target, field=field, value=value
                ),
                context=ctx,
                dry_run=dry,
            )

        out: dict[str, Any] = {}
        await act("work_order", "status", "requested", order, dry=True)
        out["dry_status"] = order.status
        await act("work_order", "status", "requested", order)
        out["status"] = order.status
        out["again"] = (await act("work_order", "status", "requested", order))["detail"]
        try:
            await act("work_order", "status", "in_progress", order)
            out["skip_flow"] = "no error"
        except ActionError:
            out["skip_flow"] = "error"
        events = list(
            await session.scalars(
                select(WorkOrderEvent).where(WorkOrderEvent.work_order_id == order.id)
            )
        )
        out["events"] = [(e.from_status, e.to_status, e.user_id) for e in events]
        await act("work_order", "scheduled_at", when, order)
        out["scheduled"] = order.scheduled_at
        await act("work_order", "assignee_user_id", str(assignee), order)
        await session.refresh(ticket)
        out["assignee"] = ticket.assignee_user_id
        try:
            await act("work_order", "assignee_user_id", str(uuid.uuid4()), order)
            out["stranger"] = "no error"
        except ActionError:
            out["stranger"] = "error"
        # wrong event entity
        try:
            await act("work_order", "status", "requested", ticket)
            out["wrong"] = "no error"
        except ActionError:
            out["wrong"] = "error"
        await act("document", "category_id", str(cat.id), doc)
        out["category"] = doc.category_id
        try:
            await act("document", "category_id", str(cat.id), held)
            out["held"] = "no error"
        except ActionError:
            out["held"] = "error"
        await act("document", "property_id", str(property_id), doc)
        out["again_link"] = (await act("document", "property_id", str(property_id), doc))["detail"]
        links = list(
            await session.scalars(select(DocumentLink).where(DocumentLink.document_id == doc.id))
        )
        out["links"] = [(link.entity_type, link.entity_id) for link in links]
        out["ids"] = (cat.id, order.id)
        return out

    out = asyncio.run(_with_session(settings, world.tenant_a, run))
    assert out["dry_status"] is OrderStatus.DRAFT
    assert out["status"] is OrderStatus.REQUESTED
    assert out["again"] == "Status bereits gesetzt."
    assert out["skip_flow"] == "error"
    assert out["events"] == [("draft", "requested", None)]
    assert out["scheduled"] == datetime(2026, 10, 5, 7, 0, tzinfo=UTC)
    assert out["assignee"] == assignee
    assert out["stranger"] == "error"
    assert out["wrong"] == "error"
    assert out["category"] == out["ids"][0]
    assert out["held"] == "error"
    assert out["again_link"] == "Verknüpfung besteht bereits."
    assert out["links"] == [("property", property_id)]
