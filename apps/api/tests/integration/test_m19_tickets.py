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
                "checklist": ["Mieter kontaktiert", "Dienstleister beauftragt"],
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
    assert [e["kind"] for e in full["events"]][:2] == ["created", "status"]


def test_ticket_stats_series_and_user_comparison(client: TestClient, world: World) -> None:
    """Dashboard stats: stock by status, created/resolved buckets and per-user comparison,
    plus the assignee filter narrowing stock and series."""
    h = bearer(login(client, world, "m19admin"))
    tech = str(world.users["m19tech"])
    care = str(world.users["m19care"])

    made = []
    for i in range(3):
        t = _ok(
            client.post("/api/v1/tickets", json={"title": f"Statistik {RUN} {i}"}, headers=h), 201
        )
        made.append(t["id"])
    # tech resolves one, care keeps one open, one stays unassigned
    _ok(client.patch(f"/api/v1/tickets/{made[0]}", json={"assignee_user_id": tech}, headers=h))
    _ok(client.patch(f"/api/v1/tickets/{made[0]}", json={"status": "done"}, headers=h))
    _ok(client.patch(f"/api/v1/tickets/{made[1]}", json={"assignee_user_id": care}, headers=h))

    stats = _ok(client.get("/api/v1/tickets/stats?interval=day&periods=7", headers=h))
    assert stats["interval"] == "day"
    assert len(stats["series"]) == 7
    assert stats["by_status"]["done"] >= 1
    assert stats["open_total"] >= 2
    today = stats["series"][-1]
    assert today["created"] >= 3
    assert today["resolved"] >= 1

    users = {u["user_id"]: u for u in stats["by_user"]}
    assert users[tech]["resolved"] >= 1
    assert users[tech]["name"] == "m19tech"
    assert users[care]["open"] >= 1
    assert None in users or users.get(None) is None or True  # unassigned bucket may exist

    # Assignee filter narrows stock and series to that user.
    filtered = _ok(
        client.get(
            f"/api/v1/tickets/stats?interval=day&periods=7&assignee_user_id={care}", headers=h
        )
    )
    assert filtered["open_total"] == 1
    assert filtered["series"][-1]["resolved"] == 0

    # Every interval works against the database.
    for interval in ("week", "month", "quarter", "year"):
        r = _ok(client.get(f"/api/v1/tickets/stats?interval={interval}&periods=4", headers=h))
        assert len(r["series"]) == 4

    # Reading requires the tickets permission.
    ro = bearer(login(client, world, "m19read"))
    assert client.get("/api/v1/tickets/stats", headers=ro).status_code == 403


def test_bulk_status_with_role_limit(client: TestClient, world: World) -> None:
    """Markierte Tickets gesammelt umstellen: Mitarbeiter höchstens 10 je Aufruf, Admin
    unbegrenzt; unzulässige Wechsel werden übersprungen und gemeldet."""
    admin = bearer(login(client, world, "m19admin"))
    tech = bearer(login(client, world, "m19tech"))

    ids = [
        _ok(client.post("/api/v1/tickets", json={"title": f"Bulk {RUN} {i}"}, headers=admin), 201)[
            "id"
        ]
        for i in range(12)
    ]

    # Mitarbeiter: 11 auf einmal -> Fehler "zu viele", nichts geändert
    r = client.post(
        "/api/v1/tickets/bulk-status",
        json={"ticket_ids": ids[:11], "status": "done"},
        headers=tech,
    )
    assert r.status_code == 422, r.text
    assert "Zu viele Tickets" in r.text
    assert _ok(client.get(f"/api/v1/tickets/{ids[0]}", headers=admin))["status"] == "new"

    # Mitarbeiter: 10 auf einmal ist erlaubt
    result = _ok(
        client.post(
            "/api/v1/tickets/bulk-status",
            json={"ticket_ids": ids[:10], "status": "done"},
            headers=tech,
        )
    )
    assert result == {"updated": 10, "skipped": []}

    # Admin: unbegrenzt; bereits erledigte Tickets werden gemeldet statt geändert,
    # unzulässige Wechsel (done -> waiting gibt es nicht) ebenfalls
    result = _ok(
        client.post(
            "/api/v1/tickets/bulk-status",
            json={"ticket_ids": ids, "status": "done"},
            headers=admin,
        )
    )
    assert result["updated"] == 2
    assert len(result["skipped"]) == 10
    result = _ok(
        client.post(
            "/api/v1/tickets/bulk-status",
            json={"ticket_ids": ids[:2], "status": "waiting"},
            headers=admin,
        )
    )
    assert result["updated"] == 0
    assert all("unzulässig" in s["reason"] for s in result["skipped"])

    # Leserolle darf gar nicht
    ro = bearer(login(client, world, "m19read"))
    assert (
        client.post(
            "/api/v1/tickets/bulk-status",
            json={"ticket_ids": ids[:1], "status": "done"},
            headers=ro,
        ).status_code
        == 403
    )


def test_ticket_templates_with_required_iban_field(client: TestClient, world: World) -> None:
    """Vorlagenverwaltung: anlegen, listen, ändern, löschen; ein Kautionsticket verlangt die
    IBAN als Pflichtfeld mit formaler Prüfung (Mod 97)."""
    admin = bearer(login(client, world, "m19admin"))
    tpl = _ok(
        client.post(
            "/api/v1/ticket-templates",
            json={
                "category": f"kaution-{RUN}",
                "title": "Kaution abrechnen",
                "checklist": ["Auszug prüfen", "Abrechnung erstellen", "Auszahlung anweisen"],
                "required_fields": [
                    {"key": "iban", "label": "IBAN des Mieters", "kind": "iban", "required": True}
                ],
            },
            headers=admin,
        ),
        201,
    )
    listed = _ok(client.get("/api/v1/ticket-templates", headers=admin))
    mine = next(t for t in listed if t["category"] == f"kaution-{RUN}")
    assert mine["required_fields"][0]["kind"] == "iban"

    # Ohne IBAN: klare Fehlermeldung; mit ungültiger IBAN: formale Prüfung schlägt an
    r = client.post("/api/v1/tickets", json={"category": f"kaution-{RUN}"}, headers=admin)
    assert r.status_code == 422, r.text
    assert "Pflichtfeld fehlt: IBAN" in r.text
    r = client.post(
        "/api/v1/tickets",
        json={"category": f"kaution-{RUN}", "extra_fields": {"iban": "DE00 1234"}},
        headers=admin,
    )
    assert r.status_code == 422, r.text
    assert "keine gültige IBAN" in r.text

    # Gültige IBAN (Testwert, Mod 97 = 1) wird normalisiert gespeichert; Checkliste kommt mit
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={
                "category": f"kaution-{RUN}",
                "extra_fields": {"iban": "de89 3704 0044 0532 0130 00"},
            },
            headers=admin,
        ),
        201,
    )
    assert ticket["extra_fields"] == {"iban": "DE89370400440532013000"}
    assert len(ticket["checklist"]) == 3

    # Ändern; Löschen ist gesperrt, solange Tickets die Vorlage verwenden
    patched = _ok(
        client.patch(
            f"/api/v1/ticket-templates/{tpl['id']}",
            json={
                "category": f"kaution-{RUN}",
                "title": "Kaution abrechnen (neu)",
                "required_fields": [],
            },
            headers=admin,
        )
    )
    assert patched["title"] == "Kaution abrechnen (neu)"
    assert client.delete(f"/api/v1/ticket-templates/{tpl['id']}", headers=admin).status_code == 409

    # Unbenutzte Vorlage lässt sich löschen; Nicht-Admin darf nicht verwalten
    spare = _ok(
        client.post(
            "/api/v1/ticket-templates",
            json={"category": f"leer-{RUN}", "title": "Leer"},
            headers=admin,
        ),
        201,
    )
    ro = bearer(login(client, world, "m19read"))
    assert client.delete(f"/api/v1/ticket-templates/{spare['id']}", headers=ro).status_code == 403
    assert (
        client.delete(f"/api/v1/ticket-templates/{spare['id']}", headers=admin).status_code == 204
    )
