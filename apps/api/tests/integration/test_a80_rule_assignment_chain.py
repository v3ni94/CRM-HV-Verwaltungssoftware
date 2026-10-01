"""Sure chain after a learned contact rule (rule M9-11 with A80-01, follow-up 28.09.2026): when
an accepted learned rule assigns the contact (action ``assign_record``), property and unit
follow with the same deterministic chain the review uses (exactly one active tenancy contract
or exactly one active ownership unit), only into empty fields without a member's decision,
status ``auto`` with reason and event, without a second rule step (depth 1). Ambiguous
contracts leave the fields empty and the question open; a field set by a member or decided in
the review stays unchanged; rules and chain stay within the tenant. Synthetic data only."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.automation.tasks import process_events_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a80_assignment_chain import (
    _contact_with_email,
    _owner,
    _tenancy,
)
from tests.integration.test_a80_assignment_review import _eml
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _property, _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
T = "/api/v1/tickets"
R = "/api/v1/automation/rules"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rch-{RUN}", name=f"Rkette {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rchb-{RUN}", name=f"Rkette B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("a80radmin", a), ("a80radminb", b)):
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _by_dim(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["dimension"]: r for r in reviews}


_COUNTER = {"n": 0}


def _ingest(client: TestClient, h: dict[str, str], sender: str, body: str, **extra: Any) -> Any:
    _COUNTER["n"] += 1
    tag = f"{RUN}-rch-{_COUNTER['n']}"
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={
                "file": (
                    f"m-{tag}.eml",
                    _eml(sender, f"Anfrage {tag}", f"{body}\n\nVorgang {tag}", f"<{tag}@x>"),
                    "message/rfc822",
                )
            },
            headers=h,
        ),
        201,
    )["id"]
    return _ok(client.post(f"{M}/ingest", json={"document_id": doc, **extra}, headers=h), 201)


def _n(n: int) -> str:
    return f"{(int(RUN, 16) + 300 + n) % 900:03d}"


def _contact_with_contracts(
    client: TestClient, h: dict[str, str], name: str, units: list[str]
) -> dict[str, Any]:
    """Contact (e-mail address unknown to the sender lookup) with one tenancy per unit."""
    contact = _contact_with_email(client, h, name, f"{name.lower()}-{RUN}@kontakt.example")
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    for unit in units:
        _tenancy(client, h, unit, party["id"])
    return dict(contact)


def _learned_contact_rule(
    client: TestClient, h: dict[str, str], sender: str, target: str, contact_id: str
) -> dict[str, Any]:
    """The rule an accepted contact proposal creates (``learning.rule_definition``)."""
    label = "Mail" if target == "message" else "Ticket"
    rule = _ok(
        client.post(
            R,
            json={
                "name": f"Lernregel {label} {sender}: Kontakt",
                "active": True,
                "trigger_kind": "event",
                "trigger_event_type": "message.received",
                "conditions": {
                    "op": "and",
                    "conditions": [{"field": "entity.from_address", "op": "eq", "value": sender}],
                },
                "actions": [
                    {
                        "type": "assign_record",
                        "target": target,
                        "dimension": "contact",
                        "value": contact_id,
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    return dict(rule)


def _run_rules(settings: Any) -> None:
    # The rule job leaves events younger than PROCESS_LAG for the next run.
    asyncio.run(process_events_once(settings, now=datetime.now(UTC) + timedelta(seconds=30)))


def _auto_events(database: Database, tenant_id: Any, entity_id: str) -> list[dict[str, Any]]:
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            rows = conn.execute(
                text(
                    "SELECT payload FROM domain_event WHERE entity_id = :id "
                    "AND type = 'assignment_review.auto'"
                ),
                {"id": entity_id},
            ).all()
            return [dict(r._mapping["payload"]) for r in rows]
    finally:
        engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def _watermark(world: World, database: Database, redis_url: str) -> None:
    # The first pass per tenant only positions the watermark of the rule job.
    asyncio.run(process_events_once(_settings(database, redis_url)))


def test_learned_contact_rule_then_chain_fills_property_and_unit(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "a80radmin"))
    prop = _property(client, h, _n(1), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    contact = _contact_with_contracts(client, h, "Greta", [unit])
    sender = f"greta-privat-{RUN}@lernkette.example"
    rule = _learned_contact_rule(client, h, sender, "ticket", contact["id"])

    msg = _ingest(client, h, sender, "Guten Tag, kurze Frage.", auto_ticket=True)
    ticket_id = msg["ticket_id"]
    assert ticket_id
    before = _ok(client.get(f"{T}/{ticket_id}", headers=h))
    assert (before["contact_id"], before["property_id"], before["unit_id"]) == (None, None, None)

    _run_rules(_settings(database, redis_url))

    after = _ok(client.get(f"{T}/{ticket_id}", headers=h))
    assert after["contact_id"] == contact["id"]
    assert after["property_id"] == prop["id"]
    assert after["unit_id"] == unit
    reviews = _by_dim(_ok(client.get(f"{T}/{ticket_id}/assignment-review", headers=h)))
    assert reviews["contact"]["decision"] == "rule"
    for dimension in ("property", "unit"):
        assert reviews[dimension]["status"] == "auto"
        assert reviews[dimension]["reason"] == "eindeutiger Vertrag"
        assert reviews[dimension]["decision"] is None  # a member can still correct it
    events = {e["dimension"]: e for e in _auto_events(database, world.tenant_a, ticket_id)}
    for dimension in ("property", "unit"):
        event = events[dimension]
        assert event["reason"] == "eindeutiger Vertrag"
        assert event["rule_id"] == rule["id"]
        # Depth 1: the chain events carry the automation marker and trigger no rule again.
        assert event["automation"]["rule_id"] == rule["id"]
        assert event["automation"]["depth"] == 1
    runs = _ok(client.get("/api/v1/automation/runs", params={"limit": 50}, headers=h))["items"]
    details = [a["detail"] for r in runs if r["rule_id"] == rule["id"] for a in r["actions"]]
    assert any("sichere Kette ergänzt: Objekt, Einheit" in d for d in details), details

    # A later check of the ticket keeps the rows and writes no second event.
    _ok(client.patch(f"{T}/{ticket_id}", json={"priority": "high"}, headers=h))
    again = _by_dim(_ok(client.get(f"{T}/{ticket_id}/assignment-review", headers=h)))
    assert again["property"]["status"] == "auto"
    assert again["unit"]["status"] == "auto"
    assert len(_auto_events(database, world.tenant_a, ticket_id)) == len(events)


def test_mail_target_fills_property(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """A mail has no unit field: the chain fills the property only."""
    h = bearer(login(client, world, "a80radmin"))
    prop = _property(client, h, _n(2), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    contact = _contact_with_contracts(client, h, "Hanna", [unit])
    sender = f"hanna-privat-{RUN}@lernkette.example"
    _learned_contact_rule(client, h, sender, "message", contact["id"])

    msg = _ingest(client, h, sender, "Guten Tag, kurze Frage.")
    _run_rules(_settings(database, redis_url))

    after = _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))
    assert after["contact_id"] == contact["id"]
    assert after["property_id"] == prop["id"]
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))
    assert reviews["property"]["status"] == "auto"
    assert reviews["property"]["reason"] == "eindeutiger Vertrag"
    assert "unit" not in reviews


def test_two_contracts_leave_fields_empty_and_question_open(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "a80radmin"))
    prop = _property(client, h, _n(3), "rental")
    unit_a = _unit(client, h, prop["id"], "01")
    unit_b = _unit(client, h, prop["id"], "02")
    _owner(client, h, prop["id"])
    contact = _contact_with_contracts(client, h, "Ines", [unit_a, unit_b])
    sender = f"ines-privat-{RUN}@lernkette.example"
    _learned_contact_rule(client, h, sender, "message", contact["id"])

    # The address in the text makes the property an open question at intake.
    msg = _ingest(client, h, sender, "Guten Tag, in der Rheinpromenade 13 tropft der Hahn.")
    question = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))
    assert question["property"]["status"] == "open", question["property"]

    _run_rules(_settings(database, redis_url))

    after = _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))
    assert after["contact_id"] == contact["id"]
    assert after["property_id"] is None
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))
    assert reviews["property"]["status"] == "open"
    assert reviews["property"]["candidates"] == question["property"]["candidates"]
    assert not [
        e for e in _auto_events(database, world.tenant_a, msg["id"]) if e["dimension"] != "contact"
    ]


def test_field_set_by_member_or_decided_stays_unchanged(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "a80radmin"))
    settings = _settings(database, redis_url)
    prop = _property(client, h, _n(4), "rental")
    other = _property(client, h, _n(5), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    contact = _contact_with_contracts(client, h, "Jana", [unit])

    # (a) Ticket: a member sets the property before the rule runs; the chain overwrites
    # nothing and, the property being another one, leaves the unit alone.
    sender = f"jana-privat-{RUN}@lernkette.example"
    _learned_contact_rule(client, h, sender, "ticket", contact["id"])
    msg = _ingest(client, h, sender, "Guten Tag, kurze Frage.", auto_ticket=True)
    ticket_id = msg["ticket_id"]
    _ok(client.patch(f"{T}/{ticket_id}", json={"property_id": other["id"]}, headers=h))
    _run_rules(settings)
    ticket = _ok(client.get(f"{T}/{ticket_id}", headers=h))
    assert ticket["contact_id"] == contact["id"]
    assert ticket["property_id"] == other["id"]
    assert ticket["unit_id"] is None
    reviews = _by_dim(_ok(client.get(f"{T}/{ticket_id}/assignment-review", headers=h)))
    assert reviews["property"]["chosen_id"] == other["id"]
    assert reviews["unit"]["status"] != "auto"

    # (b) Mail: a member answered the property question with Nein; the field stays empty.
    sender_b = f"jana-buero-{RUN}@lernkette.example"
    _learned_contact_rule(client, h, sender_b, "message", contact["id"])
    mail = _ingest(client, h, sender_b, "Guten Tag, in der Rheinpromenade 13 klemmt die Tür.")
    assert (
        _by_dim(_ok(client.get(f"{M}/messages/{mail['id']}/assignment-review", headers=h)))[
            "property"
        ]["status"]
        == "open"
    )
    _ok(
        client.post(
            f"{M}/messages/{mail['id']}/assignment-review/decide",
            json={"dimension": "property", "decision": "reject", "seen_value": None},
            headers=h,
        )
    )
    _run_rules(settings)
    after = _ok(client.get(f"{M}/messages/{mail['id']}", headers=h))
    assert after["contact_id"] == contact["id"]
    assert after["property_id"] is None
    decided = _by_dim(_ok(client.get(f"{M}/messages/{mail['id']}/assignment-review", headers=h)))
    assert decided["property"]["status"] == "rejected"
    assert decided["property"]["decision"] == "reject"


def test_tenant_separation(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """The learned rule and its chain act only in their tenant: a mail of the same sender in
    another tenant stays unassigned, and the other tenant sees neither rule nor runs."""
    h = bearer(login(client, world, "a80radmin"))
    hb = bearer(login(client, world, "a80radminb"))
    prop = _property(client, h, _n(6), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    contact = _contact_with_contracts(client, h, "Karla", [unit])
    sender = f"karla-privat-{RUN}@lernkette.example"
    rule = _learned_contact_rule(client, h, sender, "message", contact["id"])

    mail_b = _ingest(client, hb, sender, "Guten Tag, kurze Frage.")
    mail_a = _ingest(client, h, sender, "Guten Tag, kurze Frage.")
    _run_rules(_settings(database, redis_url))

    assert _ok(client.get(f"{M}/messages/{mail_a['id']}", headers=h))["property_id"] == prop["id"]
    other = _ok(client.get(f"{M}/messages/{mail_b['id']}", headers=hb))
    assert (other["contact_id"], other["property_id"]) == (None, None)
    assert client.get(f"{R}/{rule['id']}", headers=hb).status_code == 404
    assert client.get(f"{M}/messages/{mail_a['id']}", headers=hb).status_code == 404
    runs_b = _ok(client.get("/api/v1/automation/runs", params={"limit": 50}, headers=hb))["items"]
    assert all(r["rule_id"] != rule["id"] for r in runs_b)
    assert _auto_events(database, world.tenant_b, mail_b["id"]) == []
