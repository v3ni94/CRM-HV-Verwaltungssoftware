"""M9 daily jobs (section 15.1, tasks A40 and A41): digest per user and day (idempotent,
nothing for empty overviews), deadline list from meters, bank consents and documents with
one notification per row at the lead time, permissions on the endpoints and tenant
separation. Dates are orientation only (M1-09)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.tasks import deadlines_once, digest_once
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"
TODAY = date(2026, 9, 26)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"j-{RUN}", name=f"Jobs {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"j2-{RUN}", name=f"Jobs2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("jadmin", a, "tenant_admin"),
            ("jcolleague", a, "standard"),
            ("jcaretaker", a, "caretaker"),
            ("jother", b, "tenant_admin"),
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


async def _seed(settings: Any, world: World, property_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Rows the API cannot create with a chosen date: tickets with an SLA due time, a meter
    with a calibration date and a bank connection with a consent date (tenant A only)."""
    from mhvp.banking.models import BankConnection, ConnectionStatus, Connector
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.properties.models import Meter
    from mhvp.tickets.models import Priority, Ticket, TicketStatus

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        async with tenant_transaction(factory, world.tenant_a) as session:
            noon = datetime(TODAY.year, TODAY.month, TODAY.day, 10, 0, tzinfo=UTC)
            for key, number, due in (
                ("ticket_today", 9001, noon),
                ("ticket_overdue", 9002, noon - timedelta(days=3)),
                ("ticket_future", 9003, noon + timedelta(days=5)),
            ):
                ticket = Ticket(
                    tenant_id=world.tenant_a,
                    number=number,
                    property_id=property_id,
                    title=f"Ticket {key} {RUN}",
                    status=TicketStatus.IN_PROGRESS,
                    priority=Priority.NORMAL,
                    assignee_user_id=world.users["jcolleague"],
                    sla_due_at=due,
                )
                session.add(ticket)
                await session.flush()
                ids[key] = ticket.id
            meter = Meter(
                tenant_id=world.tenant_a,
                property_id=property_id,
                meter_type_code="cold_water",
                number=f"Z-{RUN}",
                calibration_due_date=TODAY + timedelta(days=20),
                valid_from=TODAY,
            )
            session.add(meter)
            conn = BankConnection(
                tenant_id=world.tenant_a,
                connector=Connector.EBICS,
                bank_name=f"Hausbank {RUN}",
                consent_valid_until=TODAY + timedelta(days=90),
                status=ConnectionStatus.ACTIVE,
            )
            session.add(conn)
            await session.flush()
            ids["meter"] = meter.id
            ids["bank"] = conn.id
    finally:
        await engine.dispose()
    return ids


async def _set_meter_date(settings: Any, tenant_id: uuid.UUID, meter_id: uuid.UUID) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.properties.models import Meter

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            meter = await session.scalar(select(Meter).where(Meter.id == meter_id))
            assert meter is not None
            meter.calibration_due_date = TODAY + timedelta(days=200)
    finally:
        await engine.dispose()


def test_deadlines_and_digest(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "jadmin"))
    colleague = bearer(login(client, world, "jcolleague"))
    caretaker = bearer(login(client, world, "jcaretaker"))
    other = bearer(login(client, world, "jother"))

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "941",
                "name": f"Jobhaus {RUN}",
                "management_type": "rental",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    ids = asyncio.run(_seed(settings, world, uuid.UUID(prop["id"])))

    # Job settings: default off / 30 days, editable only with tenant_settings:update.
    js = _ok(client.get(f"{W}/job-settings", headers=colleague))
    assert js == {
        "digest_mail_enabled": False,
        "deadline_lead_days": 30,
        "deadline_lead_days_default": 30,
    }
    assert (
        client.put(
            f"{W}/job-settings", json={"deadline_lead_days": 45}, headers=colleague
        ).status_code
        == 403
    )
    js = _ok(client.put(f"{W}/job-settings", json={"deadline_lead_days": 45}, headers=h))
    assert js["deadline_lead_days"] == 45
    assert js["digest_mail_enabled"] is False

    # Deadline job: meter (20 days, inside the 45 day lead time) and bank consent (90 days,
    # outside). One notification for the meter, none for the consent, none on a re-run.
    first = asyncio.run(deadlines_once(settings, TODAY))
    assert first["created"] >= 2
    assert first["notified"] >= 1
    second = asyncio.run(deadlines_once(settings, TODAY))
    assert second["created"] == 0
    assert second["notified"] == 0
    assert second["closed"] == 0

    rows = _ok(client.get(f"{W}/deadlines", headers=h))
    by_source = {r["source_id"]: r for r in rows}
    meter_row = by_source[str(ids["meter"])]
    bank_row = by_source[str(ids["bank"])]
    assert meter_row["kind"] == "meter_calibration"
    assert meter_row["lead_days"] == 45
    assert meter_row["notified_at"] is not None
    assert meter_row["status"] == "open"
    assert bank_row["kind"] == "bank_consent"
    assert bank_row["notified_at"] is None
    assert meter_row["due_on"] == (TODAY + timedelta(days=20)).isoformat()

    # Filters: kind and period.
    only_bank = _ok(client.get(f"{W}/deadlines", params={"kind": "bank_consent"}, headers=h))
    assert {r["kind"] for r in only_bank} == {"bank_consent"}
    window = _ok(
        client.get(
            f"{W}/deadlines",
            params={"from": TODAY.isoformat(), "to": (TODAY + timedelta(days=30)).isoformat()},
            headers=h,
        )
    )
    assert str(ids["meter"]) in {r["source_id"] for r in window}
    assert str(ids["bank"]) not in {r["source_id"] for r in window}

    # Permissions: the caretaker reads properties but not accounting; the other tenant sees
    # nothing of tenant A.
    care_rows = _ok(client.get(f"{W}/deadlines", headers=caretaker))
    assert str(ids["meter"]) in {r["source_id"] for r in care_rows}
    assert str(ids["bank"]) not in {r["source_id"] for r in care_rows}
    assert _ok(client.get(f"{W}/deadlines", params={"status": "all"}, headers=other)) == []

    # Notification once, to users with properties:update (admin), not to the caretaker.
    notes = _ok(client.get(f"{W}/notifications", params={"unread": True}, headers=h))
    mine = [n for n in notes if n["kind"] == "compliance_deadline"]
    assert len(mine) == 1
    assert mine[0]["entity_id"] == meter_row["id"]
    assert "zu prüfen" in (mine[0]["body"] or "")
    care_notes = _ok(client.get(f"{W}/notifications", headers=caretaker))
    assert not [n for n in care_notes if n["kind"] == "compliance_deadline"]

    # Source date moves: the old row is closed, a new open row appears (not yet notified).
    asyncio.run(_set_meter_date(settings, world.tenant_a, ids["meter"]))
    third = asyncio.run(deadlines_once(settings, TODAY))
    assert third["closed"] >= 1
    assert third["created"] >= 1
    assert third["notified"] == 0
    all_rows = _ok(
        client.get(
            f"{W}/deadlines", params={"kind": "meter_calibration", "status": "all"}, headers=h
        )
    )
    statuses = {r["due_on"]: r["status"] for r in all_rows if r["source_id"] == str(ids["meter"])}
    assert statuses[(TODAY + timedelta(days=20)).isoformat()] == "done"
    assert statuses[(TODAY + timedelta(days=200)).isoformat()] == "open"

    # Digest endpoint: the colleague sees own due and overdue tickets, not the future one.
    digest = _ok(client.get(f"{W}/digest", params={"day": TODAY.isoformat()}, headers=colleague))
    assert digest["date"] == TODAY.isoformat()
    assert digest["sections"]["tickets_due_today"]["count"] == 1
    assert digest["sections"]["tickets_overdue"]["count"] == 1
    assert digest["sections"]["tickets_due_today"]["items"][0]["id"] == str(ids["ticket_today"])
    assert digest["total"] >= 2
    admin_digest = _ok(client.get(f"{W}/digest", params={"day": TODAY.isoformat()}, headers=h))
    assert admin_digest["sections"]["tickets_due_today"]["count"] == 0

    # Digest job: one notification for the colleague, none for members with an empty
    # overview, none twice on the same day; the other tenant gets nothing from tenant A.
    run1 = asyncio.run(digest_once(settings, TODAY))
    assert run1["notified"] >= 1
    assert run1["mails"] == 0
    run2 = asyncio.run(digest_once(settings, TODAY))
    assert run2["notified"] == 0
    assert run2["skipped"] >= run1["users"]
    col_notes = [
        n
        for n in _ok(client.get(f"{W}/notifications", headers=colleague))
        if n["kind"] == "daily_digest"
    ]
    assert len(col_notes) == 1
    assert "Überfällige Tickets: 1" in (col_notes[0]["body"] or "")
    assert "Heute fällige Tickets: 1" in (col_notes[0]["body"] or "")
    care_digest = [
        n
        for n in _ok(client.get(f"{W}/notifications", headers=caretaker))
        if n["kind"] == "daily_digest"
    ]
    assert care_digest == []
    other_notes = _ok(client.get(f"{W}/notifications", headers=other))
    assert not [n for n in other_notes if n["kind"] in ("daily_digest", "compliance_deadline")]

    # A later day is a new digest.
    run3 = asyncio.run(digest_once(settings, TODAY + timedelta(days=1)))
    assert run3["notified"] >= 1


def test_endpoints_require_tenant_user(client: TestClient) -> None:
    assert client.get(f"{W}/digest").status_code == 401
    assert client.get(f"{W}/deadlines").status_code == 401
    assert client.get(f"{W}/job-settings").status_code == 401
