"""M19-09 traffic light of the ticket list (operator 26.09.2026): ``last_staff_activity_at``,
``last_inbound_at``, ``attention`` and the sort orders ``urgency`` (default) and
``created_desc``. Time travel by backdating rows inside the tenant scope. Only actions by
staff reset the clock; inbound mails and portal comments do not."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

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
        a, _ = await services.provision_tenant(factory, slug=f"tka-{RUN}", name=f"Ampel {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"tkab-{RUN}", name=f"AmpelB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant, name in ((a, "m19aadmin"), (b, "m19aadminb")):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def db(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _now() -> datetime:
    return datetime.now(UTC)


def _run(settings: Any, tenant_id: uuid.UUID, work: Any) -> None:
    """Run ``work(session)`` inside the tenant scope (RLS), like a request would."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _go() -> None:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                await work(session)
        finally:
            await engine.dispose()

    asyncio.run(_go())


def _backdate_ticket(settings: Any, tenant_id: uuid.UUID, ticket_id: str, at: datetime) -> None:
    from mhvp.tickets.models import Ticket

    async def work(session: Any) -> None:
        result = await session.execute(
            update(Ticket).where(Ticket.id == uuid.UUID(ticket_id)).values(created_at=at)
        )
        assert result.rowcount == 1

    _run(settings, tenant_id, work)


def _backdate_staff_events(
    settings: Any, tenant_id: uuid.UUID, ticket_id: str, at: datetime
) -> None:
    from mhvp.tickets.models import TicketEvent

    async def work(session: Any) -> None:
        result = await session.execute(
            update(TicketEvent)
            .where(TicketEvent.ticket_id == uuid.UUID(ticket_id))
            .values(created_at=at)
        )
        assert result.rowcount >= 1

    _run(settings, tenant_id, work)


def _backdate_out_mails(settings: Any, tenant_id: uuid.UUID, ticket_id: str, at: datetime) -> None:
    from mhvp.communication.models import Message

    async def work(session: Any) -> None:
        result = await session.execute(
            update(Message)
            .where(Message.ticket_id == uuid.UUID(ticket_id), Message.direction == "out")
            .values(created_at=at)
        )
        assert result.rowcount >= 1

    _run(settings, tenant_id, work)


def _mail(
    settings: Any, tenant_id: uuid.UUID, ticket_id: str, direction: str, at: datetime
) -> None:
    from mhvp.communication.models import Message

    async def work(session: Any) -> None:
        session.add(
            Message(
                tenant_id=tenant_id,
                direction=direction,
                status="new" if direction == "in" else "sent",
                from_address="mieter@example.com" if direction == "in" else "hv@example.com",
                to_addresses=["hv@example.com"] if direction == "in" else ["mieter@example.com"],
                subject=f"Mail {direction} {RUN}",
                body="Text",
                ticket_id=uuid.UUID(ticket_id),
                created_at=at,
                received_at=at if direction == "in" else None,
                sent_at=at if direction == "out" else None,
            )
        )

    _run(settings, tenant_id, work)


def _portal_comment(
    settings: Any, tenant_id: uuid.UUID, ticket_id: str, contact_id: str, at: datetime
) -> None:
    from mhvp.tickets.models import TicketComment

    async def work(session: Any) -> None:
        session.add(
            TicketComment(
                tenant_id=tenant_id,
                ticket_id=uuid.UUID(ticket_id),
                internal=False,
                author_contact_id=uuid.UUID(contact_id),
                body="Erinnerung des Mieters",
                created_at=at,
            )
        )

    _run(settings, tenant_id, work)


def _ticket(c: TestClient, h: dict[str, str], title: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], _ok(c.post("/api/v1/tickets", json={"title": title}, headers=h), 201)
    )


def _row(c: TestClient, h: dict[str, str], ticket_id: str, **params: Any) -> dict[str, Any]:
    rows = _ok(c.get("/api/v1/tickets", params={"include_closed": "true", **params}, headers=h))
    match = [r for r in rows if r["id"] == ticket_id]
    assert len(match) == 1, f"ticket {ticket_id} not listed"
    return cast(dict[str, Any], match[0])


def test_new_ticket_without_reaction_uses_created_at(
    client: TestClient, world: World, db: Any
) -> None:
    h = bearer(login(client, world, "m19aadmin"))
    ticket = _ticket(client, h, f"Ampel neu {RUN}")
    row = _row(client, h, ticket["id"])
    assert row["attention"] == "new"
    assert row["last_staff_activity_at"] is None
    assert row["last_inbound_at"] is None
    assert row["last_activity_at"] == row["created_at"]

    _backdate_ticket(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=30))
    assert _row(client, h, ticket["id"])["attention"] == "stale_24h"
    _backdate_ticket(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=96, minutes=1))
    assert _row(client, h, ticket["id"])["attention"] == "stale_96h"


def test_only_staff_actions_reset_the_clock(client: TestClient, world: World, db: Any) -> None:
    h = bearer(login(client, world, "m19aadmin"))
    ticket = _ticket(client, h, f"Ampel Reaktion {RUN}")
    _backdate_ticket(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=200))
    assert _row(client, h, ticket["id"])["attention"] == "stale_96h"

    # Status change by staff: event with user, resets the clock.
    _ok(client.patch(f"/api/v1/tickets/{ticket['id']}", json={"status": "in_progress"}, headers=h))
    row = _row(client, h, ticket["id"])
    assert row["attention"] == "none"
    assert row["last_staff_activity_at"] is not None
    assert row["last_activity_at"] == row["last_staff_activity_at"]

    # Time travel: the staff event is 30 hours old.
    _backdate_staff_events(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=30))
    assert _row(client, h, ticket["id"])["attention"] == "stale_24h"

    # Inbound mail and a portal comment do not reset the clock but are reported.
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Erna", "last_name": "Mieter"},
            headers=h,
        ),
        201,
    )
    _mail(db, world.tenant_a, ticket["id"], "in", _now() - timedelta(minutes=5))
    _portal_comment(db, world.tenant_a, ticket["id"], contact["id"], _now() - timedelta(minutes=2))
    row = _row(client, h, ticket["id"])
    assert row["attention"] == "stale_24h"
    assert row["last_inbound_at"] is not None
    assert datetime.fromisoformat(row["last_inbound_at"]) > datetime.fromisoformat(
        row["last_staff_activity_at"]
    )

    # Outbound mail by staff resets it.
    _mail(db, world.tenant_a, ticket["id"], "out", _now() - timedelta(minutes=1))
    row = _row(client, h, ticket["id"])
    assert row["attention"] == "none"

    # 100 hours later without any staff action: red, even after a further inbound mail.
    _backdate_staff_events(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=100))
    _backdate_out_mails(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=100))
    _mail(db, world.tenant_a, ticket["id"], "in", _now())
    assert _row(client, h, ticket["id"])["attention"] == "stale_96h"

    # A staff comment (internal) resets the clock again.
    _ok(
        client.post(
            f"/api/v1/tickets/{ticket['id']}/comments",
            json={"body": "Rückruf erfolgt", "internal": True},
            headers=h,
        ),
        201,
    )
    assert _row(client, h, ticket["id"])["attention"] == "none"


def test_closed_tickets_are_hidden_by_default_and_never_stale(
    client: TestClient, world: World, db: Any
) -> None:
    h = bearer(login(client, world, "m19aadmin"))
    ticket = _ticket(client, h, f"Ampel erledigt {RUN}")
    _ok(
        client.patch(
            f"/api/v1/tickets/{ticket['id']}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )
    _backdate_ticket(db, world.tenant_a, ticket["id"], _now() - timedelta(days=30))
    _backdate_staff_events(db, world.tenant_a, ticket["id"], _now() - timedelta(days=20))

    default_rows = _ok(client.get("/api/v1/tickets", headers=h))
    assert not any(r["id"] == ticket["id"] for r in default_rows)
    row = _row(client, h, ticket["id"])
    assert row["attention"] == "closed"


def test_urgency_and_created_desc_sort(client: TestClient, world: World, db: Any) -> None:
    h = bearer(login(client, world, "m19aadmin"))
    tag = f"Sortierung {uuid.uuid4().hex[:6]}"
    red = _ticket(client, h, f"{tag} rot")
    orange = _ticket(client, h, f"{tag} orange")
    fresh = _ticket(client, h, f"{tag} neu")
    closed = _ticket(client, h, f"{tag} erledigt")
    _ok(
        client.patch(
            f"/api/v1/tickets/{closed['id']}",
            json={"status": "done", "resolution": {"kind": "auskunft_erteilt"}},
            headers=h,
        )
    )
    now = _now()
    # The closed one is the oldest of all: with urgency it still comes last.
    _backdate_ticket(db, world.tenant_a, closed["id"], now - timedelta(hours=300))
    _backdate_staff_events(db, world.tenant_a, closed["id"], now - timedelta(hours=299))
    _backdate_ticket(db, world.tenant_a, red["id"], now - timedelta(hours=120))
    _backdate_ticket(db, world.tenant_a, orange["id"], now - timedelta(hours=40))
    _backdate_ticket(db, world.tenant_a, fresh["id"], now - timedelta(hours=1))

    by_urgency = _ok(
        client.get("/api/v1/tickets", params={"q": tag, "include_closed": "true"}, headers=h)
    )
    assert [r["id"] for r in by_urgency] == [red["id"], orange["id"], fresh["id"], closed["id"]]
    assert [r["attention"] for r in by_urgency] == ["stale_96h", "stale_24h", "new", "closed"]

    by_created = _ok(
        client.get(
            "/api/v1/tickets",
            params={"q": tag, "include_closed": "true", "sort": "created_desc"},
            headers=h,
        )
    )
    assert [r["id"] for r in by_created] == [fresh["id"], orange["id"], red["id"], closed["id"]]

    # Pagination keeps the urgency order across pages.
    page_1 = _ok(
        client.get("/api/v1/tickets", params={"q": tag, "page": 1, "page_size": 2}, headers=h)
    )
    page_2 = _ok(
        client.get("/api/v1/tickets", params={"q": tag, "page": 2, "page_size": 2}, headers=h)
    )
    assert [r["id"] for r in page_1] == [red["id"], orange["id"]]
    assert [r["id"] for r in page_2] == [fresh["id"]]

    assert client.get("/api/v1/tickets", params={"sort": "nope"}, headers=h).status_code == 422


def test_dashboard_rows_carry_attention(client: TestClient, world: World, db: Any) -> None:
    h = bearer(login(client, world, "m19aadmin"))
    ticket = _ticket(client, h, f"Ampel Startseite {RUN}")
    _backdate_ticket(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=50))
    stats = _ok(client.get(f"{W}/dashboard/stats", params={"range": "week"}, headers=h))
    rows = [r for r in stats["tickets"] if r["id"] == ticket["id"]]
    assert rows
    assert rows[0]["attention"] == "stale_24h"
    assert rows[0]["last_activity_at"] is not None


def test_tenant_separation(client: TestClient, world: World, db: Any) -> None:
    h_a = bearer(login(client, world, "m19aadmin"))
    h_b = bearer(login(client, world, "m19aadminb"))
    ticket = _ticket(client, h_a, f"Ampel Mandant A {RUN}")
    _backdate_ticket(db, world.tenant_a, ticket["id"], _now() - timedelta(hours=30))
    rows_b = _ok(client.get("/api/v1/tickets", params={"include_closed": "true"}, headers=h_b))
    assert not any(r["id"] == ticket["id"] for r in rows_b)
    # A staff mail inserted by tenant B's scope on A's ticket id is not visible to A (RLS) and
    # therefore does not reset A's clock.
    _mail(db, world.tenant_b, ticket["id"], "out", _now())
    assert _row(client, h_a, ticket["id"])["attention"] == "stale_24h"
