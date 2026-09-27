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
