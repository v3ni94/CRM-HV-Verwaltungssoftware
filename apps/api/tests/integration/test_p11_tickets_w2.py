"""P11: Auftragsliste und Auftragsdetail (M19-01), Teams (M19-02), Ticketfelder (M19-03,
M19-04), archivierte Kommentare (M19-07). Mandantentrennung, Berechtigung, Validierung."""

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
        a, _ = await services.provision_tenant(factory, slug=f"p11-{RUN}", name=f"P11 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p11b-{RUN}", name=f"P11B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant, name, role in [
            (a, "p11admin", "tenant_admin"),
            (a, "p11read", "read_only"),
            (b, "p11adminb", "tenant_admin"),
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


def _setup_order(c: TestClient, h: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "771", "name": "P11 Objekt", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"P11 Handwerk {RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    ticket = _ok(
        c.post("/api/v1/tickets", json={"title": "Dach", "property_id": prop["id"]}, headers=h), 201
    )
    order = _ok(
        c.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": prop["id"],
                "provider_contact_id": provider,
                "description": "Dach prüfen",
            },
            headers=h,
        ),
        201,
    )
    return ticket, order


def test_work_order_list_and_detail(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p11admin"))
    hb = bearer(login(client, world, "p11adminb"))
    hr = bearer(login(client, world, "p11read"))
    ticket, order = _setup_order(client, h)
    _ok(
        client.post(
            f"/api/v1/work-orders/{order['id']}/steps", json={"status": "requested"}, headers=h
        )
    )

    listed = _ok(client.get("/api/v1/work-orders?status=requested", headers=h))
    row = next(o for o in listed if o["id"] == order["id"])
    assert row["ticket_number"] == ticket["number"]
    assert _ok(client.get(f"/api/v1/work-orders?ticket_id={ticket['id']}", headers=hr))
    assert client.get("/api/v1/work-orders?status=bogus", headers=h).status_code == 422

    detail = _ok(client.get(f"/api/v1/work-orders/{order['id']}", headers=h))
    assert [e["to_status"] for e in detail["events"]] == ["requested"]
    # Mandantentrennung: anderer Mandant sieht den Auftrag nicht.
    assert client.get(f"/api/v1/work-orders/{order['id']}", headers=hb).status_code == 404
    assert all(o["id"] != order["id"] for o in _ok(client.get("/api/v1/work-orders", headers=hb)))


def test_teams_crud_permissions_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p11admin"))
    hb = bearer(login(client, world, "p11adminb"))
    hr = bearer(login(client, world, "p11read"))
    team = _ok(client.post("/api/v1/teams", json={"name": f"Technik {RUN}"}, headers=h), 201)
    assert any(t["id"] == team["id"] for t in _ok(client.get("/api/v1/teams", headers=hr)))
    assert (
        client.patch(f"/api/v1/teams/{team['id']}", json={"name": "X"}, headers=hr).status_code
        == 403
    )
    assert client.delete(f"/api/v1/teams/{team['id']}", headers=hr).status_code == 403
    assert client.get(f"/api/v1/teams/{team['id']}", headers=hb).status_code == 404
    assert (
        client.patch(f"/api/v1/teams/{team['id']}", json={"name": ""}, headers=h).status_code == 422
    )
    member = str(world.users["p11admin"])
    patched = _ok(
        client.patch(
            f"/api/v1/teams/{team['id']}",
            json={"name": f"Technik neu {RUN}", "member_user_ids": [member, member]},
            headers=h,
        )
    )
    assert patched["member_user_ids"] == [member]
    other = _ok(client.post("/api/v1/teams", json={"name": f"Zweit {RUN}"}, headers=h), 201)
    assert (
        client.patch(
            f"/api/v1/teams/{other['id']}", json={"name": patched["name"]}, headers=h
        ).status_code
        == 409
    )
    used = _ok(client.post("/api/v1/tickets", json={"title": "mit Team"}, headers=h), 201)
    _ok(client.patch(f"/api/v1/tickets/{used['id']}", json={"team_id": team["id"]}, headers=h))
    assert client.delete(f"/api/v1/teams/{team['id']}", headers=h).status_code == 409
    assert client.delete(f"/api/v1/teams/{other['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/teams/{other['id']}", headers=h).status_code == 404


def test_ticket_fields_building_dates_visibility(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p11admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "772", "name": "P11 Gebäude", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    other_prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "773", "name": "P11 Fremd", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus A"}, headers=h
        ),
        201,
    )
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={
                "title": "Feld",
                "property_id": prop["id"],
                "building_id": building["id"],
                "start_date": "2026-10-05",
                "follow_up_date": "2026-10-20",
                "external_comments": "to_manager",
            },
            headers=h,
        ),
        201,
    )
    assert ticket["building_id"] == building["id"]
    assert ticket["follow_up_date"] == "2026-10-20"
    assert ticket["external_comments"] == "to_manager"
    assert ticket["external_attachments"] == "none"
    patched = _ok(
        client.patch(
            f"/api/v1/tickets/{ticket['id']}",
            json={"follow_up_date": None, "external_attachments": "initiator_only"},
            headers=h,
        )
    )
    assert patched["follow_up_date"] is None
    assert patched["external_attachments"] == "initiator_only"
    bad = client.patch(
        f"/api/v1/tickets/{ticket['id']}", json={"external_comments": "all"}, headers=h
    )
    assert bad.status_code == 422
    foreign = client.post(
        "/api/v1/tickets",
        json={"title": "x", "property_id": other_prop["id"], "building_id": building["id"]},
        headers=h,
    )
    assert foreign.status_code == 422


def test_comment_list_and_archive(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p11admin"))
    hb = bearer(login(client, world, "p11adminb"))
    hr = bearer(login(client, world, "p11read"))
    ticket = _ok(client.post("/api/v1/tickets", json={"title": "Kommentare"}, headers=h), 201)
    base = f"/api/v1/tickets/{ticket['id']}/comments"
    first = _ok(client.post(base, json={"body": "eins", "internal": True}, headers=h), 201)
    _ok(client.post(base, json={"body": "zwei", "internal": False}, headers=h), 201)
    assert [c["body"] for c in _ok(client.get(base, headers=hr))] == ["eins", "zwei"]
    assert client.delete(f"{base}/{first['id']}", headers=hr).status_code == 403
    assert client.delete(f"{base}/{first['id']}", headers=hb).status_code == 404
    assert client.delete(f"{base}/{first['id']}", headers=h).status_code == 204
    assert client.delete(f"{base}/{first['id']}", headers=h).status_code == 204
    assert [c["body"] for c in _ok(client.get(base, headers=h))] == ["zwei"]
    assert len(_ok(client.get(f"{base}?include_removed=true", headers=h))) == 2
    detail = _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))
    assert [c["body"] for c in detail["comments"]] == ["zwei"]
