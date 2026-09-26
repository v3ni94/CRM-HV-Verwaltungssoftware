"""Review 26.09.2026 (docs/reviews/2026-09-26-review-tickets-mail.md), H6, H7 and M14:
closing a ticket via PATCH or bulk action stops its SLA clock and emits
``ticket.status_changed``; reopening restarts the clock; GET /tickets paginates with
``page``/``page_size`` and reports the total in ``X-Total-Count``; the SLA backfill starts
clocks for open tickets that were created without one."""

import asyncio
from collections.abc import Iterator
from datetime import datetime
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rv-{RUN}", name=f"Review {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("rvadmin"), display_name="rvadmin", password=PASSWORD
        )
        world.users["rvadmin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ticket(c: TestClient, h: dict[str, str], title: str) -> dict[str, Any]:
    return cast(dict[str, Any], _ok(c.post(T, json={"title": title}, headers=h), 201))


def _clock(c: TestClient, h: dict[str, str], ticket_id: str) -> dict[str, Any]:
    return cast(dict[str, Any], _ok(c.get(f"/api/v1/sla/tickets/{ticket_id}/sla", headers=h)))


def _events(c: TestClient, h: dict[str, str], ticket_id: str) -> list[dict[str, Any]]:
    rows = _ok(
        c.get(
            "/api/v1/tenant/events",
            params={"type": "ticket.status_changed", "page_size": 200},
            headers=h,
        )
    )
    return [e for e in rows if e["entity_id"] == ticket_id]


def test_patch_done_stops_clock_and_emits_status_event(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rvadmin"))
    ticket = _ticket(client, h, f"Uhr Patch {RUN}")
    assert _clock(client, h, ticket["id"])["state"] == "running"

    _ok(client.patch(f"{T}/{ticket['id']}", json={"status": "in_progress"}, headers=h))
    _ok(client.patch(f"{T}/{ticket['id']}", json={"status": "done"}, headers=h))
    clock = _clock(client, h, ticket["id"])
    assert clock["state"] == "done"
    assert clock["resolved_at"] is not None

    events = _events(client, h, ticket["id"])
    assert [(e["payload"]["from"], e["payload"]["to"]) for e in reversed(events)] == [
        ("new", "in_progress"),
        ("in_progress", "done"),
    ]
    detail = _ok(client.get(f"{T}/{ticket['id']}", headers=h))
    assert detail["resolved_at"] is not None

    # Reopening restarts the resolution clock.
    _ok(client.patch(f"{T}/{ticket['id']}", json={"status": "in_progress"}, headers=h))
    clock = _clock(client, h, ticket["id"])
    assert (clock["state"], clock["resolved_at"]) == ("running", None)
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["resolved_at"] is None

    # A forbidden transition changes nothing and emits nothing.
    assert (
        client.patch(f"{T}/{ticket['id']}", json={"status": "closed"}, headers=h).status_code == 409
    )
    assert len(_events(client, h, ticket["id"])) == 3


def test_bulk_status_stops_clocks_and_reports_failures(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rvadmin"))
    first = _ticket(client, h, f"Uhr Bulk 1 {RUN}")
    second = _ticket(client, h, f"Uhr Bulk 2 {RUN}")
    closed = _ticket(client, h, f"Uhr Bulk 3 {RUN}")
    _ok(client.patch(f"{T}/{closed['id']}", json={"status": "done"}, headers=h))
    _ok(client.patch(f"{T}/{closed['id']}", json={"status": "closed"}, headers=h))

    result = _ok(
        client.post(
            f"{T}/bulk-status",
            json={"ticket_ids": [first["id"], second["id"], closed["id"]], "status": "rejected"},
            headers=h,
        )
    )
    assert {c["id"] for c in result["changed"]} == {first["id"], second["id"]}
    assert [f["id"] for f in result["failed"]] == [closed["id"]]
    assert "unzulässig" in result["failed"][0]["reason"]
    for ticket in (first, second):
        assert _clock(client, h, ticket["id"])["state"] == "done"
        events = _events(client, h, ticket["id"])
        assert events[0]["payload"] == {"from": "new", "to": "rejected", "number": ticket["number"]}


def test_list_tickets_paginates_and_stays_a_list(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rvadmin"))
    numbers = [_ticket(client, h, f"Seite {i} {RUN}")["number"] for i in range(5)]

    # Legacy call: plain list, first page, total in the header.
    legacy = client.get(T, params={"q": "Seite", "limit": 2}, headers=h)
    rows = _ok(legacy)
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert int(legacy.headers["x-total-count"]) >= 5
    assert (legacy.headers["x-page"], legacy.headers["x-page-size"]) == ("1", "2")

    page1 = client.get(T, params={"q": "Seite", "page": 1, "page_size": 2}, headers=h)
    page2 = client.get(T, params={"q": "Seite", "page": 2, "page_size": 2}, headers=h)
    page3 = client.get(T, params={"q": "Seite", "page": 3, "page_size": 2}, headers=h)
    total = int(page1.headers["x-total-count"])
    seen = [t["number"] for p in (page1, page2, page3) for t in _ok(p)]
    assert len(seen) == min(total, 6)
    assert len(set(seen)) == len(seen)  # no overlap between pages
    assert seen == sorted(seen, reverse=True)  # newest number first across pages
    page4 = _ok(client.get(T, params={"q": "Seite", "page": 4, "page_size": 2}, headers=h))
    assert set(numbers) <= set(seen) | {t["number"] for t in page4}
    assert client.get(T, params={"page": 0}, headers=h).status_code == 422
    assert client.get(T, params={"page_size": 501}, headers=h).status_code == 422


def test_sla_backfill_starts_clocks_for_open_tickets_without_one(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Tickets that bypassed start_clock (older rows, imports) get a clock from the SLA job,
    started at the ticket's creation time; closed tickets are left alone."""
    from sqlalchemy import text

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.sla.service import backfill_clocks

    h = bearer(login(client, world, "rvadmin"))
    open_ticket = _ticket(client, h, f"Nachlauf offen {RUN}")
    done_ticket = _ticket(client, h, f"Nachlauf erledigt {RUN}")
    _ok(client.patch(f"{T}/{done_ticket['id']}", json={"status": "done"}, headers=h))

    async def run() -> int:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                await session.execute(
                    text("DELETE FROM sla_clock WHERE ticket_id IN (:a, :b)"),
                    {"a": open_ticket["id"], "b": done_ticket["id"]},
                )
            async with tenant_transaction(factory, world.tenant_a) as session:
                return await backfill_clocks(session, world.tenant_a)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) >= 1
    clock = _clock(client, h, open_ticket["id"])
    assert clock["state"] == "running"
    assert datetime.fromisoformat(clock["started_at"]) == datetime.fromisoformat(
        open_ticket["created_at"]
    )
    assert client.get(f"/api/v1/sla/tickets/{done_ticket['id']}/sla", headers=h).status_code == 404
