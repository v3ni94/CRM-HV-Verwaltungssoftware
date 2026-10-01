"""Q11 (Welle 3): calendar entry of work order appointments (M19-06), notification
preferences (M23-04), bulk actions for documents and deadline tasks (M9-04), rule actions
``set_field`` and ``notify_provider`` (S15-06) and the receipt draft from an accepted invoice
submission (M22-02). Other tenant: 404, missing permission: 403, bad body: 422."""

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q11a-{RUN}", name=f"Q11 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q11b-{RUN}", name=f"Q11 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("q11admin", a, "tenant_admin"),
            ("q11care", a, "caretaker"),
            ("q11other", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


async def _with_session(settings: Any, tenant_id: uuid.UUID, fn: Any) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            return await fn(session)
    finally:
        await engine.dispose()


def _property(client: TestClient, headers: dict[str, str], number: str) -> dict[str, Any]:
    return _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Q11 Haus {number} {RUN}",
                "management_type": "rental",
                "city": "Monheim am Rhein",
            },
            headers=headers,
        ),
        201,
    )


def _contact(client: TestClient, headers: dict[str, str], name: str) -> dict[str, Any]:
    return _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"{name} {RUN}"},
            headers=headers,
        ),
        201,
    )


# Unit ----------------------------------------------------------------------------------------


def test_resolve_preferences_defaults_mute_and_mandatory() -> None:
    from mhvp.workspace.models import NotificationPreference as Pref
    from mhvp.workspace.notification_prefs import MANDATORY_KINDS, resolve

    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    assert resolve([], "ticket_assigned", now).in_app is True
    assert resolve([], "ticket_assigned", now).email is False
    own = Pref(kind="ticket_assigned", in_app=False, email=True, muted_until=None)
    default = Pref(kind="*", in_app=True, email=False, muted_until=now + timedelta(hours=1))
    only_mail = resolve([own], "ticket_assigned", now)
    assert (only_mail.in_app, only_mail.email) == (False, True)
    muted = resolve([own, default], "ticket_assigned", now)
    assert (muted.in_app, muted.email) == (False, False)
    # the mute has ended one hour later
    later = resolve([default], "ticket_assigned", now + timedelta(hours=2))
    assert later.in_app is True
    for kind in MANDATORY_KINDS:
        assert resolve([own, default], kind, now).in_app is True


def test_rule_action_schemas_closed_field_list() -> None:
    from mhvp.automation.schemas import parse_actions

    ok = parse_actions(
        [{"type": "set_field", "target": "property", "field": "notes", "value": "x"}]
    )
    assert ok[0].type == "set_field"  # type: ignore[union-attr]
    for bad in (
        {"type": "set_field", "target": "contract", "field": "end_date", "value": "x"},
        {"type": "set_field", "target": "contact", "field": "iban", "value": "x"},
        {"type": "set_field", "target": "property", "field": "notes", "value": ""},
    ):
        with pytest.raises((ValidationError, ValueError)):
            parse_actions([bad])
    with pytest.raises((ValidationError, ValueError)):
        parse_actions([{"type": "notify_provider", "subject": "s", "body": "b"}])
    parsed = parse_actions(
        [{"type": "notify_provider", "contract_type_code": "heating", "subject": "s", "body": "b"}]
    )
    assert parsed[0].type == "notify_provider"  # type: ignore[union-attr]


# M23-04 notification preferences -------------------------------------------------------------


def test_notification_preferences_api_and_notify(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.workspace.models import Notification
    from mhvp.workspace.services import notify

    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "q11admin"))
    care = bearer(login(client, world, "q11care"))
    current = _ok(client.get(f"{W}/notification-preferences", headers=admin))
    kinds = {i["kind"]: i for i in current["items"]}
    assert kinds["*"]["in_app"] is True
    assert kinds["*"]["email"] is False
    assert kinds["sla_escalation"]["mandatory"] is True

    # Validation: mandatory kinds cannot be switched, unknown kinds and past mutes are 422.
    def put(items: list[dict[str, Any]], headers: dict[str, str]) -> Any:
        return client.put(f"{W}/notification-preferences", json={"items": items}, headers=headers)

    assert put([{"kind": "sla_escalation", "in_app": False}], admin).status_code == 422
    assert put([{"kind": "gibt_es_nicht"}], admin).status_code == 422
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert put([{"kind": "*", "muted_until": past}], admin).status_code == 422
    assert put([], admin).status_code == 422

    saved = _ok(
        put(
            [
                {"kind": "ticket_assigned", "in_app": False, "email": True},
                {"kind": "automation", "in_app": True, "email": True},
            ],
            admin,
        )
    )
    by_kind = {i["kind"]: i for i in saved["items"]}
    assert by_kind["ticket_assigned"]["in_app"] is False
    assert by_kind["automation"]["email"] is True
    # Own settings only: the caretaker of the same tenant still sees the defaults.
    care_kinds = {
        i["kind"]: i
        for i in _ok(client.get(f"{W}/notification-preferences", headers=care))["items"]
    }
    assert care_kinds["ticket_assigned"]["in_app"] is True

    admin_id = world.users["q11admin"]
    care_id = world.users["q11care"]

    async def run(session: Any) -> dict[str, Any]:
        entity = uuid.uuid4()
        mail_only = await notify(
            session,
            tenant_id=world.tenant_a,
            user_id=admin_id,
            kind="ticket_assigned",
            title="Nur Mail",
            entity_type="ticket",
            entity_id=entity,
        )
        repeated = await notify(
            session,
            tenant_id=world.tenant_a,
            user_id=admin_id,
            kind="ticket_assigned",
            title="Nur Mail",
            entity_type="ticket",
            entity_id=entity,
        )
        both = await notify(
            session,
            tenant_id=world.tenant_a,
            user_id=admin_id,
            kind="automation",
            title="Beides",
        )
        default = await notify(
            session,
            tenant_id=world.tenant_a,
            user_id=care_id,
            kind="ticket_assigned",
            title="Standard",
        )
        return {
            "mail_only": (mail_only.read_at is not None, mail_only.email_pending),
            "repeated": repeated,
            "both": (both.read_at is None, both.email_pending),
            "default": (default.read_at is None, default.email_pending),
        }

    result = asyncio.run(_with_session(settings, world.tenant_a, run))
    assert result["mail_only"] == (True, True)  # created read (bell quiet), mail requested
    assert result["repeated"] is None  # no second mail for the same subject within a day
    assert result["both"] == (True, True)
    assert result["default"] == (True, False)

    # Mute of the admin: nothing is written for non mandatory kinds, mandatory ones stay.
    until = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    _ok(put([{"kind": "*", "muted_until": until}], admin))

    async def muted(session: Any) -> tuple[Any, Any]:
        quiet = await notify(
            session,
            tenant_id=world.tenant_a,
            user_id=admin_id,
            kind="maintenance_due",
            title="Still",
        )
        loud = await notify(
            session,
            tenant_id=world.tenant_a,
            user_id=admin_id,
            kind="compliance_deadline",
            title="Frist",
        )
        return quiet, loud.kind if loud else None

    quiet, loud = asyncio.run(_with_session(settings, world.tenant_a, muted))
    assert quiet is None
    assert loud == "compliance_deadline"

    # Sending the requested mails: a failing transport keeps them pending, success marks them.
    from mhvp.workspace import notification_prefs

    async def send(session: Any, error: str | None) -> dict[str, int]:
        import mhvp.sla.channels as channels

        async def fake(*_a: Any, **_k: Any) -> str | None:
            return error

        original = channels.send_email
        channels.send_email = fake  # type: ignore[assignment]
        try:
            return await notification_prefs.send_pending_mails(session, settings, world.tenant_a)
        finally:
            channels.send_email = original  # type: ignore[assignment]

    failed = asyncio.run(
        _with_session(settings, world.tenant_a, lambda s: send(s, "kein Postfach"))
    )
    assert failed["failed"] >= 2
    assert failed["sent"] == 0
    sent = asyncio.run(_with_session(settings, world.tenant_a, lambda s: send(s, None)))
    assert sent["sent"] >= 2
    again = asyncio.run(_with_session(settings, world.tenant_a, lambda s: send(s, None)))
    assert again["sent"] == 0

    async def pending(session: Any) -> int:
        rows = await session.scalars(
            select(Notification).where(
                Notification.email_pending.is_(True), Notification.email_sent_at.is_(None)
            )
        )
        return len(rows.all())

    assert asyncio.run(_with_session(settings, world.tenant_a, pending)) == 0
    # Tenant separation: the other tenant sees its own defaults only.
    other = bearer(login(client, world, "q11other"))
    other_kinds = {
        i["kind"]: i
        for i in _ok(client.get(f"{W}/notification-preferences", headers=other))["items"]
    }
    assert other_kinds["ticket_assigned"]["in_app"] is True
    assert client.get(f"{W}/notification-preferences").status_code == 401


# M9-04 bulk actions --------------------------------------------------------------------------


def test_bulk_documents_and_deadline_tasks(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.documents.models import (
        Document,
        DocumentCategory,
        DocumentLink,
        DocumentSource,
        StorageKind,
        TextStatus,
    )
    from mhvp.workspace.models import DeadlineEntry, DeadlineType

    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "q11admin"))
    care = bearer(login(client, world, "q11care"))
    other = bearer(login(client, world, "q11other"))
    prop = _property(client, admin, "961")
    _ok(client.get(f"{W}/deadline-types", headers=admin))  # seeds the system types

    async def seed(session: Any) -> dict[str, Any]:
        docs = []
        for n in range(2):
            d = Document(
                tenant_id=world.tenant_a,
                title=f"Q11 Beleg {n} {RUN}",
                filename=f"q11-{n}.pdf",
                mime_type="application/pdf",
                size=10,
                sha256=f"{n}" * 64,
                storage=StorageKind.MINIO,
                storage_ref=f"q11-{RUN}-{n}",
                text_status=TextStatus.NONE,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            session.add(d)
            docs.append(d)
        cat = DocumentCategory(
            tenant_id=world.tenant_a, code=f"q11_{RUN}"[:60], name="Q11 Kategorie"
        )
        session.add(cat)
        dtype = await session.scalar(select(DeadlineType).limit(1))
        entries = []
        for n in range(2):
            e = DeadlineEntry(
                tenant_id=world.tenant_a,
                type_id=dtype.id,
                title=f"Q11 Frist {n}",
                trigger_on=date(2026, 9, 30),
                due_on=date(2026, 12, 31),
                source_type="ticket",
                source_id=uuid.uuid4(),
            )
            session.add(e)
            entries.append(e)
        await session.flush()
        return {
            "docs": [d.id for d in docs],
            "cat": cat.id,
            "entries": [e.id for e in entries],
        }

    ids = asyncio.run(_with_session(settings, world.tenant_a, seed))
    docs = [str(i) for i in ids["docs"]]

    def bulk(body: dict[str, Any], headers: dict[str, str]) -> Any:
        return client.post(f"{W}/bulk", json=body, headers=headers)

    cat_body = {"action": "documents.set_category", "ids": docs, "category_id": str(ids["cat"])}
    assert _ok(bulk(cat_body, admin)) == {
        "action": "documents.set_category",
        "requested": 2,
        "changed": 2,
    }
    assert _ok(bulk(cat_body, admin))["changed"] == 0  # idempotent
    link_body = {"action": "documents.link_property", "ids": docs, "property_id": prop["id"]}
    assert _ok(bulk(link_body, admin))["changed"] == 2
    assert _ok(bulk(link_body, admin))["changed"] == 0

    async def verify(session: Any) -> tuple[int, int]:
        categorised = len(
            (
                await session.scalars(select(Document.id).where(Document.category_id == ids["cat"]))
            ).all()
        )
        linked = len(
            (
                await session.scalars(
                    select(DocumentLink.id).where(
                        DocumentLink.entity_type == "property",
                        DocumentLink.entity_id == uuid.UUID(prop["id"]),
                    )
                )
            ).all()
        )
        return categorised, linked

    assert asyncio.run(_with_session(settings, world.tenant_a, verify)) == (2, 2)

    # Validation, all or nothing, permission and tenant separation.
    assert bulk({"action": "documents.set_category", "ids": docs}, admin).status_code == 422
    assert bulk({"action": "documents.link_property", "ids": docs}, admin).status_code == 422
    unknown = {**cat_body, "ids": [*docs, str(uuid.uuid4())]}
    assert bulk(unknown, admin).status_code == 404
    assert bulk({**cat_body, "category_id": str(uuid.uuid4())}, admin).status_code == 404
    assert bulk({**link_body, "property_id": str(uuid.uuid4())}, admin).status_code == 404
    assert bulk(cat_body, other).status_code == 404  # documents of another tenant are unknown
    assert bulk(cat_body, care).status_code == 403

    entries = [str(i) for i in ids["entries"]]
    done = {"action": "deadline_entries.done", "ids": entries}
    assert bulk(done, care).status_code in (200, 403)  # caretaker may hold tickets:update
    assert bulk({**done, "ids": [*entries, str(uuid.uuid4())]}, admin).status_code == 404
    result = _ok(bulk(done, admin))
    assert result["requested"] == 2
    assert result["changed"] in (0, 2)
    assert _ok(bulk(done, admin))["changed"] == 0
    assert bulk(done, other).status_code == 404


# M19-06 calendar entry of the work order appointment -----------------------------------------


def test_work_order_appointment_calendar_entry(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.tickets.models import OrderStatus, WorkOrder
    from mhvp.workspace.models import CalendarEntry
    from mhvp.workspace.tasks import deadlines_once

    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "q11admin"))
    prop = _property(client, admin, "962")
    provider = _contact(client, admin, "Handwerker")
    scheduled = datetime(2026, 10, 6, 7, 30, tzinfo=UTC)  # 09:30 local time (CEST)

    async def seed(session: Any) -> uuid.UUID:
        order = WorkOrder(
            tenant_id=world.tenant_a,
            property_id=uuid.UUID(prop["id"]),
            provider_contact_id=uuid.UUID(provider["id"]),
            description="Heizung warten",
            status=OrderStatus.SCHEDULED,
            scheduled_at=scheduled,
        )
        session.add(order)
        await session.flush()
        return order.id

    order_id = asyncio.run(_with_session(settings, world.tenant_a, seed))
    today = date(2026, 9, 30)
    first = asyncio.run(deadlines_once(settings, today))
    assert first["calendar_created"] >= 1
    assert asyncio.run(deadlines_once(settings, today))["calendar_created"] == 0

    async def entries(session: Any) -> list[CalendarEntry]:
        return list(
            (
                await session.scalars(
                    select(CalendarEntry).where(CalendarEntry.source_id == order_id)
                )
            ).all()
        )

    rows = asyncio.run(_with_session(settings, world.tenant_a, entries))
    assert len(rows) == 1
    entry = rows[0]
    assert (entry.category, entry.source_type) == ("work_order_appointment", "work_order")
    assert entry.starts_on == date(2026, 10, 6)
    assert "09:30" in entry.title
    assert entry.owner_user_id is None
    assert entry.shared is True

    # The appointment moves: the entry follows; once the order is done it disappears.
    async def move(session: Any) -> None:
        order = await session.get(WorkOrder, order_id)
        order.scheduled_at = scheduled + timedelta(days=2)

    asyncio.run(_with_session(settings, world.tenant_a, move))
    asyncio.run(deadlines_once(settings, today))
    assert asyncio.run(_with_session(settings, world.tenant_a, entries))[0].starts_on == date(
        2026, 10, 8
    )

    async def finish(session: Any) -> None:
        order = await session.get(WorkOrder, order_id)
        order.status = OrderStatus.DONE

    asyncio.run(_with_session(settings, world.tenant_a, finish))
    asyncio.run(deadlines_once(settings, today))
    assert asyncio.run(_with_session(settings, world.tenant_a, entries)) == []


# S15-06 rule actions -------------------------------------------------------------------------


def test_rule_action_set_field_and_notify_provider(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.automation.models import AutomationRule
    from mhvp.automation.schemas import NotifyProviderAction, SetFieldAction
    from mhvp.automation.services import ActionError, _notify_provider, _set_field
    from mhvp.communication.models import Message
    from mhvp.contacts.models import Contact
    from mhvp.properties.models import Property, ServiceProviderRelation
    from mhvp.tickets.models import Ticket

    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "q11admin"))
    prop = _property(client, admin, "963")
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Heizung GmbH {RUN}",
                "emails": [{"email": f"heizung-{RUN}@example.org", "is_primary": True}],
            },
            headers=admin,
        ),
        201,
    )
    property_id = uuid.UUID(prop["id"])
    event_id = uuid.uuid4()

    async def run(session: Any) -> dict[str, Any]:
        rule = AutomationRule(
            tenant_id=world.tenant_a,
            name="Q11 Regel",
            trigger_kind="event",
            trigger_event_type="ticket.created",
            conditions={},
            actions=[],
        )
        session.add(rule)
        ticket = Ticket(
            tenant_id=world.tenant_a,
            number=uuid.uuid4().int % 1_000_000_000,
            category="damage",
            title="Heizung fällt aus",
            property_id=property_id,
        )
        session.add(ticket)
        await session.flush()
        ctx = {
            "entity_type": "ticket",
            "entity_id": str(ticket.id),
            "entity": {"title": ticket.title},
        }
        out: dict[str, Any] = {}
        # dry run changes nothing
        action = SetFieldAction(
            type="set_field", target="property", field="notes", value="Ausfall {entity.title}"
        )
        dry = await _set_field(
            session,
            tenant_id=world.tenant_a,
            rule=rule,
            event_id=event_id,
            action=action,
            context=ctx,
            dry_run=True,
        )
        out["dry"] = dry["ok"]
        prop_row = await session.get(Property, property_id)
        out["after_dry"] = prop_row.notes
        first = await _set_field(
            session,
            tenant_id=world.tenant_a,
            rule=rule,
            event_id=event_id,
            action=action,
            context=ctx,
            dry_run=False,
        )
        out["first"] = first["ok"]
        await session.refresh(prop_row)
        out["notes1"] = prop_row.notes
        second_action = action.model_copy(update={"value": "Zweite Zeile"})
        await _set_field(
            session,
            tenant_id=world.tenant_a,
            rule=rule,
            event_id=event_id,
            action=second_action,
            context=ctx,
            dry_run=False,
        )
        await session.refresh(prop_row)
        out["notes2"] = prop_row.notes
        # a contract needs a contract event
        try:
            await _set_field(
                session,
                tenant_id=world.tenant_a,
                rule=rule,
                event_id=event_id,
                action=SetFieldAction(
                    type="set_field", target="contract", field="notes", value="x"
                ),
                context=ctx,
                dry_run=False,
            )
            out["contract"] = "no error"
        except ActionError:
            out["contract"] = "error"
        # contact of the ticket: none, therefore no target
        try:
            await _set_field(
                session,
                tenant_id=world.tenant_a,
                rule=rule,
                event_id=event_id,
                action=SetFieldAction(type="set_field", target="contact", field="notes", value="x"),
                context=ctx,
                dry_run=False,
            )
            out["contact"] = "no error"
        except ActionError:
            out["contact"] = "error"

        # notify_provider: no relation yet -> error; with relation -> draft, never sent
        provider_action = NotifyProviderAction(
            type="notify_provider",
            contract_type_code="heating",
            subject="Störung {entity.title}",
            body="Bitte melden Sie sich.",
        )
        try:
            await _notify_provider(
                session,
                tenant_id=world.tenant_a,
                rule=rule,
                action=provider_action,
                context=ctx,
                dry_run=False,
            )
            out["no_relation"] = "no error"
        except ActionError:
            out["no_relation"] = "error"
        session.add(
            ServiceProviderRelation(
                tenant_id=world.tenant_a,
                property_id=property_id,
                contact_id=uuid.UUID(provider["id"]),
                contract_type_code="heating",
                valid_from=date(2020, 1, 1),
            )
        )
        await session.flush()
        result = await _notify_provider(
            session,
            tenant_id=world.tenant_a,
            rule=rule,
            action=provider_action,
            context=ctx,
            dry_run=False,
        )
        draft = await session.get(Message, uuid.UUID(result["entity_id"]))
        out["draft"] = (draft.status, draft.direction, draft.subject, list(draft.to_addresses))
        assert await session.get(Contact, uuid.UUID(provider["id"])) is not None
        return out

    out = asyncio.run(_with_session(settings, world.tenant_a, run))
    assert out["dry"] is True
    assert out["after_dry"] in (None, "")
    assert out["first"] is True
    assert out["notes1"] == "Ausfall Heizung fällt aus"
    assert out["notes2"].startswith("Ausfall Heizung fällt aus\n[")
    assert out["notes2"].endswith("Zweite Zeile")  # appended, the earlier text is kept
    assert out["contract"] == "error"
    assert out["contact"] == "error"
    assert out["no_relation"] == "error"
    assert out["draft"] == (
        "draft",
        "out",
        "Störung Heizung fällt aus",
        [f"heizung-{RUN}@example.org"],
    )


# M22-02 invoice submission into the receipt inbox ------------------------------------------------


def test_invoice_submission_becomes_receipt_draft(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.documents.models import Document, DocumentSource, StorageKind, TextStatus
    from mhvp.portal.models import ChangeRequest
    from mhvp.portal.routers import _apply_invoice_submission
    from mhvp.receipts.models import ReceiptDraft
    from mhvp.tickets.models import OrderStatus, WorkOrder, WorkOrderEvent

    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "q11admin"))
    prop = _property(client, admin, "964")
    provider = _contact(client, admin, "Dachdecker")

    class _Principal:
        user_id = world.users["q11admin"]
        tenant_id = world.tenant_a

        def __init__(self, allowed: bool) -> None:
            self.allowed = allowed

        def has(self, permission: str) -> bool:
            return self.allowed

    async def run(session: Any) -> dict[str, Any]:
        from mhvp.core.problems import ProblemError

        doc = Document(
            tenant_id=world.tenant_a,
            title="Rechnung",
            filename="r.pdf",
            mime_type="application/pdf",
            size=1,
            sha256="d" * 64,
            storage=StorageKind.MINIO,
            storage_ref=f"q11-inv-{RUN}",
            text_status=TextStatus.NONE,
            source=DocumentSource.UPLOAD,
            visibility=[],
        )
        order = WorkOrder(
            tenant_id=world.tenant_a,
            property_id=uuid.UUID(prop["id"]),
            provider_contact_id=uuid.UUID(provider["id"]),
            description="Dach reparieren",
            status=OrderStatus.DONE,
        )
        session.add_all([doc, order])
        await session.flush()
        payload = {
            "number": "R-2026-77",
            "invoice_date": "2026-09-29",
            "gross": "1190.00",
            "document_id": str(doc.id),
            "work_order_id": str(order.id),
        }
        row = ChangeRequest(
            tenant_id=world.tenant_a,
            account_id=uuid.uuid4(),
            kind="invoice_submission",
            payload=json.dumps(payload),
        )
        out: dict[str, Any] = {}
        try:
            await _apply_invoice_submission(session, _Principal(False), row, payload)  # type: ignore[arg-type]
            out["denied"] = False
        except ProblemError:
            out["denied"] = True
        draft_id = await _apply_invoice_submission(
            session,
            _Principal(True),
            row,
            payload,  # type: ignore[arg-type]
        )
        again = await _apply_invoice_submission(
            session,
            _Principal(True),
            row,
            payload,  # type: ignore[arg-type]
        )
        draft = await session.get(ReceiptDraft, draft_id)
        out["same"] = again == draft_id
        out["draft"] = (draft.status, draft.source, draft.invoice_id, draft.document_id == doc.id)
        out["fields"] = {k: v["value"] for k, v in draft.fields.items()}
        await session.refresh(order)
        out["order"] = order.status.value
        out["events"] = [
            e.to_status
            for e in (
                await session.scalars(
                    select(WorkOrderEvent).where(WorkOrderEvent.work_order_id == order.id)
                )
            ).all()
        ]
        assert Decimal(out["fields"]["gross"]) == Decimal("1190.00")
        return out

    out = asyncio.run(_with_session(settings, world.tenant_a, run))
    assert out["denied"] is True
    assert out["same"] is True  # idempotent per document, no second draft
    assert out["draft"] == ("proposed", "portal", None, True)  # draft only, no invoice, no posting
    assert out["fields"]["invoice_number"] == "R-2026-77"
    assert out["fields"]["invoice_date"] == "2026-09-29"
    assert out["fields"]["supplier_name"].startswith("Dachdecker")
    assert out["order"] == "invoiced"
    assert out["events"] == ["invoiced"]


def test_notification_mail_modes_collective(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """M23-04: email_mode validation and persistence; one collective mail per user, daily
    entries only wait for the daily run."""
    from mhvp.workspace import notification_prefs
    from mhvp.workspace.models import Notification
    from mhvp.workspace.services import notify

    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "q11admin"))
    care = bearer(login(client, world, "q11care"))
    url = f"{W}/notification-preferences"
    # The preferences test above leaves a two hour mute on the admin; lift it first.
    _ok(client.put(url, json={"items": [{"kind": "*", "muted_until": None}]}, headers=admin))
    assert (
        client.put(
            url, json={"items": [{"kind": "automation", "email_mode": "weekly"}]}, headers=admin
        ).status_code
        == 422
    )
    saved = _ok(
        client.put(
            url,
            json={
                "items": [
                    {"kind": "ticket_assigned", "email": True, "email_mode": "immediate"},
                    {"kind": "automation", "email": True, "email_mode": "daily"},
                ]
            },
            headers=admin,
        )
    )
    modes = {i["kind"]: i["email_mode"] for i in saved["items"]}
    assert modes["automation"] == "daily"
    assert modes["ticket_assigned"] == "immediate"
    other = {i["kind"]: i for i in _ok(client.get(url, headers=care))["items"]}
    assert other["automation"]["email_mode"] == "immediate"
    admin_id = world.users["q11admin"]

    async def seed(session: Any) -> None:
        for kind, title in (
            ("ticket_assigned", "Eins"),
            ("ticket_assigned", "Zwei"),
            ("automation", "Taeglich"),
        ):
            await notify(
                session,
                tenant_id=world.tenant_a,
                user_id=admin_id,
                kind=kind,
                title=title,
                entity_type="ticket",
                entity_id=uuid.uuid4(),
            )

    asyncio.run(_with_session(settings, world.tenant_a, seed))
    calls: list[tuple[str, str]] = []

    async def send(session: Any, daily: bool) -> dict[str, int]:
        import mhvp.sla.channels as channels

        async def fake(_s: Any, _c: Any, _t: Any, to: str, subject: str, body: str) -> None:
            calls.append((subject, body))

        original = channels.send_email
        channels.send_email = fake  # type: ignore[assignment]
        try:
            return await notification_prefs.send_pending_mails(
                session, settings, world.tenant_a, daily=daily
            )
        finally:
            channels.send_email = original  # type: ignore[assignment]

    first = asyncio.run(_with_session(settings, world.tenant_a, lambda s: send(s, False)))
    assert first["mails"] == 1
    assert first["sent"] == 2
    assert calls[0][0] == "2 neue Benachrichtigungen"
    assert "Eins" in calls[0][1]
    assert "Zwei" in calls[0][1]
    assert "Taeglich" not in calls[0][1]
    second = asyncio.run(_with_session(settings, world.tenant_a, lambda s: send(s, True)))
    assert second["mails"] == 1
    assert calls[1][0] == "Taeglich"

    async def open_mails(session: Any) -> int:
        rows = await session.scalars(
            select(Notification).where(
                Notification.email_pending.is_(True), Notification.email_sent_at.is_(None)
            )
        )
        return len(rows.all())

    assert asyncio.run(_with_session(settings, world.tenant_a, open_mails)) == 0
