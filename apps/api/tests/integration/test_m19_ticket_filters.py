"""M19 ticket list filters (operator 25.09.2026): assignee (primary and secondary), property,
unit, contact role (owner/tenant), q across number/title/description/contact name/property
address, date range, and tenant separation. Additive to GET /tickets (docs/plans/M19.md)."""

import asyncio
from collections.abc import Iterator
from typing import Any, cast

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
        a, _ = await services.provision_tenant(factory, slug=f"tkf-{RUN}", name=f"Filter {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"tkfb-{RUN}", name=f"FilterB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant, names in (
            (a, ["m19fadmin", "m19ftech", "m19fother"]),
            (b, ["m19fadminb"]),
        ):
            for name in names:
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(
    c: TestClient, h: dict[str, str], number: str, street: str, city: str
) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"Objekt {number}",
        "management_type": "rental",
        "street": street,
        "house_number": "7",
        "postal_code": "40789",
        "city": city,
    }
    return cast(dict[str, Any], _ok(c.post("/api/v1/properties", json=body, headers=h), 201))


def _unit(c: TestClient, h: dict[str, str], prop_id: str, number: str) -> str:
    building = _ok(
        c.post(f"/api/v1/properties/{prop_id}/buildings", json={"name": "Haus"}, headers=h), 201
    )
    unit = _ok(
        c.post(
            f"/api/v1/properties/{prop_id}/units",
            json={
                "building_id": building["id"],
                "number": number,
                "label": f"WE {number}",
                "unit_type": "apartment",
            },
            headers=h,
        ),
        201,
    )
    return str(unit["id"])


def _contact_and_party(c: TestClient, h: dict[str, str], first: str, last: str) -> tuple[str, str]:
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": first, "last_name": last},
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
        201,
    )
    return str(contact["id"]), str(party["id"])


def _ticket(c: TestClient, h: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"title": "Testfall"} | overrides
    return cast(dict[str, Any], _ok(c.post("/api/v1/tickets", json=body, headers=h), 201))


def test_filter_by_assignee_primary_and_secondary(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m19fadmin"))
    tech = world.users["m19ftech"]
    other = world.users["m19fother"]
    primary = _ticket(client, h, title="Primär zugewiesen")
    _ok(
        client.patch(
            f"/api/v1/tickets/{primary['id']}", json={"assignee_user_id": str(tech)}, headers=h
        )
    )
    secondary = _ticket(client, h, title="Sekundär zugewiesen")
    _ok(
        client.post(
            f"/api/v1/tickets/{secondary['id']}/assignees",
            json={"user_id": str(tech), "reason": "manuell"},
            headers=h,
        ),
        201,
    )
    unrelated = _ticket(client, h, title="Ohne Bezug")
    _ok(
        client.patch(
            f"/api/v1/tickets/{unrelated['id']}", json={"assignee_user_id": str(other)}, headers=h
        )
    )

    result = _ok(client.get("/api/v1/tickets", params={"assignee_user_id": str(tech)}, headers=h))
    ids = {t["id"] for t in result}
    assert primary["id"] in ids
    assert secondary["id"] in ids
    assert unrelated["id"] not in ids


def test_filter_by_property_and_unit(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m19fadmin"))
    prop1 = _property(client, h, "601", "Beispielweg", "Musterstadt")
    prop2 = _property(client, h, "602", "Anderweg", "Musterstadt")
    unit1 = _unit(client, h, prop1["id"], "01")
    unit2 = _unit(client, h, prop1["id"], "02")
    t1 = _ticket(client, h, title="Objekt 1 Einheit 1", property_id=prop1["id"], unit_id=unit1)
    t2 = _ticket(client, h, title="Objekt 1 Einheit 2", property_id=prop1["id"], unit_id=unit2)
    t3 = _ticket(client, h, title="Objekt 2", property_id=prop2["id"])

    by_property = _ok(client.get("/api/v1/tickets", params={"property_id": prop1["id"]}, headers=h))
    ids = {t["id"] for t in by_property}
    assert {t1["id"], t2["id"]} <= ids
    assert t3["id"] not in ids

    by_unit = _ok(client.get("/api/v1/tickets", params={"unit_id": unit1}, headers=h))
    ids = {t["id"] for t in by_unit}
    assert t1["id"] in ids
    assert t2["id"] not in ids


def test_filter_by_contact_role_owner_and_tenant(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m19fadmin"))
    prop = _property(client, h, "603", "Rollenweg", "Musterstadt")
    unit = _unit(client, h, prop["id"], "01")
    owner_contact, owner_party = _contact_and_party(client, h, "Erika", f"Eigentum{RUN}")
    tenant_contact, tenant_party = _contact_and_party(client, h, "Max", f"Miete{RUN}")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner_party, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant_party,
                "start_date": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )

    owner_ticket = _ticket(
        client, h, title="Vom Eigentümer", unit_id=unit, contact_id=owner_contact
    )
    tenant_ticket = _ticket(client, h, title="Vom Mieter", unit_id=unit, contact_id=tenant_contact)

    by_owner = _ok(
        client.get("/api/v1/tickets", params={"contact_role": "owner", "unit_id": unit}, headers=h)
    )
    owner_ids = {t["id"] for t in by_owner}
    assert owner_ticket["id"] in owner_ids
    assert tenant_ticket["id"] not in owner_ids

    by_tenant = _ok(
        client.get("/api/v1/tickets", params={"contact_role": "tenant", "unit_id": unit}, headers=h)
    )
    tenant_ids = {t["id"] for t in by_tenant}
    assert tenant_ticket["id"] in tenant_ids
    assert owner_ticket["id"] not in tenant_ids

    invalid = client.get("/api/v1/tickets", params={"contact_role": "invalid"}, headers=h)
    assert invalid.status_code == 422


def test_q_matches_number_and_contact_name(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m19fadmin"))
    contact, _party = _contact_and_party(client, h, f"Suchvorname{RUN}", "Suchnachname")
    ticket = _ticket(client, h, title="Beliebiger Titel", contact_id=contact)

    by_number = _ok(client.get("/api/v1/tickets", params={"q": str(ticket["number"])}, headers=h))
    assert any(t["id"] == ticket["id"] for t in by_number)

    by_contact_name = _ok(
        client.get("/api/v1/tickets", params={"q": f"Suchvorname{RUN}"}, headers=h)
    )
    assert any(t["id"] == ticket["id"] for t in by_contact_name)


def test_created_date_range_and_multi_status(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m19fadmin"))
    ticket = _ticket(client, h, title="Zeitraumticket")

    future_only = _ok(
        client.get("/api/v1/tickets", params={"created_from": "2099-01-01T00:00:00Z"}, headers=h)
    )
    assert not any(t["id"] == ticket["id"] for t in future_only)

    since_epoch = _ok(
        client.get("/api/v1/tickets", params={"created_from": "2020-01-01T00:00:00Z"}, headers=h)
    )
    assert any(t["id"] == ticket["id"] for t in since_epoch)

    multi_status = _ok(
        client.get("/api/v1/tickets", params={"status": "new,in_progress"}, headers=h)
    )
    assert any(t["id"] == ticket["id"] for t in multi_status)


def test_tenant_separation_on_filters(client: TestClient, world: World) -> None:
    h_a = bearer(login(client, world, "m19fadmin"))
    h_b = bearer(login(client, world, "m19fadminb"))
    tech = world.users["m19ftech"]
    ticket_a = _ticket(client, h_a, title="Mandant A Ticket")
    _ok(
        client.patch(
            f"/api/v1/tickets/{ticket_a['id']}", json={"assignee_user_id": str(tech)}, headers=h_a
        )
    )
    result_b = _ok(
        client.get("/api/v1/tickets", params={"assignee_user_id": str(tech)}, headers=h_b)
    )
    assert not any(t["id"] == ticket_a["id"] for t in result_b)


def test_mine_includes_additional_assignees(client: TestClient, world: World) -> None:
    """Review N8: ``mine`` uses the same rule as ``assignee_user_id`` (primary or
    additional assignee)."""
    h = bearer(login(client, world, "m19fadmin"))
    h_tech = bearer(login(client, world, "m19ftech"))
    primary = _ok(
        client.post("/api/v1/tickets", json={"title": f"Mine primär {RUN}"}, headers=h), 201
    )
    secondary = _ok(
        client.post("/api/v1/tickets", json={"title": f"Mine zusätzlich {RUN}"}, headers=h), 201
    )
    foreign = _ok(
        client.post("/api/v1/tickets", json={"title": f"Mine fremd {RUN}"}, headers=h), 201
    )
    tech = str(world.users["m19ftech"])
    _ok(
        client.patch(f"/api/v1/tickets/{primary['id']}", json={"assignee_user_id": tech}, headers=h)
    )
    _ok(
        client.post(
            f"/api/v1/tickets/{secondary['id']}/assignees",
            json={"user_id": tech, "reason": "Kompetenz Heizung"},
            headers=h,
        ),
        201,
    )
    ids = {
        t["id"] for t in _ok(client.get("/api/v1/tickets", params={"mine": True}, headers=h_tech))
    }
    assert {primary["id"], secondary["id"]} <= ids
    assert foreign["id"] not in ids
