"""M9 / A38: rule engine stage 1.

A rule on ``ticket.created`` with a category condition sets priority and team, notifies a
role, creates a follow-up ticket from a template; runs are idempotent per event and rule,
events written by rule actions never trigger a rule again (depth 1), inactive rules do not
run, maintenance needs ``tenant_settings:update``, tenants are separated.
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
        a, _ = await services.provision_tenant(factory, slug=f"auto-{RUN}", name=f"Auto {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"auto2-{RUN}", name=f"Auto2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("autoadmin", "tenant_admin", a),
            ("autocare", "caretaker", a),
            ("autob", "tenant_admin", b),
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


def _later() -> datetime:
    # The job leaves events younger than PROCESS_LAG for the next run; pretend time passed.
    return datetime.now(UTC) + timedelta(seconds=30)


def test_rule_engine_stage_one(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "autoadmin"))
    care = bearer(login(client, world, "autocare"))
    other = bearer(login(client, world, "autob"))

    # First run only positions the watermark; nothing older is a trigger.
    first = asyncio.run(process_events_once(settings))
    assert first["tenants"] >= 2

    team = _ok(
        client.post("/api/v1/teams", json={"name": f"Objektbetreuung {RUN}"}, headers=admin), 201
    )
    template = _ok(
        client.post(
            "/api/v1/tickets/templates",
            json={"category": "Wasserschaden", "title": "Wasserschaden bearbeiten"},
            headers=admin,
        ),
        201,
    )

    # Rights: the caretaker reads (tickets:read) but cannot maintain rules.
    rule_body = {
        "name": "Wasserschaden eskalieren",
        "trigger_event_type": "ticket.created",
        "conditions": {"field": "entity.category", "op": "eq", "value": "Wasserschaden"},
        "actions": [
            {"type": "set_ticket_field", "field": "priority", "value": "high"},
            {"type": "set_ticket_field", "field": "team_id", "value": team["id"]},
            {
                "type": "notify",
                "role_codes": ["caretaker"],
                "title": "Wasserschaden: Ticket {payload.number}",
                "body": "{entity.title}",
            },
            {
                "type": "create_ticket",
                "template_id": template["id"],
                "title": "Folgeauftrag zu {entity.title}",
                "fields": {
                    "category": "Wasserschaden",
                    "property_id": {"$field": "entity.property_id"},
                },
            },
        ],
    }
    assert client.post(f"{A}/rules", json=rule_body, headers=care).status_code == 403
    assert client.post(f"{A}/rules", json=rule_body, headers=other).status_code == 201
    rule = _ok(client.post(f"{A}/rules", json=rule_body, headers=admin), 201)
    assert rule["active"] is False
    assert client.post(f"{A}/rules", json=rule_body, headers=admin).status_code == 409
    inactive = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": "Nie aktiv",
                "trigger_event_type": "ticket.created",
                "actions": [
                    {"type": "notify", "user_ids": [str(world.users["autocare"])], "title": "x"}
                ],
            },
            headers=admin,
        ),
        201,
    )

    # Money actions are refused at the schema (rule 0.1.6, 0.1.7).
    bad = rule_body | {"name": "Buchen", "actions": [{"type": "post_journal", "amount": "1,00"}]}
    assert client.post(f"{A}/rules", json=bad, headers=admin).status_code == 422
    bad = rule_body | {
        "name": "Status",
        "actions": [{"type": "set_ticket_field", "field": "status", "value": "closed"}],
    }
    assert client.post(f"{A}/rules", json=bad, headers=admin).status_code == 422
    bad = rule_body | {"name": "Regex", "conditions": {"field": "x", "op": "regex", "value": ".*"}}
    assert client.post(f"{A}/rules", json=bad, headers=admin).status_code == 422

    listed = _ok(client.get(f"{A}/rules", headers=care))
    assert {r["id"] for r in listed} == {rule["id"], inactive["id"]}
    assert client.get(f"{A}/meta", headers=care).status_code == 200

    # Test run: matched with previews, nothing written.
    tickets_before = _ok(client.get("/api/v1/tickets", headers=admin))
    dry = _ok(
        client.post(
            f"{A}/rules/{rule['id']}/test",
            json={
                "type": "ticket.created",
                "entity": {"category": "Wasserschaden", "title": "Probe"},
                "payload": {"number": 7},
            },
            headers=admin,
        )
    )
    assert dry["matched"] is True
    assert dry["status"] == "dry_run"
    assert [a["type"] for a in dry["actions"]] == [
        "set_ticket_field",
        "set_ticket_field",
        "notify",
        "create_ticket",
    ]
    assert dry["actions"][2]["title"] == "Wasserschaden: Ticket 7"
    assert str(world.users["autocare"]) in dry["actions"][2]["user_ids"]
    assert dry["actions"][3]["title"] == "Folgeauftrag zu Probe"
    miss = _ok(
        client.post(
            f"{A}/rules/{rule['id']}/test",
            json={"type": "ticket.created", "entity": {"category": "Sturm"}},
            headers=admin,
        )
    )
    assert miss["matched"] is False
    assert miss["actions"] == []
    assert (
        client.post(
            f"{A}/rules/{rule['id']}/test", json={"type": "ticket.created"}, headers=care
        ).status_code
        == 403
    )
    assert _ok(client.get("/api/v1/tickets", headers=admin)) == tickets_before
    assert _ok(client.get(f"{A}/runs", headers=care))["total"] == 0

    # Activate and create the triggering tickets.
    assert (
        _ok(client.post(f"{A}/rules/{rule['id']}/activate", json={"active": True}, headers=admin))[
            "active"
        ]
        is True
    )
    assert (
        client.post(
            f"{A}/rules/{rule['id']}/activate", json={"active": False}, headers=care
        ).status_code
        == 403
    )
    wasser = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Rohrbruch Keller", "category": "Wasserschaden"},
            headers=admin,
        ),
        201,
    )
    sturm = _ok(
        client.post(
            "/api/v1/tickets", json={"title": "Dachziegel", "category": "Sturm"}, headers=admin
        ),
        201,
    )
    assert wasser["priority"] == "normal"

    result = asyncio.run(process_events_once(settings, now=_later()))
    assert result["failed"] == 0
    assert result["runs"] >= 1

    changed = _ok(client.get(f"/api/v1/tickets/{wasser['id']}", headers=admin))
    assert changed["priority"] == "high"
    assert changed["team_id"] == team["id"]
    untouched = _ok(client.get(f"/api/v1/tickets/{sturm['id']}", headers=admin))
    assert untouched["priority"] == "normal"
    assert untouched["team_id"] is None

    notes = _ok(
        client.get("/api/v1/workspace/notifications", params={"unread": True}, headers=care)
    )
    mine = [n for n in notes if n["kind"] == "automation" and n["entity_id"] == wasser["id"]]
    assert len(mine) == 1
    assert mine[0]["title"] == f"Wasserschaden: Ticket {wasser['number']}"
    assert mine[0]["body"] == "Rohrbruch Keller"

    def _follow_ups() -> list[dict[str, Any]]:
        rows = _ok(client.get("/api/v1/tickets", headers=admin))
        items = rows["items"] if isinstance(rows, dict) else rows
        return [t for t in items if t["title"] == "Folgeauftrag zu Rohrbruch Keller"]

    follow = _follow_ups()
    assert len(follow) == 1
    assert follow[0]["category"] == "Wasserschaden"
    assert follow[0]["template_id"] == template["id"]

    runs = _ok(client.get(f"{A}/runs", headers=care))
    assert runs["total"] == 1
    run = runs["items"][0]
    assert run["rule_id"] == rule["id"]
    assert run["status"] == "executed"
    assert run["rule_name"] == "Wasserschaden eskalieren"
    assert [a["ok"] for a in run["actions"]] == [True, True, True, True]
    assert run["actions"][3]["entity_id"] == follow[0]["id"]
    assert (
        _ok(client.get(f"{A}/runs", params={"rule_id": inactive["id"]}, headers=admin))["total"]
        == 0
    )

    # Idempotent and loop safe: a second run neither repeats the actions nor reacts to the
    # ticket.created event of the follow-up ticket (it also has category Wasserschaden).
    again = asyncio.run(process_events_once(settings, now=_later()))
    assert again["runs"] == 0
    assert _ok(client.get(f"{A}/runs", headers=admin))["total"] == 1
    assert len(_follow_ups()) == 1
    notes = _ok(
        client.get("/api/v1/workspace/notifications", params={"unread": True}, headers=care)
    )
    assert len([n for n in notes if n["kind"] == "automation"]) == 1

    # Tenant separation: tenant B sees only its own rule and no runs of A.
    b_rules = _ok(client.get(f"{A}/rules", headers=other))
    assert [r["name"] for r in b_rules] == ["Wasserschaden eskalieren"]
    assert b_rules[0]["id"] != rule["id"]
    assert client.get(f"{A}/rules/{rule['id']}", headers=other).status_code == 404
    assert (
        client.post(
            f"{A}/rules/{rule['id']}/activate", json={"active": False}, headers=other
        ).status_code
        == 404
    )
    assert _ok(client.get(f"{A}/runs", headers=other))["total"] == 0

    # Patch, then delete (delete only with tenant_settings:delete, docs/rules/M2-07.md).
    patched = _ok(
        client.patch(f"{A}/rules/{rule['id']}", json={"description": "Stufe 1"}, headers=admin)
    )
    assert patched["description"] == "Stufe 1"
    assert patched["active"] is True
    assert client.delete(f"{A}/rules/{rule['id']}", headers=care).status_code == 403
    assert client.delete(f"{A}/rules/{rule['id']}", headers=admin).status_code == 204
    assert client.get(f"{A}/rules/{rule['id']}", headers=admin).status_code == 404
    assert _ok(client.get(f"{A}/runs", headers=admin))["total"] == 0


def test_failed_action_is_recorded_and_does_not_block(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "autoadmin"))
    asyncio.run(process_events_once(settings))
    rule = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": f"Kaputt {RUN}",
                "active": True,
                "trigger_event_type": "ticket.created",
                "actions": [
                    {
                        "type": "create_ticket",
                        "template_id": "00000000-0000-4000-8000-000000000000",
                    },
                ],
            },
            headers=admin,
        ),
        201,
    )
    ok_rule = _ok(
        client.post(
            f"{A}/rules",
            json={
                "name": f"Heil {RUN}",
                "active": True,
                "trigger_event_type": "ticket.created",
                "actions": [{"type": "set_ticket_field", "field": "category", "value": "Geprüft"}],
            },
            headers=admin,
        ),
        201,
    )
    ticket = _ok(client.post("/api/v1/tickets", json={"title": "Fehlerfall"}, headers=admin), 201)
    result = asyncio.run(process_events_once(settings, now=_later()))
    assert result["failed"] >= 1
    failed = _ok(client.get(f"{A}/runs", params={"rule_id": rule["id"]}, headers=admin))["items"]
    assert len(failed) == 1
    assert failed[0]["status"] == "failed"
    assert "Ticketvorlage nicht gefunden" in failed[0]["error"]
    good = _ok(client.get(f"{A}/runs", params={"rule_id": ok_rule["id"]}, headers=admin))["items"]
    assert len(good) == 1
    assert good[0]["status"] == "executed"
    assert (
        _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=admin))["category"] == "Geprüft"
    )
    for rid in (rule["id"], ok_rule["id"]):
        assert client.delete(f"{A}/rules/{rid}", headers=admin).status_code == 204
