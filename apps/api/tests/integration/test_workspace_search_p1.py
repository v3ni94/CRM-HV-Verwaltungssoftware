"""P1 AP6: global search over tickets, buildings and postings (Ergänzung 5, rule 2, and 7.4).

Every hit type is guarded by its own read permission; a second tenant never sees the hits.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"srch-{RUN}", name=f"Suche {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"srch2-{RUN}", name=f"Suche2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("srchadmin", a, "tenant_admin"),
            ("srchcaretaker", a, "caretaker"),
            ("srchclerk", a, "clerk_no_accounting"),
            ("srchother", b, "tenant_admin"),
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


def _types(client: TestClient, h: dict[str, str], q: str) -> dict[str, list[dict[str, Any]]]:
    hits = _ok(client.get(f"{W}/search", params={"q": q, "limit": 10}, headers=h))
    out: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        out.setdefault(hit["entity_type"], []).append(hit)
    return out


def test_search_tickets_buildings_postings_with_permission_per_type(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "srchadmin"))
    marker = f"Suchwort{RUN}"
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "601", "name": f"Suchhaus {RUN}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/buildings",
            json={"name": f"Nebengebäude {marker}", "street": "Suchgasse"},
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": f"Heizung defekt {marker}", "priority": "normal"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )
    accounts = _ok(client.get(f"{A}/ledgers/{ledger['id']}/accounts", headers=h))
    first, second = accounts[0]["id"], accounts[1]["id"]
    entry = _ok(
        client.post(
            f"{A}/ledgers/{ledger['id']}/entries",
            json={
                "kind": "custom",
                "booking_date": "2026-03-01",
                "text": f"Rechnung Dachdecker {marker}",
                "lines": [
                    {"account_id": first, "debit": "10.00", "credit": "0"},
                    {"account_id": second, "debit": "0", "credit": "10.00"},
                ],
            },
            headers=h,
        ),
        201,
    )

    # Admin: every type, with the parent id for the jump path (building -> property,
    # posting -> ledger journal).
    found = _types(client, h, marker)
    assert {x["id"] for x in found["building"]} == {building["id"]}
    assert found["building"][0]["parent_id"] == prop["id"]
    assert {x["id"] for x in found["ticket"]} == {ticket["id"]}
    assert found["ticket"][0]["title"].startswith(f"#{ticket['number']} ")
    assert {x["id"] for x in found["posting"]} == {entry["id"]}
    assert found["posting"][0]["parent_id"] == ledger["id"]
    # Ticket number and posting text are searchable too.
    by_number = _types(client, h, f"#{ticket['number']}")  # search needs two characters
    assert ticket["id"] in {x["id"] for x in by_number.get("ticket", [])}

    # Caretaker: properties and tickets readable, no accounting.
    caretaker = bearer(login(client, world, "srchcaretaker"))
    found = _types(client, caretaker, marker)
    assert set(found) == {"building", "ticket"}
    # Clerk without accounting: tickets yes, postings no.
    clerk = bearer(login(client, world, "srchclerk"))
    found = _types(client, clerk, marker)
    assert "ticket" in found
    assert "posting" not in found

    # Tenant separation: the other tenant sees nothing.
    other = bearer(login(client, world, "srchother"))
    assert _types(client, other, marker) == {}
