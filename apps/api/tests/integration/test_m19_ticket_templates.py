"""M19 ticket templates with checklists and required fields (25.09.2026): template CRUD,
ticket creation from a template copies checklist and extra field definitions, a required IBAN
extra field is validated, an open required checklist item blocks done/closed, and bulk status
change is limited for standard users but unlimited for tickets:approve/admin. Tenant separation
for templates and tickets."""

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
        a, _ = await services.provision_tenant(factory, slug=f"tt-{RUN}", name=f"Vorlagen {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"tt2-{RUN}", name=f"Vorlagen2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("m19tadmin", "tenant_admin", a),
            ("m19tcare", "caretaker", a),
            ("m19totherb", "tenant_admin", b),
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
    return response.json()


def test_template_crud_and_ticket_checklist_and_iban(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "m19tadmin"))
    care = bearer(login(client, world, "m19tcare"))

    tpl = _ok(
        client.post(
            "/api/v1/tickets/templates",
            json={
                "category": f"kaution-{RUN}",
                "title": "Kaution einrichten",
                "description": "Kautionsticket mit Pflicht-IBAN",
                "checklist": [
                    {"key": "vertrag", "label": "Vertrag geprüft", "required": True},
                    {"key": "info", "label": "Mieter informiert", "required": False},
                ],
                "extra_fields": [
                    {"key": "iban", "label": "IBAN", "type": "iban", "required": True},
                ],
                "default_priority": "normal",
            },
            headers=admin,
        ),
        201,
    )
    assert tpl["active"] is True
    assert len(tpl["checklist"]) == 2

    # A user without tickets:approve or tenant_settings:update may not manage templates.
    assert (
        client.post(
            "/api/v1/tickets/templates",
            json={"category": f"x-{RUN}", "title": "x"},
            headers=care,
        ).status_code
        == 403
    )

    got = _ok(client.get(f"/api/v1/tickets/templates/{tpl['id']}", headers=care))
    assert got["title"] == "Kaution einrichten"

    patched = _ok(
        client.patch(
            f"/api/v1/tickets/templates/{tpl['id']}",
            json={"active": False},
            headers=admin,
        )
    )
    assert patched["active"] is False
    _ok(
        client.patch(f"/api/v1/tickets/templates/{tpl['id']}", json={"active": True}, headers=admin)
    )

    listed = _ok(client.get("/api/v1/tickets/templates", headers=care))
    assert any(t["id"] == tpl["id"] for t in listed)

    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"template_id": tpl["id"], "public_description": "Kaution Musterstr. 1"},
            headers=care,
        ),
        201,
    )
    assert len(ticket["checklist"]) == 2
    assert ticket["checklist"][0]["required"] is True
    assert ticket["checklist"][0]["done"] is False

    # Missing required IBAN blocks closure even with checklist complete.
    _ok(
        client.patch(
            f"/api/v1/tickets/{ticket['id']}/checklist/vertrag", json={"done": True}, headers=care
        )
    )
    resp = client.patch(f"/api/v1/tickets/{ticket['id']}", json={"status": "done"}, headers=care)
    assert resp.status_code == 422

    # Invalid IBAN is rejected.
    bad = client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        json={"extra_fields": {"iban": "DE00INVALID"}},
        headers=care,
    )
    assert bad.status_code == 422

    _ok(
        client.patch(
            f"/api/v1/tickets/{ticket['id']}",
            json={"extra_fields": {"iban": "DE89370400440532013000"}},
            headers=care,
        )
    )

    # Checklist has an open required item again? No: only "vertrag" is required and it is done.
    done = _ok(
        client.patch(f"/api/v1/tickets/{ticket['id']}", json={"status": "done"}, headers=care)
    )
    assert done["status"] == "done"
    assert done["extra_fields"]["iban"] == "DE89370400440532013000"


def test_template_open_required_checklist_blocks_closure(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "m19tadmin"))
    care = bearer(login(client, world, "m19tcare"))
    tpl = _ok(
        client.post(
            "/api/v1/tickets/templates",
            json={
                "category": f"letting-{RUN}",
                "title": "Vermietung Checkliste",
                "checklist": [{"key": "besichtigung", "label": "Besichtigt", "required": True}],
            },
            headers=admin,
        ),
        201,
    )
    ticket = _ok(client.post("/api/v1/tickets", json={"template_id": tpl["id"]}, headers=care), 201)
    resp = client.patch(f"/api/v1/tickets/{ticket['id']}", json={"status": "done"}, headers=care)
    assert resp.status_code == 422
    assert "Checkliste unvollständig" in resp.json()["detail"]

    _ok(
        client.patch(
            f"/api/v1/tickets/{ticket['id']}/checklist/besichtigung",
            json={"done": True},
            headers=care,
        )
    )
    _ok(client.patch(f"/api/v1/tickets/{ticket['id']}", json={"status": "done"}, headers=care))


def test_bulk_status_limit_standard_vs_admin(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "m19tadmin"))
    care = bearer(login(client, world, "m19tcare"))

    def _make_tickets(n: int, headers: dict[str, str]) -> list[str]:
        ids = []
        for i in range(n):
            t = _ok(
                client.post("/api/v1/tickets", json={"title": f"Bulk {RUN} {i}"}, headers=headers),
                201,
            )
            ids.append(t["id"])
        return ids

    ids_standard = _make_tickets(11, care)
    resp = client.post(
        "/api/v1/tickets/bulk-status",
        json={"ticket_ids": ids_standard, "status": "in_progress"},
        headers=care,
    )
    assert resp.status_code == 422
    assert "Höchstens 10 Tickets gleichzeitig" in resp.json()["detail"]

    ids_admin = _make_tickets(11, admin)
    ok = _ok(
        client.post(
            "/api/v1/tickets/bulk-status",
            json={"ticket_ids": ids_admin, "status": "in_progress"},
            headers=admin,
        )
    )
    assert len(ok["changed"]) == 11
    assert ok["failed"] == []

    # Within limit, standard user succeeds, with a partial failure reported per ticket.
    ids_small = _make_tickets(3, care)
    resp2 = _ok(
        client.post(
            "/api/v1/tickets/bulk-status",
            json={
                "ticket_ids": [*ids_small, "00000000-0000-0000-0000-000000000000"],
                "status": "in_progress",
            },
            headers=care,
        )
    )
    assert len(resp2["changed"]) == 3
    assert len(resp2["failed"]) == 1


def test_tenant_separation_for_templates(client: TestClient, world: World) -> None:
    admin_a = bearer(login(client, world, "m19tadmin"))
    admin_b = bearer(login(client, world, "m19totherb"))
    tpl = _ok(
        client.post(
            "/api/v1/tickets/templates",
            json={"category": f"sep-{RUN}", "title": "Nur Mandant A"},
            headers=admin_a,
        ),
        201,
    )
    assert client.get(f"/api/v1/tickets/templates/{tpl['id']}", headers=admin_b).status_code == 404
    listed_b = _ok(client.get("/api/v1/tickets/templates", headers=admin_b))
    assert all(t["id"] != tpl["id"] for t in listed_b)
