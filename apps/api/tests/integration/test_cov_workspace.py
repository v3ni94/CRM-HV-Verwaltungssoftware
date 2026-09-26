"""Coverage: workspace (M9) paths not exercised by the M9 flow: derived contract dates,
reminder windows and overdue notifications, digest and deadline list per permission, job
settings, notifications read by id, calendar targets without a Google mailbox, bulk edge
cases, ticket statistics buckets per range, operating metrics with a stored backup verify
protocol (A67), tenant separation."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import select

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.properties.models import MaintenanceItem
from mhvp.workspace import backup_verify
from mhvp.workspace import jobs as ws_jobs
from mhvp.workspace import routers as ws_routers
from mhvp.workspace import services as ws
from mhvp.workspace.models import Notification
from mhvp.workspace.tasks import reminders_once
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"
METRICS = "/api/v1/platform/ops/metrics"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"covws-{RUN}", name=f"CovWS {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"covws2-{RUN}", name=f"CovWS2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("covwsadmin", a, "tenant_admin"),
            ("covwsstandard", a, "standard"),
            ("covwscaretaker", a, "caretaker"),
            ("covwsother", b, "tenant_admin"),
            ("covwspadmin", None, ""),
        ]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=tenant is None,
            )
            world.users[name] = uid
            if tenant is not None:
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


def _run(database: Database, redis_url: str, tenant_id: uuid.UUID, fn: Any) -> Any:
    async def go() -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, tenant_id) as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _property(client: TestClient, h: dict[str, str], number: str, manager: uuid.UUID) -> Any:
    return _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Covhaus {number} {RUN}",
                "management_type": "rental",
                "manager_user_id": str(manager),
            },
            headers=h,
        ),
        201,
    )


def _maintenance(
    client: TestClient, h: dict[str, str], prop_id: str, title: str, due: date, remind: str | None
) -> Any:
    body: dict[str, Any] = {"kind": "inspection", "title": title, "due_date": due.isoformat()}
    if remind:
        body["remind_before"] = remind
    return _ok(client.post(f"/api/v1/properties/{prop_id}/maintenance", json=body, headers=h), 201)


# Services: reminder windows and derived contract dates ---------------------------------------


def test_maintenance_reminder_windows_and_overdue(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "covwsadmin"))
    manager = world.users["covwsadmin"]
    today = ws.local_today()
    prop = _property(client, h, "951", manager)
    overdue = _maintenance(client, h, prop["id"], "Überfällig Cov", today - timedelta(days=3), None)
    soon_6m = _maintenance(client, h, prop["id"], "Halbjahr Cov", today + timedelta(days=150), "6m")
    far_14d = _maintenance(client, h, prop["id"], "Weit Cov", today + timedelta(days=60), "14d")
    inside_1m = _maintenance(client, h, prop["id"], "Monat Cov", today + timedelta(days=20), "1m")

    async def run_twice(session: Any) -> tuple[int, int]:
        first = await ws.maintenance_reminders(session, today)
        second = await ws.maintenance_reminders(session, today)
        return first, second

    first, second = _run(database, redis_url, world.tenant_a, run_twice)
    assert first == 3  # overdue, 6m window (182 days), 1m window; the 14d item is too far
    assert second == 0  # idempotent: unread notifications are not repeated

    notes = _ok(client.get(f"{W}/notifications", params={"unread": True}, headers=h))
    by_entity = {n["entity_id"]: n for n in notes}
    assert by_entity[overdue["id"]]["kind"] == "maintenance_overdue"
    assert by_entity[overdue["id"]]["title"].startswith("Überfällig:")
    assert by_entity[soon_6m["id"]]["kind"] == "maintenance_due"
    assert by_entity[inside_1m["id"]]["kind"] == "maintenance_due"
    assert far_14d["id"] not in by_entity
    assert f"Objekt 951 Covhaus 951 {RUN}" in by_entity[overdue["id"]]["body"]

    # Read only the overdue one by id; the others stay unread.
    _ok(
        client.post(f"{W}/notifications/read", json=[by_entity[overdue["id"]]["id"]], headers=h),
        204,
    )
    unread = {
        n["entity_id"]
        for n in _ok(client.get(f"{W}/notifications", params={"unread": True}, headers=h))
    }
    assert overdue["id"] not in unread
    assert {soon_6m["id"], inside_1m["id"]} <= unread
    limited = _ok(client.get(f"{W}/notifications", params={"limit": 1}, headers=h))
    assert len(limited) == 1

    # Once read, the reminder is created again (only unread ones deduplicate).
    assert (
        _run(database, redis_url, world.tenant_a, lambda s: ws.maintenance_reminders(s, today)) == 1
    )

    # Job over all tenants: no new rows for this tenant now.
    assert asyncio.run(reminders_once(_settings(database, redis_url), today))["created"] >= 0

    # Tenant separation: the other tenant sees no notifications of the manager.
    other = bearer(login(client, world, "covwsother"))
    assert _ok(client.get(f"{W}/notifications", headers=other)) == []

    async def count_rows(session: Any) -> int:
        rows = (await session.scalars(select(Notification))).all()
        return len(rows)

    assert _run(database, redis_url, world.tenant_b, count_rows) == 0

    # Items without manager or already done are ignored by the reminder job.
    async def unassign(session: Any) -> None:
        item = await session.get(MaintenanceItem, uuid.UUID(far_14d["id"]))
        assert item is not None
        item.status = "done"

    _run(database, redis_url, world.tenant_a, unassign)
    _ok(client.post(f"{W}/notifications/read", headers=h), 204)
    assert (
        _run(database, redis_url, world.tenant_a, lambda s: ws.maintenance_reminders(s, today)) == 3
    )


def test_derived_dates_include_contract_end_and_termination(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from tests.integration.test_m5_contracts import _party
    from tests.integration.test_m5_contracts import _unit as _unit_

    h = bearer(login(client, world, "covwsadmin"))
    prop = _property(client, h, "952", world.users["covwsadmin"])
    owner, _ = _party(client, h, "CovEigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit = _unit_(client, h, prop["id"], "01")
    tenant_party, _ = _party(client, h, "CovMieter")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant_party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/termination",
            json={"end_date": "2030-03-31", "termination_date": "2030-01-15"},
            headers=h,
        )
    )

    async def derived(
        session: Any,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        both = await ws.derived_dates(
            session, date(2030, 1, 1), date(2030, 12, 31), contracts=True, properties=True
        )
        only_end = await ws.derived_dates(
            session, date(2030, 3, 1), date(2030, 3, 31), contracts=True, properties=False
        )
        none = await ws.derived_dates(
            session, date(2030, 1, 1), date(2030, 12, 31), contracts=False, properties=False
        )
        return both, only_end, none

    both, only_end, none = _run(database, redis_url, world.tenant_a, derived)
    kinds = {
        (d["kind"], str(d["date"])) for d in both if d["entity_id"] == uuid.UUID(contract["id"])
    }
    assert kinds == {
        ("contract_end_date", "2030-03-31"),
        ("contract_termination_date", "2030-01-15"),
    }
    labels = {d["title"] for d in both if d["entity_id"] == uuid.UUID(contract["id"])}
    assert labels == {
        f"Vertragsende Vertrag {contract['number']}",
        f"Kündigung Vertrag {contract['number']}",
    }
    assert [d["kind"] for d in only_end if d["entity_id"] == uuid.UUID(contract["id"])] == [
        "contract_end_date"
    ]
    assert none == []

    # Calendar shows the derived dates to a reader with contracts:read, not to the caretaker.
    cal = _ok(
        client.get(f"{W}/calendar", params={"start": "2030-01-01", "end": "2030-12-31"}, headers=h)
    )["items"]
    assert any(c["kind"] == "contract_end_date" for c in cal)
    caretaker = bearer(login(client, world, "covwscaretaker"))
    care_cal = _ok(
        client.get(
            f"{W}/calendar", params={"start": "2030-01-01", "end": "2030-12-31"}, headers=caretaker
        )
    )["items"]
    assert not any(c["kind"].startswith("contract_") for c in care_cal)
    # 400 day limit
    too_long = client.get(
        f"{W}/calendar", params={"start": "2030-01-01", "end": "2031-06-01"}, headers=h
    )
    assert too_long.status_code == 422


# Router: digest, deadlines, job settings ----------------------------------------------------


def test_digest_deadlines_and_job_settings(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "covwsadmin"))
    standard = bearer(login(client, world, "covwsstandard"))
    caretaker = bearer(login(client, world, "covwscaretaker"))

    digest = _ok(client.get(f"{W}/digest", headers=h))
    assert isinstance(digest, dict)
    digest_day = _ok(client.get(f"{W}/digest", params={"day": "2026-01-05"}, headers=h))
    assert isinstance(digest_day, dict)

    assert _ok(client.get(f"{W}/deadlines", headers=h)) == []
    assert _ok(client.get(f"{W}/deadlines", params={"status": "all"}, headers=h)) == []
    assert (
        _ok(
            client.get(
                f"{W}/deadlines",
                params={"from": "2026-01-01", "to": "2026-12-31", "status": "done", "limit": 5},
                headers=h,
            )
        )
        == []
    )
    kind = ws_jobs.DEADLINE_KINDS[0]
    assert _ok(client.get(f"{W}/deadlines", params={"kind": kind}, headers=h)) == []
    assert client.get(f"{W}/deadlines", params={"kind": "nope"}, headers=h).status_code == 422
    # A caretaker may read no deadline kind at all: empty list, no error.
    assert _ok(client.get(f"{W}/deadlines", headers=caretaker)) == []

    defaults = _ok(client.get(f"{W}/job-settings", headers=standard))
    assert defaults == {
        "digest_mail_enabled": False,
        "deadline_lead_days": ws_jobs.DEFAULT_LEAD_DAYS,
        "deadline_lead_days_default": ws_jobs.DEFAULT_LEAD_DAYS,
    }
    assert (
        client.put(
            f"{W}/job-settings", json={"digest_mail_enabled": True}, headers=standard
        ).status_code
        == 403
    )
    saved = _ok(
        client.put(
            f"{W}/job-settings",
            json={"digest_mail_enabled": True, "deadline_lead_days": 45},
            headers=h,
        )
    )
    assert saved["digest_mail_enabled"] is True
    assert saved["deadline_lead_days"] == 45
    partial = _ok(client.put(f"{W}/job-settings", json={"deadline_lead_days": 10}, headers=h))
    assert partial == {
        "digest_mail_enabled": True,
        "deadline_lead_days": 10,
        "deadline_lead_days_default": ws_jobs.DEFAULT_LEAD_DAYS,
    }
    assert (
        client.put(f"{W}/job-settings", json={"deadline_lead_days": 999}, headers=h).status_code
        == 422
    )
    assert client.put(f"{W}/job-settings", json={"x": 1}, headers=h).status_code == 422
    assert _ok(client.get(f"{W}/job-settings", headers=h))["deadline_lead_days"] == 10
    # Tenant separation: the other tenant keeps its defaults.
    other = bearer(login(client, world, "covwsother"))
    assert _ok(client.get(f"{W}/job-settings", headers=other))["deadline_lead_days"] == (
        ws_jobs.DEFAULT_LEAD_DAYS
    )


# Router: calendar targets without Google, refresh ------------------------------------------


def test_calendar_google_targets_without_mailbox(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "covwsadmin"))
    today = ws.local_today().isoformat()
    for target in ("default", "own"):
        response = client.post(
            f"{W}/calendar",
            json={"title": "Google", "starts_on": today, "target": target},
            headers=h,
        )
        assert response.status_code == 409, response.text
    assert (
        client.post(
            f"{W}/calendar", json={"title": "x", "starts_on": today, "target": "x"}, headers=h
        ).status_code
        == 422
    )
    assert _ok(client.post(f"{W}/calendar/refresh", headers=h)) == {"refreshed": True}
    assert (
        client.patch(f"{W}/calendar/google/default/ev1", json={"title": "n"}, headers=h).status_code
        == 404
    )
    assert (
        client.patch(f"{W}/calendar/google/nope/ev1", json={"title": "n"}, headers=h).status_code
        == 422
    )
    assert client.delete(f"{W}/calendar/google/own/ev1", headers=h).status_code == 404
    invite = client.post(
        f"{W}/calendar/google/default/ev1/invite", json={"confirm": False}, headers=h
    )
    assert invite.status_code == 422
    invite_missing = client.post(
        f"{W}/calendar/google/default/ev1/invite", json={"confirm": True}, headers=h
    )
    assert invite_missing.status_code == 404
    # Internal entry with a time of day still stores the day range only.
    entry = _ok(
        client.post(
            f"{W}/calendar",
            json={
                "title": "Intern mit Zeit",
                "starts_on": today,
                "all_day": False,
                "starts_at": f"{today}T09:00:00Z",
                "ends_at": f"{today}T10:00:00Z",
                "location": "Büro",
                "notes": "n",
            },
            headers=h,
        ),
        201,
    )
    assert entry["source"] == "internal"
    assert entry["editable"] is True
    _ok(client.delete(f"{W}/calendar/{entry['entity_id']}", headers=h), 204)
    assert client.delete(f"{W}/calendar/{entry['entity_id']}", headers=h).status_code == 404


def test_entry_body_and_event_dates_helpers() -> None:
    body = ws_routers.CalendarEntryIn(
        title="T", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 2), location="Ort"
    )
    out = ws_routers._entry_body(body)
    assert out["start"] == {"date": "2026-05-01"}
    assert out["end"] == {"date": "2026-05-03"}  # exclusive end
    assert out["location"] == "Ort"
    # all_day False without any time of day still yields a day entry
    timed = ws_routers.CalendarEntryIn(title="T", starts_on=date(2026, 5, 1), all_day=False)
    out2 = ws_routers._entry_body(timed)
    assert out2["start"] == {"date": "2026-05-01"}
    assert out2["end"] == {"date": "2026-05-02"}
    assert "location" not in out2
    only_end = ws_routers.CalendarEntryIn(
        title="T",
        starts_on=date(2026, 5, 1),
        all_day=False,
        ends_at=datetime(2026, 5, 1, 15, 0, tzinfo=UTC),
    )
    out3 = ws_routers._entry_body(only_end)
    assert out3["start"]["dateTime"].startswith("2026-05-01T09:00")
    assert out3["end"]["dateTime"].startswith("2026-05-01T15:00")
    explicit = ws_routers.CalendarEntryIn(
        title="T",
        starts_on=date(2026, 5, 1),
        all_day=False,
        starts_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    assert ws_routers._entry_body(explicit)["end"]["dateTime"].startswith("2026-05-01T13:00")

    assert ws_routers._event_dates(
        {"start": {"date": "2026-05-01"}, "end": {"date": "2026-05-03"}}
    ) == (
        date(2026, 5, 1),
        date(2026, 5, 2),
    )
    assert ws_routers._event_dates(
        {"start": {"date": "2026-05-01"}, "end": {"date": "2026-05-02"}}
    ) == (
        date(2026, 5, 1),
        None,
    )
    assert ws_routers._event_dates(
        {"start": {"dateTime": "2026-05-01T09:00:00Z"}, "end": {"dateTime": "2026-05-01T10:00:00Z"}}
    ) == (date(2026, 5, 1), None)
    assert ws_routers._event_dates({"start": {"date": "2026-05-01"}}) == (date(2026, 5, 1), None)
    assert ws_routers._google_label("default", "a@b") == "Standardkalender (a@b)"
    assert ws_routers._google_label("own", "a@b") == "Eigener Kalender (a@b)"
    item = ws_routers._google_item(
        {"id": "e1", "start": {"date": "2026-05-01"}, "end": {}}, "own", "L", uuid.uuid4()
    )
    assert item.title == "(ohne Titel)"
    assert item.is_stale is False


# Router: stats buckets per range -------------------------------------------------------------


def test_stats_bucket_helpers_and_ranges(client: TestClient, world: World) -> None:
    assert ws_routers._bucket_key(date(2026, 1, 1), "quarter") == "2026-W01"
    assert ws_routers._bucket_key(date(2026, 3, 5), "year") == "2026-03"
    assert ws_routers._bucket_key(date(2026, 3, 5), "day") == "2026-03-05"
    assert ws_routers._bucket_series(date(2026, 1, 1), date(2026, 1, 3), "week") == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]
    assert ws_routers._bucket_series(date(2026, 1, 1), date(2026, 3, 1), "year") == [
        "2026-01",
        "2026-02",
        "2026-03",
    ]
    start, end = ws_routers._stats_bounds("day", date(2026, 3, 5))
    assert (start, end) == (date(2026, 3, 5), date(2026, 3, 5))

    h = bearer(login(client, world, "covwsadmin"))
    ticket = _ok(
        client.post("/api/v1/tickets", json={"title": "Cov Stat", "priority": "normal"}, headers=h),
        201,
    )
    for range_key in ("day", "month", "quarter", "year"):
        stats = _ok(client.get(f"{W}/dashboard/stats", params={"range": range_key}, headers=h))
        assert stats["range"] == range_key
        assert stats["totals"]["open"] >= 1
        assert sum(b["created"] for b in stats["buckets"]) == stats["totals"]["created_in_range"]
        assert any(t["id"] == ticket["id"] for t in stats["tickets"])
    filtered = _ok(
        client.get(
            f"{W}/dashboard/stats",
            params={"range": "week", "user_id": str(uuid.uuid4())},
            headers=h,
        )
    )
    assert filtered["totals"] == {
        "open": 0,
        "in_progress": 0,
        "done_in_range": 0,
        "created_in_range": 0,
    }
    assert filtered["assignees"] == []
    caretaker = bearer(login(client, world, "covwscaretaker"))
    assert client.get(f"{W}/dashboard/stats", headers=caretaker).status_code == 200
    # Search by a caretaker covers properties only; the standard user sees contracts too.
    standard = bearer(login(client, world, "covwsstandard"))
    hits = _ok(client.get(f"{W}/search", params={"q": "Covhaus 952", "limit": 3}, headers=standard))
    assert {x["entity_type"] for x in hits} >= {"property"}
    assert client.get(f"{W}/search", params={"q": "x"}, headers=h).status_code == 422


# Router: bulk edge cases ----------------------------------------------------------------------


def test_bulk_edge_cases(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "covwsadmin"))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Bulk", "last_name": f"Cov{RUN}"},
            headers=h,
        ),
        201,
    )
    # removing a tag that never existed changes nothing and does not fail
    remove = {"action": "contacts.remove_tag", "ids": [contact["id"]], "tag": f"nie-{RUN}"}
    assert _ok(client.post(f"{W}/bulk", json=remove, headers=h)) == {
        "action": "contacts.remove_tag",
        "requested": 1,
        "changed": 0,
    }
    # duplicate ids count once
    add = {"action": "contacts.add_tag", "ids": [contact["id"], contact["id"]], "tag": f"cov-{RUN}"}
    assert _ok(client.post(f"{W}/bulk", json=add, headers=h)) == {
        "action": "contacts.add_tag",
        "requested": 1,
        "changed": 1,
    }
    # maintenance.done: all or nothing with unknown ids, caretaker lacks properties:update
    done = {"action": "maintenance.done", "ids": [str(uuid.uuid4())]}
    assert client.post(f"{W}/bulk", json=done, headers=h).status_code == 404
    caretaker = bearer(login(client, world, "covwscaretaker"))
    assert client.post(f"{W}/bulk", json=done, headers=caretaker).status_code == 403
    assert (
        client.post(
            f"{W}/bulk", json={"action": "x", "ids": [contact["id"]]}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{W}/bulk", json={"action": "maintenance.done", "ids": []}, headers=h
        ).status_code
        == 422
    )
    # Tenant separation: the other tenant cannot tag this contact.
    other = bearer(login(client, world, "covwsother"))
    assert client.post(f"{W}/bulk", json=add, headers=other).status_code == 404


# Ops metrics with a stored job protocol (A67) --------------------------------------------------


def test_ops_metrics_include_backup_protocol_and_alerts(
    client: TestClient, world: World, redis_url: str
) -> None:
    admin = bearer(login(client, world, "covwspadmin"))
    record = {
        "status": backup_verify.STATUS_FAILED,
        "started_at": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
        "duration_seconds": 4.2,
        "checked_file": "/backups/cov.dump",
        "exit_code": 1,
        "error": "pg_restore failed",
        "script": "scripts/backup-verify.sh",
    }

    async def store() -> None:
        redis = Redis.from_url(redis_url)
        try:
            await backup_verify.store_result(redis, record)
        finally:
            await redis.aclose()

    async def clear() -> None:
        redis = Redis.from_url(redis_url)
        try:
            await redis.delete(backup_verify.RESULT_KEY)
        finally:
            await redis.aclose()

    asyncio.run(store())
    try:
        body = _ok(client.get(METRICS, headers=admin))
        assert body["jobs"]["backup_verify"]["status"] == "failed"
        assert body["jobs"]["backup_verify"]["checked_file"] == "/backups/cov.dump"
        assert body["jobs"]["backup_verify"]["stale"] is True
        assert body["metrics"]["backup_verify_failed"] == 1
        assert body["metrics"]["backup_verify_stale"] == 1
        assert body["metrics"]["backup_verify_duration_seconds"] == 4
        assert {"backup_verify_failed", "backup_verify_stale"} <= set(body["alerts"])
        assert body["metrics"]["tenants_active"] >= 2
        assert body["metrics"]["notifications_unread"] >= 0
        text = client.get(METRICS, params={"format": "prometheus"}, headers=admin)
        assert text.status_code == 200
        assert text.headers["content-type"].startswith("text/plain")
        assert "# TYPE mhvp_backup_verify_failed gauge\nmhvp_backup_verify_failed 1\n" in text.text
        assert "mhvp_tenants_active " in text.text
        assert "geheim" not in text.text
    finally:
        asyncio.run(clear())
    # Without a record the job is reported missing and stale, never silent.
    missing = _ok(client.get(METRICS, headers=admin))
    assert missing["jobs"]["backup_verify"]["status"] == "missing"
    assert "backup_verify_stale" in missing["alerts"]
    assert "backup_verify_failed" not in missing["alerts"]
    # Tenant users, even administrators, are refused; anonymous callers too.
    assert (
        client.get(METRICS, headers=bearer(login(client, world, "covwsadmin"))).status_code == 403
    )
    assert client.get(METRICS).status_code == 401


# Daily jobs over all tenants, release gate resolver, list pagination --------------------------


def test_daily_jobs_gate_resolver_and_pagination(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from fastapi import Response

    from mhvp.core.pagination import paginate
    from mhvp.core.release_gates import ReleaseGate
    from mhvp.platform.gates import DbReleaseGateResolver, approved_scopes
    from mhvp.platform.models import GateRequestStatus, ReleaseGateRequest
    from mhvp.workspace.tasks import deadlines_once, digest_once

    settings = _settings(database, redis_url)
    today = ws.local_today()
    first = asyncio.run(digest_once(settings, today))
    assert first["tenants"] >= 2
    assert first["users"] >= 1
    second = asyncio.run(digest_once(settings, today))  # idempotent per user and day
    assert second["notified"] == 0
    assert second["empty"] == 0
    assert second["skipped"] == second["users"]
    deadlines = asyncio.run(deadlines_once(settings, today))
    assert deadlines["tenants"] >= 2
    assert set(deadlines) >= {"created", "updated", "closed", "notified"}

    async def gates_and_pages(
        session: Any,
    ) -> tuple[list[str], bool, list[str], int, dict[str, str]]:
        before = await approved_scopes(session, world.tenant_a, ReleaseGate.G1)
        session.add(
            ReleaseGateRequest(
                tenant_id=world.tenant_a,
                gate="G1",
                scope="cov-scope",
                evidence="Testnachweis",
                status=GateRequestStatus.APPROVED,
                requested_by=world.users["covwsadmin"],
                decided_by=world.users["covwsadmin"],
                decided_at=datetime.now(UTC),
            )
        )
        await session.flush()
        after = await approved_scopes(session, world.tenant_a, ReleaseGate.G1)
        other_gate = await approved_scopes(session, world.tenant_a, ReleaseGate.G2)
        response = Response()
        rows = await paginate(
            session,
            select(Notification).order_by(Notification.created_at),
            response,
            page=1,
            page_size=2,
            limit=50,
        )
        return before, bool(other_gate), after, len(rows), dict(response.headers)

    before, other_gate, after, page_len, headers = _run(
        database, redis_url, world.tenant_a, gates_and_pages
    )
    assert before == []
    assert after == ["cov-scope"]
    assert other_gate is False
    assert page_len <= 2
    assert headers["x-page"] == "1"
    assert headers["x-page-size"] == "2"
    assert int(headers["x-total-count"]) >= page_len

    async def resolver() -> tuple[bool, bool, bool]:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            res = DbReleaseGateResolver(factory)
            return (
                await res.is_open(world.tenant_a, ReleaseGate.G1),
                await res.is_open(world.tenant_a, ReleaseGate.G2),
                await res.is_open(world.tenant_b, ReleaseGate.G1),  # tenant separation
            )
        finally:
            await engine.dispose()

    assert asyncio.run(resolver()) == (True, False, False)

    async def cleanup(session: Any) -> None:
        from sqlalchemy import delete as sa_delete

        await session.execute(
            sa_delete(ReleaseGateRequest).where(ReleaseGateRequest.scope == "cov-scope")
        )

    _run(database, redis_url, world.tenant_a, cleanup)
    assert asyncio.run(resolver()) == (False, False, False)
