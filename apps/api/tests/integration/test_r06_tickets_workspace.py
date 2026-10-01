"""R06 (Welle 4): ticket bulk in the shared report format, notification mute, maintenance bulk
with interval, immediate calendar entry of work order appointments, receipt draft link in the
portal proposals. Other tenant: 404, missing permission: 403, bad body: 422."""

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r06a-{RUN}", name=f"R06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r06b-{RUN}", name=f"R06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("r06admin", a, "tenant_admin"),
            ("r06care", a, "caretaker"),
            ("r06other", b, "tenant_admin"),
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


def _property(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    return _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"R06 Haus {number} {RUN}",
                "management_type": "rental",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )


def _contact(client: TestClient, h: dict[str, str], name: str) -> dict[str, Any]:
    return _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"{name} {RUN}"},
            headers=h,
        ),
        201,
    )


def test_tickets_bulk_shared_report(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r06admin"))
    other = bearer(login(client, world, "r06other"))
    first = _ok(client.post(T, json={"title": f"Bulk 1 {RUN}"}, headers=h), 201)
    second = _ok(client.post(T, json={"title": f"Bulk 2 {RUN}"}, headers=h), 201)
    ghost = str(uuid.uuid4())
    body = {"ids": [first["id"], second["id"], ghost], "status": "in_progress"}
    report = _ok(client.post(f"{T}/bulk", json=body, headers=h))
    assert (report["total"], report["succeeded"], report["failed"]) == (3, 2, 1)
    failed = [i for i in report["items"] if not i["ok"]]
    assert failed[0]["id"] == ghost
    assert failed[0]["code"]
    # idempotent: the same status again is no failure
    again = _ok(client.post(f"{T}/bulk", json=body | {"ids": [first["id"]]}, headers=h))
    assert again["failed"] == 0
    assert _ok(client.get(f"{T}/{first['id']}", headers=h))["status"] == "in_progress"
    # other tenant: the tickets are not found, nothing changes
    foreign = _ok(client.post(f"{T}/bulk", json=body | {"ids": [first["id"]]}, headers=other))
    assert foreign["failed"] == 1
    assert (
        client.post(f"{T}/bulk", json={"ids": [], "status": "done"}, headers=h).status_code == 422
    )
    assert (
        client.post(f"{T}/bulk", json=body | {"status": "gibt_es_nicht"}, headers=h).status_code
        == 422
    )
    assert client.post(f"{T}/bulk", json=body).status_code == 401


def test_notifications_mute_all(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r06admin"))
    care = bearer(login(client, world, "r06care"))
    future = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    out = _ok(client.post(f"{W}/notifications/mute", json={"muted_until": future}, headers=h))
    by_kind = {i["kind"]: i for i in out["items"]}
    assert by_kind["*"]["muted_until"] is not None
    assert by_kind["sla_escalation"]["muted_until"] is None  # mandatory kinds ignore the mute
    # own settings only
    care_kinds = {
        i["kind"]: i
        for i in _ok(client.get(f"{W}/notification-preferences", headers=care))["items"]
    }
    assert care_kinds["*"]["muted_until"] is None
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert (
        client.post(f"{W}/notifications/mute", json={"muted_until": past}, headers=h).status_code
        == 422
    )
    lifted = _ok(client.post(f"{W}/notifications/mute", json={"muted_until": None}, headers=h))
    assert {i["kind"]: i for i in lifted["items"]}["*"]["muted_until"] is None
    assert client.post(f"{W}/notifications/mute", json={}).status_code == 401


def test_maintenance_bulk_done_follows_interval(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r06admin"))
    care = bearer(login(client, world, "r06care"))
    other = bearer(login(client, world, "r06other"))
    prop = _property(client, h, "971")
    due = datetime.now(UTC).date() + timedelta(days=5)
    once = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/maintenance",
            json={"kind": "inspection", "title": "Einmalig", "due_date": due.isoformat()},
            headers=h,
        ),
        201,
    )
    cyclic = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/maintenance",
            json={
                "kind": "maintenance",
                "title": "Jährlich",
                "due_date": due.isoformat(),
                "interval_months": 12,
            },
            headers=h,
        ),
        201,
    )
    body = {
        "action": "maintenance.done",
        "ids": [once["id"], cyclic["id"]],
        "done_on": "2026-10-01",
    }
    assert client.post(f"{W}/bulk", json=body, headers=other).status_code == 404
    assert client.post(f"{W}/bulk", json=body, headers=care).status_code == 403
    assert _ok(client.post(f"{W}/bulk", json=body, headers=h))["changed"] == 2
    items = {
        i["title"]: i
        for i in _ok(client.get(f"/api/v1/properties/{prop['id']}/maintenance", headers=h))
    }
    assert items["Einmalig"]["status"] == "done"
    assert items["Jährlich"]["status"] == "open"  # interval: stays open like the single action
    assert items["Jährlich"]["due_date"] == "2027-10-01"
    # the closed item is skipped the second time, the cyclic one moves on again
    assert _ok(client.post(f"{W}/bulk", json=body, headers=h))["changed"] == 1


def test_work_order_step_writes_calendar_entry_at_once(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.workspace.models import CalendarEntry
    from mhvp.workspace.tasks import deadlines_once

    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "r06admin"))
    prop = _property(client, h, "972")
    provider = _contact(client, h, "Elektriker")
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "property_id": prop["id"],
                "provider_contact_id": provider["id"],
                "description": "Steckdosen prüfen",
            },
            headers=h,
        ),
        201,
    )
    steps = f"/api/v1/work-orders/{order['id']}/steps"
    _ok(client.post(steps, json={"status": "requested"}, headers=h))
    _ok(client.post(steps, json={"status": "approved"}, headers=h))
    _ok(
        client.post(
            steps, json={"status": "scheduled", "scheduled_at": "2026-10-06T07:30:00Z"}, headers=h
        )
    )

    async def entries(session: Any) -> list[CalendarEntry]:
        return list(
            (
                await session.scalars(
                    select(CalendarEntry).where(CalendarEntry.source_id == uuid.UUID(order["id"]))
                )
            ).all()
        )

    rows = asyncio.run(_with_session(settings, world.tenant_a, entries))
    assert len(rows) == 1  # without waiting for the daily job
    assert rows[0].starts_on == date(2026, 10, 6)
    assert "09:30" in rows[0].title
    assert rows[0].owner_user_id is None
    # the daily job finds the entry and creates no second one
    asyncio.run(deadlines_once(settings, date(2026, 9, 30)))
    assert len(asyncio.run(_with_session(settings, world.tenant_a, entries))) == 1


def test_change_requests_list_links_receipt_draft(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.documents.models import Document, DocumentSource, StorageKind, TextStatus
    from mhvp.portal.models import ChangeRequest, PortalAccount
    from mhvp.receipts.models import ReceiptDraft, ReceiptDraftStatus

    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "r06admin"))
    provider = _contact(client, h, "Dachdecker")

    async def seed(session: Any) -> uuid.UUID:
        doc = Document(
            tenant_id=world.tenant_a,
            title="Rechnung",
            filename="r.pdf",
            mime_type="application/pdf",
            size=1,
            sha256="e" * 64,
            storage=StorageKind.MINIO,
            storage_ref=f"r06-inv-{RUN}",
            text_status=TextStatus.NONE,
            source=DocumentSource.UPLOAD,
            visibility=[],
        )
        account = PortalAccount(
            tenant_id=world.tenant_a,
            user_id=world.users["r06care"],
            contact_id=uuid.UUID(provider["id"]),
            status="active",
        )
        session.add_all([doc, account])
        await session.flush()
        draft = ReceiptDraft(
            tenant_id=world.tenant_a,
            created_by=world.users["r06admin"],
            document_id=doc.id,
            source="portal",
            status=ReceiptDraftStatus.PROPOSED.value,
            fields={},
            property_suggestions=[],
            warnings=[],
        )
        session.add(draft)
        session.add(
            ChangeRequest(
                tenant_id=world.tenant_a,
                account_id=account.id,
                kind="invoice_submission",
                status="accepted",
                payload=json.dumps({"number": "R-1", "document_id": str(doc.id)}),
            )
        )
        await session.flush()
        return draft.id

    draft_id = asyncio.run(_with_session(settings, world.tenant_a, seed))
    rows = _ok(
        client.get(
            "/api/v1/portal-admin/change-requests",
            params={"contact_id": provider["id"]},
            headers=h,
        )
    )
    assert [r["receipt_draft_id"] for r in rows] == [str(draft_id)]
