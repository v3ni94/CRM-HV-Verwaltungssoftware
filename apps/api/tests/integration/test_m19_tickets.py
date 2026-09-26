"""M19: ticket with template routing, checklist and SLA; status flow; internal and external
comments; work order request, quote over budget refused, approval, appointment, execution,
invoice of the same provider linked, acceptance with rating (ticket to order to invoice)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"tk-{RUN}", name=f"Ticket {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("m19admin", "tenant_admin"),
            ("m19care", "caretaker"),
            ("m19tech", "technical_clerk"),
            ("m19read", "read_only_master_data"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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
    return response.json()


def test_ticket_to_order_to_invoice(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m19admin"))
    care = bearer(login(client, world, "m19care"))
    tech = bearer(login(client, world, "m19tech"))
    reader = bearer(login(client, world, "m19read"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "791", "name": "Tickethaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    team = _ok(
        client.post(
            "/api/v1/teams",
            json={"name": f"Technik {RUN}", "member_user_ids": [str(world.users["m19tech"])]},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/ticket-templates",
            json={
                "category": "Heizungsausfall",
                "title": "Heizung ausgefallen",
                "checklist": [
                    {"key": "mieter", "label": "Mieter kontaktiert", "required": False},
                    {
                        "key": "dienstleister",
                        "label": "Dienstleister beauftragt",
                        "required": False,
                    },
                ],
                "default_priority": "urgent",
                "default_team_id": team["id"],
                "default_assignee_user_id": str(world.users["m19tech"]),
                "sla_hours": 24,
            },
            headers=h,
        ),
        201,
    )

    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={
                "category": "Heizungsausfall",
                "property_id": prop["id"],
                "public_description": "Keine Wärme im 2. OG",
                "source": "phone",
            },
            headers=care,
        ),
        201,
    )
    assert ticket["priority"] == "urgent"
    assert ticket["assignee_user_id"] == str(world.users["m19tech"])
    assert len(ticket["checklist"]) == 2
    assert ticket["sla_due_at"] is not None
    assert ticket["sla_breached"] is False
    notes = _ok(client.get("/api/v1/workspace/notifications", headers=tech))
    assert any(n["entity_id"] == ticket["id"] for n in notes)
    assert client.post("/api/v1/tickets", json={"title": "x"}, headers=reader).status_code == 403

    assert (
        client.patch(
            f"/api/v1/tickets/{ticket['id']}", json={"status": "closed"}, headers=tech
        ).status_code
        == 409
    )
    _ok(
        client.patch(
            f"/api/v1/tickets/{ticket['id']}",
            json={"status": "in_progress", "checklist_done": [0]},
            headers=tech,
        )
    )
    _ok(
        client.post(
            f"/api/v1/tickets/{ticket['id']}/comments",
            json={"body": "Mieter informiert", "internal": False},
            headers=tech,
        ),
        201,
    )

    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Heizung {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    other = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Anders {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": prop["id"],
                "provider_contact_id": provider,
                "description": "Heizung instand setzen",
                "budget_limit": "1000.00",
            },
            headers=tech,
        ),
        201,
    )
    steps = f"/api/v1/work-orders/{order['id']}/steps"
    assert client.post(steps, json={"status": "done"}, headers=tech).status_code == 409
    _ok(client.post(steps, json={"status": "requested"}, headers=tech))
    _ok(client.post(steps, json={"status": "quoted", "quote_amount": "1200.00"}, headers=tech))
    over = client.post(steps, json={"status": "approved"}, headers=tech)
    assert over.status_code == 409  # quote above budget
    order2 = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": prop["id"],
                "provider_contact_id": provider,
                "description": "Heizung instand setzen, neues Angebot",
                "budget_limit": "1000.00",
            },
            headers=tech,
        ),
        201,
    )
    steps = f"/api/v1/work-orders/{order2['id']}/steps"
    _ok(client.post(steps, json={"status": "requested"}, headers=tech))
    _ok(client.post(steps, json={"status": "quoted", "quote_amount": "900.00"}, headers=tech))
    approved = _ok(client.post(steps, json={"status": "approved"}, headers=tech))
    assert approved["approved_by"] == str(world.users["m19tech"])
    assert client.post(steps, json={"status": "scheduled"}, headers=tech).status_code == 422
    _ok(
        client.post(
            steps,
            json={"status": "scheduled", "scheduled_at": "2026-10-01T08:00:00Z"},
            headers=tech,
        )
    )
    _ok(client.post(steps, json={"status": "in_progress"}, headers=tech))
    _ok(
        client.post(
            steps, json={"status": "done", "completion_report": "Pumpe getauscht"}, headers=tech
        )
    )

    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post("/api/v1/accounting/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            "/api/v1/accounting/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"/api/v1/accounting/ledgers/{ledger}/accounts", headers=h))
    }
    base = {
        "ledger_id": ledger,
        "number": "H-1",
        "invoice_date": "2026-10-02",
        "net": "900.00",
        "vat": "0.00",
        "gross": "900.00",
        "lines": [{"account_id": acc["041400"], "net": "900.00"}],
    }
    wrong = _ok(
        client.post(
            "/api/v1/accounting/invoices", json={**base, "provider_contact_id": other}, headers=h
        ),
        201,
    )
    assert (
        client.post(
            steps, json={"status": "invoiced", "invoice_id": wrong["id"]}, headers=tech
        ).status_code
        == 422
    )
    invoice = _ok(
        client.post(
            "/api/v1/accounting/invoices",
            json={**base, "number": "H-2", "provider_contact_id": provider},
            headers=h,
        ),
        201,
    )
    _ok(client.post(steps, json={"status": "invoiced", "invoice_id": invoice["id"]}, headers=tech))
    assert (
        _ok(client.get(f"/api/v1/accounting/invoices/{invoice['id']}", headers=h))["review_status"]
        == "open"
    )  # no payment from the order
    accepted = _ok(
        client.post(
            steps,
            json={"status": "accepted", "rating": 5, "rating_comment": "schnell"},
            headers=tech,
        )
    )
    assert accepted["invoice_id"] == invoice["id"]

    _ok(client.patch(f"/api/v1/tickets/{ticket['id']}", json={"status": "done"}, headers=tech))
    full = _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))
    assert full["resolved_at"] is not None
    assert [o["status"] for o in full["work_orders"]] == ["quoted", "accepted"] or sorted(
        o["status"] for o in full["work_orders"]
    ) == ["accepted", "quoted"]
    # Template routing assigns the default assignee through the service layer (review M14).
    assert [e["kind"] for e in full["events"]][:3] == ["created", "assigned", "status"]
    assigned = next(e for e in full["events"] if e["kind"] == "assigned")
    assert assigned["data"]["reason"] == "Vorlage"
    assert assigned["data"]["to"] == str(world.users["m19tech"])


def test_every_closing_status_triggers_mail_archiving(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operator rule 25.09.2026: done, closed and rejected archive the ticket's mails."""
    from mhvp.communication import services as comm_services

    calls: list[str] = []

    async def _fake(session: Any, settings: Any, tenant_id: Any, ticket_id: Any) -> None:
        calls.append(str(ticket_id))

    monkeypatch.setattr(comm_services, "enqueue_archive_for_ticket", _fake)
    h = bearer(login(client, world, "m19admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "792", "name": "Archivhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    ids = []
    for _ in range(3):
        ids.append(
            _ok(
                client.post(
                    "/api/v1/tickets",
                    json={
                        "category": "Sonstiges",
                        "title": "Archivtest",
                        "property_id": prop["id"],
                        "public_description": "Archivtest",
                        "source": "phone",
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )
    for ticket_id, status in zip(ids, ("done", "rejected", "done"), strict=True):
        _ok(client.patch(f"/api/v1/tickets/{ticket_id}", json={"status": status}, headers=h))
    _ok(client.patch(f"/api/v1/tickets/{ids[2]}", json={"status": "closed"}, headers=h))
    assert calls.count(ids[0]) == 1
    assert calls.count(ids[1]) == 1  # rejected archives as well
    assert calls.count(ids[2]) == 2  # done, then closed
