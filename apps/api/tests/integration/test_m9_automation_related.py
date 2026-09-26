"""M9 / A81: rule conditions on related master data (property, contact) beyond the ticket.

The context of an event is enriched once per event with the groups the rules of the event
type read; a rule matches only when the linked property field fits, unknown related fields
are refused at save time, and a tenant never sees the properties of another tenant.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.automation.tasks import process_events_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/automation"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"autr-{RUN}", name=f"AutR {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"autrb-{RUN}", name=f"AutRb {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [("aradmin", "tenant_admin", a), ("arb", "tenant_admin", b)]:
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


def _later(seconds: int = 30) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _property(client: TestClient, h: dict[str, str], number: str, kind: str, city: str) -> Any:
    return _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Objekt {number}",
                "management_type": kind,
                "street": "Rheinpromenade",
                "house_number": number,
                "postal_code": "40789",
                "city": city,
            },
            headers=h,
        ),
        201,
    )


def _ticket(client: TestClient, h: dict[str, str], title: str, **extra: Any) -> Any:
    return _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": title, "category": "Wasserschaden", **extra},
            headers=h,
        ),
        201,
    )


def test_conditions_on_related_property_and_contact(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    admin = bearer(login(client, world, "aradmin"))
    other = bearer(login(client, world, "arb"))
    settings = _settings(database, redis_url)
    hoa = _property(client, admin, "701", "hoa", "Monheim am Rhein")
    rental = _property(client, admin, "702", "rental", "Langenfeld")
    # Tenant B has a HOA property with the same number as A's; it must never match A's rule.
    _property(client, other, "701", "hoa", "Monheim am Rhein")
    owner = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Otto",
                "last_name": f"Eigen{RUN}",
                "roles": ["eigentuemer"],
            },
            headers=admin,
        ),
        201,
    )
    meta = _ok(client.get(f"{A}/meta", headers=admin))
    assert "management_type" in meta["related_fields"]["property"]
    assert "roles" in meta["related_fields"]["contact"]
    assert set(meta["related_fields"]) == {"property", "unit", "contact", "contract"}

    # Unknown related fields (and anything money related) are refused at save time.
    bad = {
        "name": f"Miete {RUN}",
        "trigger_event_type": "ticket.created",
        "conditions": {"field": "contract.rent", "op": "gt", "value": 0},
        "actions": [{"type": "notify", "user_ids": [str(world.users["aradmin"])], "title": "x"}],
    }
    assert client.post(f"{A}/rules", json=bad, headers=admin).status_code == 422

    body = {
        "name": f"WEG Objekt {RUN}",
        "trigger_event_type": "ticket.created",
        "conditions": {
            "op": "and",
            "conditions": [
                {"field": "property.management_type", "op": "eq", "value": "hoa"},
                {"field": "property.number", "op": "eq", "value": "701"},
                {"field": "contact.roles", "op": "contains", "value": "eigentuemer"},
            ],
        },
        "actions": [
            {
                "type": "notify",
                "user_ids": [str(world.users["aradmin"])],
                "title": "WEG {property.number} in {property.city}: {entity.title}",
            }
        ],
    }
    rule = _ok(client.post(f"{A}/rules", json=body, headers=admin), 201)

    # Dry run resolves the related data from the sample's ids.
    dry = _ok(
        client.post(
            f"{A}/rules/{rule['id']}/test",
            json={
                "type": "ticket.created",
                "entity": {"title": "Probe", "property_id": hoa["id"], "contact_id": owner["id"]},
            },
            headers=admin,
        )
    )
    assert dry["matched"] is True, dry
    assert dry["context"]["property"]["management_type"] == "hoa"
    assert dry["context"]["contact"]["roles"] == ["eigentuemer"]
    assert dry["actions"][0]["title"] == "WEG 701 in Monheim am Rhein: Probe"
    miss = _ok(
        client.post(
            f"{A}/rules/{rule['id']}/test",
            json={
                "type": "ticket.created",
                "entity": {"title": "Probe", "property_id": rental["id"]},
            },
            headers=admin,
        )
    )
    assert miss["matched"] is False
    assert miss["context"]["property"]["management_type"] == "rental"
    assert miss["context"]["contact"] == {}

    # Real runs: only the ticket on the HOA property with the owner contact triggers the rule.
    # First pass only positions the watermark (older events are history).
    asyncio.run(process_events_once(settings))
    _ok(client.post(f"{A}/rules/{rule['id']}/activate", json={"active": True}, headers=admin))
    hit = _ticket(client, admin, "Rohrbruch WEG", property_id=hoa["id"], contact_id=owner["id"])
    _ticket(client, admin, "Rohrbruch Miete", property_id=rental["id"], contact_id=owner["id"])
    _ticket(client, admin, "Rohrbruch ohne Objekt", contact_id=owner["id"])
    _ticket(client, admin, "Rohrbruch ohne Kontakt", property_id=hoa["id"])
    result = asyncio.run(process_events_once(settings, now=_later(60)))
    assert result["failed"] == 0
    runs = _ok(client.get(f"{A}/runs", params={"rule_id": rule["id"]}, headers=admin))["items"]
    assert len(runs) == 1, runs
    assert runs[0]["status"] == "executed"
    assert runs[0]["actions"][0]["title"] == "WEG 701 in Monheim am Rhein: Rohrbruch WEG"
    assert runs[0]["event_id"] is not None
    notes = _ok(
        client.get("/api/v1/workspace/notifications", params={"unread": True}, headers=admin)
    )
    titles = [n["title"] for n in notes if n["kind"] == "automation"]
    assert "WEG 701 in Monheim am Rhein: Rohrbruch WEG" in titles
    assert not any("Miete" in t or "ohne" in t for t in titles)
    assert hit["id"]

    # Tenant separation: the same rule in tenant B only sees B's property 701.
    b_rule = _ok(
        client.post(
            f"{A}/rules",
            json=body
            | {
                "name": f"B {RUN}",
                "conditions": {"field": "property.number", "op": "eq", "value": "701"},
                "actions": [
                    {
                        "type": "notify",
                        "user_ids": [str(world.users["arb"])],
                        "title": "B {property.city}",
                    }
                ],
            },
            headers=other,
        ),
        201,
    )
    foreign = _ok(
        client.post(
            f"{A}/rules/{b_rule['id']}/test",
            json={"type": "ticket.created", "entity": {"title": "x", "property_id": hoa["id"]}},
            headers=other,
        )
    )
    assert foreign["matched"] is False
    assert foreign["context"]["property"] == {}
    assert _ok(client.get(f"{A}/runs", headers=other))["total"] == 0
    for rid, h in ((rule["id"], admin), (b_rule["id"], other)):
        assert client.delete(f"{A}/rules/{rid}", headers=h).status_code == 204
