"""Ticket and mail analytics (/api/v1/workspace/ticket-analytics, operator 26.09.2026):
hand computed counts per bucket, response time percentiles, backlog, throughput, user and
mailbox filters, personal versus default mailbox classification, tenant separation and
permission."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, time, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from mhvp.workspace.ticket_analytics import build_window, percentile
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace/ticket-analytics"
LOCAL = ZoneInfo("Europe/Berlin")


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ta-{RUN}", name=f"TA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ta2-{RUN}", name=f"TA2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("taadmin", a, "tenant_admin"),
            ("taagent1", a, "standard"),
            ("taagent2", a, "standard"),
            ("tasupport", a, "support"),
            ("taother", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=False,
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


def _run(settings: Any, tenant_id: uuid.UUID, work: Any) -> Any:
    """Run ``work(session)`` inside the tenant scope (RLS), like a request would."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _go() -> Any:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def _ticket(client: TestClient, h: dict[str, str], title: str, assignee: uuid.UUID | None) -> str:
    row = _ok(client.post("/api/v1/tickets", json={"title": title}, headers=h), 201)
    if assignee is not None:
        _ok(
            client.patch(
                f"/api/v1/tickets/{row['id']}", json={"assignee_user_id": str(assignee)}, headers=h
            )
        )
    return str(row["id"])


def _close(client: TestClient, h: dict[str, str], ticket_id: str) -> None:
    _ok(
        client.patch(
            f"/api/v1/tickets/{ticket_id}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )


def _set_created(settings: Any, tenant: uuid.UUID, ticket_id: str, at: datetime) -> None:
    from mhvp.tickets.models import Ticket

    async def work(session: Any) -> None:
        result = await session.execute(
            update(Ticket).where(Ticket.id == uuid.UUID(ticket_id)).values(created_at=at)
        )
        assert result.rowcount == 1

    _run(settings, tenant, work)


def _set_status_event(
    settings: Any, tenant: uuid.UUID, ticket_id: str, to_status: str, at: datetime
) -> None:
    from mhvp.tickets.models import TicketEvent

    async def work(session: Any) -> None:
        result = await session.execute(
            update(TicketEvent)
            .where(
                TicketEvent.ticket_id == uuid.UUID(ticket_id),
                TicketEvent.kind == "status",
                TicketEvent.data["to"].astext == to_status,
            )
            .values(created_at=at)
        )
        assert result.rowcount == 1

    _run(settings, tenant, work)


def _mailbox(
    settings: Any, tenant: uuid.UUID, address: str, *, default: bool, users: list[uuid.UUID]
) -> uuid.UUID:
    from mhvp.communication.models import Mailbox, MailboxUser

    async def work(session: Any) -> uuid.UUID:
        box = Mailbox(tenant_id=tenant, address=address, kind="gmail", is_default=default)
        session.add(box)
        await session.flush()
        for uid in users:
            session.add(MailboxUser(tenant_id=tenant, mailbox_id=box.id, user_id=uid))
        return box.id

    return cast(uuid.UUID, _run(settings, tenant, work))


def _mail(
    settings: Any,
    tenant: uuid.UUID,
    *,
    direction: str,
    at: datetime,
    mailbox_id: uuid.UUID | None,
    ticket_id: str | None,
    created_by: uuid.UUID | None = None,
    status: str | None = None,
) -> None:
    from mhvp.communication.models import Message

    async def work(session: Any) -> None:
        session.add(
            Message(
                tenant_id=tenant,
                direction=direction,
                status=status or ("new" if direction == "in" else "sent"),
                mailbox_id=mailbox_id,
                from_address="mieter@example.com",
                to_addresses=["hv@example.com"],
                subject=f"Mail {RUN}",
                body="Text",
                ticket_id=uuid.UUID(ticket_id) if ticket_id else None,
                created_at=at,
                created_by=created_by,
                received_at=at if direction == "in" else None,
                sent_at=at if direction == "out" else None,
            )
        )

    _run(settings, tenant, work)


def _comment(
    settings: Any, tenant: uuid.UUID, ticket_id: str, user_id: uuid.UUID, at: datetime
) -> None:
    from mhvp.tickets.models import TicketComment

    async def work(session: Any) -> None:
        session.add(
            TicketComment(
                tenant_id=tenant,
                ticket_id=uuid.UUID(ticket_id),
                internal=True,
                author_user_id=user_id,
                body="Rückruf erledigt",
                created_at=at,
            )
        )

    _run(settings, tenant, work)


def test_percentile_linear_interpolation() -> None:
    assert percentile([], 0.5) is None
    assert percentile([30.0], 0.9) == 30.0
    assert percentile([30.0, 60.0], 0.5) == 45.0
    # Position (n-1)*q = 0.9 between 30 and 60: 30 + 0.9 * 30.
    assert percentile([60.0, 30.0], 0.9) == 57.0
    assert percentile([10.0, 20.0, 30.0, 40.0], 0.5) == 25.0


def test_window_buckets() -> None:
    from datetime import date

    week = build_window("week", date(2026, 9, 26))
    assert week.unit == "day"
    assert len(week.starts) == 7
    assert week.keys[0] == "2026-09-20T00:00:00+02:00"
    day = build_window("day", date(2026, 9, 26))
    assert day.unit == "hour"
    assert len(day.starts) == 24
    quarter = build_window("quarter", date(2026, 9, 26))
    assert quarter.unit == "week"
    assert quarter.starts[0].weekday() == 0
    year = build_window("year", date(2026, 9, 26))
    assert year.unit == "month"
    # 364 days back is 27.09.2025, aligned to the month start: 13 month buckets.
    assert year.keys[0] == "2025-09-01T00:00:00+02:00"
    assert len(year.starts) == 13
    # Custom range: day buckets up to 31 days, DST change keeps whole days.
    custom = build_window(
        "custom", date(2026, 9, 26), date_from=date(2026, 3, 28), date_to=date(2026, 3, 30)
    )
    assert custom.keys == [
        "2026-03-28T00:00:00+01:00",
        "2026-03-29T00:00:00+01:00",
        "2026-03-30T00:00:00+02:00",
    ]
    with pytest.raises(ValueError, match="before"):
        build_window(
            "custom", date(2026, 9, 26), date_from=date(2026, 1, 1), date_to=date(2025, 1, 1)
        )
    with pytest.raises(ValueError, match="limited"):
        build_window(
            "custom", date(2026, 9, 26), date_from=date(2024, 1, 1), date_to=date(2026, 1, 1)
        )


def test_ticket_analytics(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    tenant = world.tenant_a
    h = bearer(login(client, world, "taadmin"))
    other = bearer(login(client, world, "taother"))
    admin = world.users["taadmin"]
    a1 = world.users["taagent1"]
    a2 = world.users["taagent2"]

    today = local_today()
    window = build_window("week", today)
    # Day D is two days ago, D1 one day ago, both inside the week window (7 day buckets).
    d = datetime.combine(today - timedelta(days=2), time(0), tzinfo=LOCAL)
    d1 = d + timedelta(days=1)
    before = window.start - timedelta(days=1)

    default_box = _mailbox(settings, tenant, f"info-{RUN}@example.com", default=True, users=[])
    personal_box = _mailbox(settings, tenant, f"a1-{RUN}@example.com", default=False, users=[a1])

    # T1: created D 08:00 from the default mailbox, assigned a1, reply by a1 after 60 minutes,
    # closed by admin after 180 minutes.
    t1 = _ticket(client, h, f"Heizung {RUN}", a1)
    _set_created(settings, tenant, t1, d.replace(hour=8))
    _mail(
        settings, tenant, direction="in", at=d.replace(hour=8), mailbox_id=default_box, ticket_id=t1
    )
    _mail(
        settings,
        tenant,
        direction="out",
        at=d.replace(hour=9),
        mailbox_id=default_box,
        ticket_id=t1,
        created_by=a1,
    )
    _close(client, h, t1)
    _set_status_event(settings, tenant, t1, "done", d.replace(hour=11))

    # T2: created D 10:00 from the personal mailbox, assigned a1, staff comment after 30
    # minutes, stays open. A draft (not sent) must not count as outbound.
    t2 = _ticket(client, h, f"Aufzug {RUN}", a1)
    _set_created(settings, tenant, t2, d.replace(hour=10))
    _mail(
        settings,
        tenant,
        direction="in",
        at=d.replace(hour=10),
        mailbox_id=personal_box,
        ticket_id=t2,
    )
    _comment(settings, tenant, t2, a1, d.replace(hour=10, minute=30))
    _mail(
        settings,
        tenant,
        direction="out",
        at=d.replace(hour=12),
        mailbox_id=personal_box,
        ticket_id=t2,
        created_by=a1,
        status="draft",
    )

    # T3: created D1 09:00 without mail, assigned a2, closed after 180 minutes and reopened
    # one hour later (still open at the end).
    t3 = _ticket(client, h, f"Klingel {RUN}", a2)
    _set_created(settings, tenant, t3, d1.replace(hour=9))
    _close(client, h, t3)
    _set_status_event(settings, tenant, t3, "done", d1.replace(hour=12))
    _ok(client.patch(f"/api/v1/tickets/{t3}", json={"status": "in_progress"}, headers=h))
    _set_status_event(settings, tenant, t3, "in_progress", d1.replace(hour=13))

    # T4: created and closed before the window (no backlog). T5: created before the window,
    # still open (backlog at the window start = 1).
    t4 = _ticket(client, h, f"Alt erledigt {RUN}", None)
    _set_created(settings, tenant, t4, before - timedelta(days=2))
    _close(client, h, t4)
    _set_status_event(settings, tenant, t4, "done", before - timedelta(days=1))
    t5 = _ticket(client, h, f"Alt offen {RUN}", None)
    _set_created(settings, tenant, t5, before)

    # Foreign tenant: one ticket with an inbound mail, never visible in tenant A.
    _ticket(client, other, f"Fremd {RUN}", None)

    data = _ok(client.get(W, params={"range": "week"}, headers=h))
    assert data["range"] == "week"
    assert data["bucket"] == "day"
    assert data["timezone"] == "Europe/Berlin"
    assert len(data["buckets"]) == 7
    assert [b["key"] for b in data["buckets"]] == window.keys

    totals = data["totals"]
    assert totals["tickets_created"] == 3
    assert totals["tickets_closed"] == 2
    assert totals["tickets_reopened"] == 1
    assert totals["backlog_start"] == 1
    # 1 + 3 created - 2 closed + 1 reopened = T2, T3, T5 open.
    assert totals["backlog_end"] == 3
    assert totals["inbound"] == 2
    assert totals["outbound"] == 1
    assert totals["replies_per_ticket"] == 0.33
    # First responses 60 (T1) and 30 (T2) minutes: median 45, p90 = 30 + 0.9 * 30.
    assert totals["first_response_median_minutes"] == 45.0
    assert totals["first_response_p90_minutes"] == 57.0
    assert totals["time_to_close_median_minutes"] == 180.0
    # 2 closed over 7 days: 2 / (7 * 24 * 60) per minute, times 60 per hour.
    assert totals["throughput_per_minute"] == 0.0
    assert totals["throughput_per_hour"] == 0.01

    by_key = {b["key"]: b for b in data["buckets"]}
    bd = by_key[d.isoformat()]
    assert bd["tickets_created"] == 2
    assert bd["tickets_closed"] == 1
    assert bd["tickets_reopened"] == 0
    assert bd["backlog_end"] == 2
    assert bd["inbound"] == 2
    assert bd["outbound"] == 1
    assert bd["replies_per_ticket"] == 0.5
    assert bd["first_response_median_minutes"] == 45.0
    assert bd["time_to_close_median_minutes"] == 180.0
    assert bd["minutes"] == 1440.0
    assert bd["throughput_per_hour"] == 0.04
    bd1 = by_key[d1.isoformat()]
    assert bd1["tickets_created"] == 1
    assert bd1["tickets_closed"] == 1
    assert bd1["tickets_reopened"] == 1
    assert bd1["backlog_end"] == 3
    assert bd1["first_response_median_minutes"] is None
    first_key = window.keys[0]
    assert by_key[first_key]["backlog_end"] == 1
    assert by_key[first_key]["throughput_per_hour"] == 0.0

    staff = {s["user_id"]: s for s in data["staff"]}
    assert staff[str(a1)] == {
        "user_id": str(a1),
        "closed": 0,
        "created": 0,
        "replies_sent": 1,
        "first_response_median_minutes": 45.0,
        "open_assigned": 1,
    }
    assert staff[str(admin)]["closed"] == 2
    assert staff[str(admin)]["created"] == 3
    assert staff[str(a2)]["open_assigned"] == 1
    assert staff[str(a2)]["first_response_median_minutes"] is None

    boxes = {m["mailbox_id"]: m for m in data["mailboxes"]}
    assert boxes[str(default_box)]["kind"] == "default"
    assert boxes[str(default_box)]["inbound"] == 1
    assert boxes[str(default_box)]["outbound"] == 1
    assert boxes[str(default_box)]["tickets_created"] == 1
    assert boxes[str(default_box)]["share_inbound_pct"] == 50.0
    assert boxes[str(personal_box)]["kind"] == "personal"
    assert boxes[str(personal_box)]["inbound"] == 1
    assert boxes[str(personal_box)]["outbound"] == 0
    assert boxes[str(personal_box)]["tickets_created"] == 1
    assert data["by_kind"]["personal"]["inbound"] == 1
    assert data["by_kind"]["default"]["inbound"] == 1
    assert data["by_kind"]["other"]["tickets_created"] == 1  # T3 without mail
    assert {m["kind"] for m in data["all_mailboxes"]} >= {"default", "personal"}

    # User filter: tickets assigned to a1, outbound by a1, inbound of a1's tickets.
    f1 = _ok(client.get(W, params={"range": "week", "user_id": str(a1)}, headers=h))
    assert f1["totals"]["tickets_created"] == 2
    assert f1["totals"]["tickets_closed"] == 1
    assert f1["totals"]["tickets_reopened"] == 0
    assert f1["totals"]["inbound"] == 2
    assert f1["totals"]["outbound"] == 1
    assert f1["totals"]["backlog_start"] == 0
    assert f1["totals"]["backlog_end"] == 1

    # Mailbox kind: personal only (T2 from the personal mailbox).
    fp = _ok(client.get(W, params={"range": "week", "mailbox_kind": "personal"}, headers=h))
    assert fp["totals"]["tickets_created"] == 1
    assert fp["totals"]["tickets_closed"] == 0
    assert fp["totals"]["inbound"] == 1
    assert fp["totals"]["outbound"] == 0
    assert [m["mailbox_id"] for m in fp["mailboxes"]] == [str(personal_box)]
    assert fp["by_kind"]["default"]["inbound"] == 0

    # Single mailbox: the default one (T1 with its reply and closing).
    fd = _ok(client.get(W, params={"range": "week", "mailbox_id": str(default_box)}, headers=h))
    assert fd["totals"]["tickets_created"] == 1
    assert fd["totals"]["tickets_closed"] == 1
    assert fd["totals"]["outbound"] == 1
    # Contradicting filters (default mailbox, kind personal) match nothing.
    fx = _ok(
        client.get(
            W,
            params={"range": "week", "mailbox_id": str(default_box), "mailbox_kind": "personal"},
            headers=h,
        )
    )
    assert fx["totals"]["tickets_created"] == 0
    assert fx["totals"]["inbound"] == 0

    # Hour buckets for a single day and explicit bucket sizes.
    day = _ok(client.get(W, params={"range": "day"}, headers=h))
    assert day["bucket"] == "hour"
    assert len(day["buckets"]) == 24
    custom = _ok(
        client.get(
            W,
            params={
                "range": "custom",
                "from": (today - timedelta(days=2)).isoformat(),
                "to": (today - timedelta(days=1)).isoformat(),
                "bucket": "day",
            },
            headers=h,
        )
    )
    assert custom["totals"]["tickets_created"] == 3
    assert [b["tickets_created"] for b in custom["buckets"]] == [2, 1]
    # Backlog before the custom window: T5 (open) only; T4 closed before.
    assert custom["totals"]["backlog_start"] == 1

    # Validation: unknown range, custom without dates, dates in the wrong order.
    assert client.get(W, params={"range": "century"}, headers=h).status_code == 422
    assert client.get(W, params={"range": "custom"}, headers=h).status_code == 422
    assert (
        client.get(
            W, params={"range": "custom", "from": "2026-02-01", "to": "2026-01-01"}, headers=h
        ).status_code
        == 422
    )

    # Tenant separation: the other tenant sees only its own ticket and no mailboxes of A.
    other_data = _ok(client.get(W, params={"range": "week"}, headers=other))
    assert other_data["totals"]["tickets_created"] == 1
    assert other_data["totals"]["inbound"] == 0
    assert other_data["all_mailboxes"] == []

    # Permission: the support role has no tickets:read.
    support = bearer(login(client, world, "tasupport"))
    assert client.get(W, params={"range": "week"}, headers=support).status_code == 403
