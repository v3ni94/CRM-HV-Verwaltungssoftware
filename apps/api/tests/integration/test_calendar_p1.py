"""P1 AP7 (spec 4.10): calendar entries generated from date fields by the deadline job.

Covers: deterministic and idempotent generation (a second run changes nothing), update when
the source date moves, deletion when the source row or its date disappears, the calendar
endpoint (generated entry with source link, no duplicate of the live derived date, hidden
without the read permission of its kind), the deadline list with the link to the source and
the manual delete route refusing generated entries."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.jobs import DEADLINE_KINDS, DEADLINE_PERMISSIONS, calendar_sources
from mhvp.workspace.models import CalendarEntry
from mhvp.workspace.tasks import deadlines_once
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
        a, _ = await services.provision_tenant(factory, slug=f"cal-{RUN}", name=f"Cal {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"cal2-{RUN}", name=f"Cal2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("cadmin", a, "tenant_admin"),
            ("ccaretaker", a, "caretaker"),
            ("cother", b, "tenant_admin"),
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


async def _seed(session: Any, tenant_id: uuid.UUID, property_id: uuid.UUID) -> dict[str, Any]:
    from mhvp.properties.models import Building, Meter

    meter = Meter(
        tenant_id=tenant_id,
        property_id=property_id,
        meter_type_code="cold_water",
        number=f"C-{RUN}",
        calibration_due_date=TODAY + timedelta(days=40),
        valid_from=TODAY,
    )
    building = Building(
        tenant_id=tenant_id,
        property_id=property_id,
        name=f"Haus {RUN}",
        energy_certificate_valid_until=TODAY + timedelta(days=100),
    )
    session.add_all([meter, building])
    await session.flush()
    return {"meter": meter.id, "building": building.id}


async def _generated(session: Any) -> dict[tuple[str, uuid.UUID | None, str], CalendarEntry]:
    rows = (
        await session.scalars(select(CalendarEntry).where(CalendarEntry.owner_user_id.is_(None)))
    ).all()
    return {(r.source_type, r.source_id, r.category): r for r in rows}


def test_registry_and_kinds() -> None:
    """Every deadline kind carries a permission pair; the registry lists the readers that
    exist today (those of parallel packages join after their merge)."""
    assert set(DEADLINE_KINDS) <= set(DEADLINE_PERMISSIONS)
    names = {reader.__name__ for reader in calendar_sources()}
    assert {"_read_contracts", "_read_meters", "_read_maintenance", "_read_meetings"} <= names
    assert "_read_energy_certificates" in names


def test_generated_calendar_entries(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "cadmin"))
    caretaker = bearer(login(client, world, "ccaretaker"))
    other = bearer(login(client, world, "cother"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "951",
                "name": f"Kalenderhaus {RUN}",
                "management_type": "rental",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    property_id = uuid.UUID(prop["id"])
    item = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/maintenance",
            json={
                "kind": "inspection",
                "title": f"Aufzugsprüfung {RUN}",
                "due_date": (TODAY + timedelta(days=10)).isoformat(),
                "remind_before": "1m",
            },
            headers=h,
        ),
        201,
    )
    ids = asyncio.run(
        _with_session(settings, world.tenant_a, lambda s: _seed(s, world.tenant_a, property_id))
    )

    # First run creates, second run is a no-op (idempotent, deterministic).
    first = asyncio.run(deadlines_once(settings, TODAY))
    assert first["calendar_created"] >= 3
    second = asyncio.run(deadlines_once(settings, TODAY))
    assert second["calendar_created"] == 0
    assert second["calendar_updated"] == 0
    assert second["calendar_deleted"] == 0

    rows = asyncio.run(_with_session(settings, world.tenant_a, _generated))
    meter_entry = rows[("meter", ids["meter"], "meter_calibration")]
    assert meter_entry.starts_on == TODAY + timedelta(days=40)
    assert meter_entry.shared is True
    assert meter_entry.owner_user_id is None
    assert meter_entry.reminders == ["1m"]
    assert rows[("building", ids["building"], "energy_certificate")].reminders == ["3m", "1m"]
    maint = rows[("maintenance_item", uuid.UUID(item["id"]), "maintenance")]
    assert maint.reminders == ["1m"]  # remind_before of the item wins
    assert maint.property_id == property_id

    # Calendar endpoint: generated entry with route to the source, no duplicate of the live
    # maintenance date, and no entry for the caretaker without contracts/properties read.
    start, end = TODAY.isoformat(), (TODAY + timedelta(days=120)).isoformat()
    cal = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=h))["items"]
    meter_items = [c for c in cal if c["entity_id"] == str(ids["meter"])]
    assert len(meter_items) == 1
    assert meter_items[0]["kind"] == "meter_calibration"
    assert meter_items[0]["href"] == f"/objekte/{prop['id']}#zaehler"
    assert meter_items[0]["editable"] is False
    assert meter_items[0]["calendar_entry_id"] == str(meter_entry.id)
    maint_items = [c for c in cal if c["entity_id"] == item["id"]]
    assert len(maint_items) == 1
    assert maint_items[0]["href"] == f"/objekte/{prop['id']}#wartung"
    assert (
        client.delete(f"{W}/calendar/{meter_entry.id}", headers=h).status_code == 404
    )  # generated entries are not deletable by hand
    # Permission per kind: the caretaker (properties read) sees the meter but not a contract
    # entry; a foreign tenant sees nothing.
    contract_source = uuid.uuid4()

    async def _contract_entry(session: Any) -> None:
        session.add(
            CalendarEntry(
                tenant_id=world.tenant_a,
                owner_user_id=None,
                title=f"Vertragsende {RUN}",
                starts_on=TODAY + timedelta(days=30),
                shared=True,
                source_type="contract",
                source_id=contract_source,
                category="contract_end",
            )
        )

    asyncio.run(_with_session(settings, world.tenant_a, _contract_entry))
    care = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=caretaker))
    assert [c for c in care["items"] if c["entity_id"] == str(ids["meter"])]
    assert not [c for c in care["items"] if c["entity_id"] == str(contract_source)]
    admin_cal = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=h))
    assert [c for c in admin_cal["items"] if c["entity_id"] == str(contract_source)]
    foreign = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=other))
    assert not [c for c in foreign["items"] if c["entity_id"] == str(ids["meter"])]

    # Deadline list carries the same link; the new kinds are filterable.
    deadlines = _ok(client.get(f"{W}/deadlines", params={"kind": "energy_certificate"}, headers=h))
    assert [d["href"] for d in deadlines if d["source_id"] == str(ids["building"])] == [
        f"/objekte/{prop['id']}#gebaeude"
    ]

    # Date moves: the entry follows; date removed: the entry disappears; source deleted: gone.
    async def _move(session: Any) -> None:
        from mhvp.properties.models import Building, MaintenanceItem, Meter

        meter = await session.scalar(select(Meter).where(Meter.id == ids["meter"]))
        meter.calibration_due_date = TODAY + timedelta(days=60)
        building = await session.scalar(select(Building).where(Building.id == ids["building"]))
        building.energy_certificate_valid_until = None
        maintenance = await session.scalar(
            select(MaintenanceItem).where(MaintenanceItem.id == uuid.UUID(item["id"]))
        )
        await session.delete(maintenance)

    asyncio.run(_with_session(settings, world.tenant_a, _move))
    third = asyncio.run(deadlines_once(settings, TODAY))
    assert third["calendar_updated"] >= 1
    assert third["calendar_deleted"] >= 3  # energy certificate, maintenance, orphan contract
    rows = asyncio.run(_with_session(settings, world.tenant_a, _generated))
    assert rows[("meter", ids["meter"], "meter_calibration")].starts_on == TODAY + timedelta(
        days=60
    )
    assert ("building", ids["building"], "energy_certificate") not in rows
    assert ("maintenance_item", uuid.UUID(item["id"]), "maintenance") not in rows


def test_expand_occurrences() -> None:
    """Recurrence expansion (B.30): weekly, monthly with month end clipping, yearly with
    end date; nothing without a rule outside the window."""
    from mhvp.workspace.jobs import expand_occurrences

    start, end = date(2026, 1, 1), date(2026, 12, 31)
    assert expand_occurrences(date(2026, 3, 1), None, start, end) == [date(2026, 3, 1)]
    assert expand_occurrences(date(2027, 3, 1), None, start, end) == []
    weekly = {"frequency": "weekly", "interval": 2, "until": "2026-02-15"}
    assert expand_occurrences(date(2026, 1, 5), weekly, start, end) == [
        date(2026, 1, 5),
        date(2026, 1, 19),
        date(2026, 2, 2),
    ]
    monthly = {"frequency": "monthly", "interval": 1, "until": "2026-04-30"}
    assert expand_occurrences(date(2026, 1, 31), monthly, start, end) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]
    yearly = {"frequency": "yearly", "interval": 1, "until": None}
    assert expand_occurrences(date(2024, 2, 29), yearly, start, date(2028, 12, 31)) == [
        date(2026, 2, 28),
        date(2027, 2, 28),
        date(2028, 2, 29),
    ]
    # Window starts after the first occurrence: only the later ones.
    assert expand_occurrences(date(2026, 1, 5), weekly, date(2026, 1, 10), end) == [
        date(2026, 1, 19),
        date(2026, 2, 2),
    ]


def test_reminders_recurrence_meeting_and_ticket_due(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Meeting entries link to the property page of the HOA, reminder codes notify once
    per code and occurrence via the deadline job, recurring manual entries are expanded
    in the calendar and the deadline list, and ``ticket.due_on`` feeds ``ticket_due``."""
    from mhvp.workspace.models import Notification

    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "cadmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "952",
                "name": f"WEG Kalender {RUN}",
                "management_type": "hoa",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    property_id = uuid.UUID(prop["id"])

    async def _meeting(session: Any) -> uuid.UUID:
        from datetime import UTC, datetime

        from mhvp.hoa.models import Meeting
        from mhvp.properties.models import LegalEntity, LegalEntityKind

        # An HOA property carries its legal entity from creation on.
        entity = await session.scalar(
            select(LegalEntity).where(
                LegalEntity.property_id == property_id, LegalEntity.kind == LegalEntityKind.HOA
            )
        )
        assert entity is not None
        meeting = Meeting(
            tenant_id=world.tenant_a,
            legal_entity_id=entity.id,
            scheduled_at=datetime(TODAY.year, TODAY.month, TODAY.day, 10, tzinfo=UTC)
            + timedelta(days=20),
        )
        session.add(meeting)
        await session.flush()
        return meeting.id

    meeting_id = asyncio.run(_with_session(settings, world.tenant_a, _meeting))

    # Ticket due date: optional, set on create, cleared and set again by patch.
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": f"Frist {RUN}", "due_on": (TODAY + timedelta(days=3)).isoformat()},
            headers=h,
        ),
        201,
    )
    assert ticket["due_on"] == (TODAY + timedelta(days=3)).isoformat()
    assert ticket["sla_due_at"] is not None  # SLA stays separate
    cleared = _ok(client.patch(f"/api/v1/tickets/{ticket['id']}", json={"due_on": None}, headers=h))
    assert cleared["due_on"] is None
    unchanged = _ok(
        client.patch(f"/api/v1/tickets/{ticket['id']}", json={"priority": "high"}, headers=h)
    )
    assert unchanged["due_on"] is None
    ticket = _ok(
        client.patch(
            f"/api/v1/tickets/{ticket['id']}",
            json={"due_on": (TODAY + timedelta(days=3)).isoformat()},
            headers=h,
        )
    )
    assert ticket["due_on"] == (TODAY + timedelta(days=3)).isoformat()

    # Manual recurring entry with a reminder: weekly from tomorrow for three weeks.
    assert (
        client.post(
            f"{W}/calendar",
            json={"title": "x", "starts_on": TODAY.isoformat(), "reminders": ["2w"]},
            headers=h,
        ).status_code
        == 422
    )
    entry = _ok(
        client.post(
            f"{W}/calendar",
            json={
                "title": f"Jour fixe {RUN}",
                "starts_on": (TODAY + timedelta(days=1)).isoformat(),
                "reminders": ["1d"],
                "recurrence": {
                    "frequency": "weekly",
                    "interval": 1,
                    "until": (TODAY + timedelta(days=21)).isoformat(),
                },
            },
            headers=h,
        ),
        201,
    )
    entry_id = entry["entity_id"]
    assert entry["recurrence"]["frequency"] == "weekly"
    assert entry["reminders"] == ["1d"]
    start, end = TODAY.isoformat(), (TODAY + timedelta(days=30)).isoformat()
    cal = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=h))["items"]
    occurrences = [c for c in cal if c["entity_id"] == entry_id]
    assert [c["date"] for c in occurrences] == [
        (TODAY + timedelta(days=d)).isoformat() for d in (1, 8, 15)
    ]
    assert all(c["recurrence"] and c["editable"] for c in occurrences)
    # Later window: only the remaining occurrence, nothing persisted per occurrence.
    later = _ok(
        client.get(
            f"{W}/calendar",
            params={"start": (TODAY + timedelta(days=10)).isoformat(), "end": end},
            headers=h,
        )
    )["items"]
    assert [c["date"] for c in later if c["entity_id"] == entry_id] == [
        (TODAY + timedelta(days=15)).isoformat()
    ]

    async def _count_entries(session: Any) -> int:
        return len(
            (
                await session.scalars(
                    select(CalendarEntry.id).where(CalendarEntry.id == uuid.UUID(entry_id))
                )
            ).all()
        )

    assert asyncio.run(_with_session(settings, world.tenant_a, _count_entries)) == 1

    # Deadline list: the occurrences as kind "appointment" with the calendar link.
    rows = _ok(
        client.get(
            f"{W}/deadlines", params={"kind": "appointment", "from": start, "to": end}, headers=h
        )
    )
    mine = [r for r in rows if r["source_id"] == entry_id]
    assert [r["due_on"] for r in mine] == [
        (TODAY + timedelta(days=d)).isoformat() for d in (1, 8, 15)
    ]
    assert mine[0]["href"] == f"/kalender?termin={entry_id}&datum={TODAY + timedelta(days=1)}"
    assert mine[0]["lead_days"] == 1

    # Job: meeting entry with the property route, ticket_due entry, reminder of the manual
    # entry (tomorrow, code 1d) exactly once.
    first = asyncio.run(deadlines_once(settings, TODAY))
    assert first["reminders"] >= 1
    cal = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=h))["items"]
    meeting_items = [c for c in cal if c["entity_id"] == str(meeting_id)]
    assert len(meeting_items) == 1
    assert meeting_items[0]["href"] == f"/weg/{prop['id']}/versammlung/{meeting_id}"
    assert meeting_items[0]["property_id"] == prop["id"]
    ticket_items = [c for c in cal if c["entity_id"] == ticket["id"]]
    assert len(ticket_items) == 1
    assert ticket_items[0]["kind"] == "ticket_due"
    assert ticket_items[0]["href"] == f"/tickets/{ticket['id']}"
    meeting_rows = _ok(client.get(f"{W}/deadlines", params={"kind": "meeting"}, headers=h))
    assert [r["href"] for r in meeting_rows if r["source_id"] == str(meeting_id)] == [
        f"/weg/{prop['id']}/versammlung/{meeting_id}"
    ]

    def _reminders(target: str) -> list[dict[str, Any]]:
        notes = _ok(client.get(f"{W}/notifications", headers=h))
        return [n for n in notes if n["kind"] == "calendar_reminder" and n["target_id"] == target]

    manual_notes = _reminders(entry_id)
    assert len(manual_notes) == 1
    assert manual_notes[0]["href"].startswith(f"/kalender?termin={entry_id}")
    assert _reminders(ticket["id"]) == []  # due in three days, reminder 1d not yet reached
    second = asyncio.run(deadlines_once(settings, TODAY))
    assert second["reminders"] == 0
    assert len(_reminders(entry_id)) == 1

    # Two days later: the ticket reminder fires once and links to the ticket; the list based
    # lead time notification of the same ticket is a different kind (no double reminder).
    later_day = TODAY + timedelta(days=2)
    asyncio.run(deadlines_once(settings, later_day))
    ticket_notes = _reminders(ticket["id"])
    assert len(ticket_notes) == 1
    assert ticket_notes[0]["href"] == f"/tickets/{ticket['id']}"
    asyncio.run(deadlines_once(settings, later_day))
    assert len(_reminders(ticket["id"])) == 1
    # The next occurrence of the recurring entry (day 8) is reminded on its own day; an
    # unread reminder of the same entry is not duplicated (``notify`` idempotency), so the
    # first one is read before.
    _ok(
        client.post(f"{W}/notifications/read", json=[manual_notes[0]["id"]], headers=h),
        204,
    )
    asyncio.run(deadlines_once(settings, TODAY + timedelta(days=7)))
    assert len(_reminders(entry_id)) == 2

    async def _sent(session: Any) -> list[str]:
        row = await session.scalar(
            select(CalendarEntry).where(CalendarEntry.id == uuid.UUID(entry_id))
        )
        return list(row.reminders_sent)

    sent = asyncio.run(_with_session(settings, world.tenant_a, _sent))
    assert f"1d@{TODAY + timedelta(days=8)}" in sent
    assert isinstance(Notification, type)
