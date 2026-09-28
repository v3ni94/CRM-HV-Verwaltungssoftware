"""Lern-Workflow (rule M9-11, operator 27.09.2026): rule proposals from repeated manual
decisions. Threshold 5 by default: four decisions propose nothing, the fifth does; a
contradicting decision resets the count; a rejected pattern comes back only with doubled
evidence; an accepted proposal creates an active rule of the rule engine that assigns the next
mail of the sender; ticket topic and assignee per sender domain; permissions and tenant
separation. Synthetic names and addresses only."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
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
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
T = "/api/v1/tickets"
P = "/api/v1/automation/rule-proposals"
S1 = f"hans{RUN}@hauswart-lern.example"  # property pattern, accepted
S2 = f"ida{RUN}@hauswart-zwei.example"  # contradiction
S3 = f"olga{RUN}@hauswart-drei.example"  # rejection and doubling
D4 = f"lernfirma{RUN}.example"  # ticket topic and assignee per domain


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lw-{RUN}", name=f"Lern {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lwb-{RUN}", name=f"Lern B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("lwadmin", "tenant_admin", a),
            ("lwstd", "standard", a),
            ("lwcare", "caretaker", a),
            ("lwadminb", "tenant_admin", b),
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


_COUNTER = {"n": 0}


def _ingest(client: TestClient, h: dict[str, str], sender: str, body: str, **extra: Any) -> Any:
    _COUNTER["n"] += 1
    tag = f"{RUN}-lw-{_COUNTER['n']}"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        sender,
        "info@example.com",
        f"Anfrage {tag}",
        f"<{tag}@x>",
    )
    msg["Date"] = "Sun, 27 Sep 2026 09:00:00 +0200"
    msg.set_content(f"{body}\n\nVorgang {tag}")
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": (f"m-{tag}.eml", bytes(msg), "message/rfc822")},
            headers=h,
        ),
        201,
    )["id"]
    return _ok(client.post(f"{M}/ingest", json={"document_id": doc, **extra}, headers=h), 201)


def _property_review(client: TestClient, h: dict[str, str], message_id: str) -> dict[str, Any]:
    rows = _ok(client.get(f"{M}/messages/{message_id}/assignment-review", headers=h))
    return next(r for r in rows if r["dimension"] == "property")


def _decide(
    client: TestClient, h: dict[str, str], message_id: str, decision: str, candidate: str | None
) -> None:
    body = {"dimension": "property", "decision": decision, "seen_value": None}
    if candidate:
        body["candidate_id"] = candidate
    _ok(client.post(f"{M}/messages/{message_id}/assignment-review/decide", json=body, headers=h))


def _mail_with_question(client: TestClient, h: dict[str, str], sender: str, prop: str) -> str:
    msg = _ingest(client, h, sender, "Guten Tag, in der Lernallee tropft der Wasserhahn.")
    review = _property_review(client, h, msg["id"])
    assert review["status"] == "open", review
    assert review["candidates"][0]["id"] == prop
    return str(msg["id"])


def _proposals(client: TestClient, h: dict[str, str], status: str = "proposed") -> list[Any]:
    rows: list[Any] = _ok(client.get(P, params={"status": status}, headers=h))
    return rows


def _pattern(
    rows: list[Any], key: str, field: str = "property", scope: str = "address"
) -> dict[str, Any] | None:
    return next(
        (r for r in rows if r["sender_key"] == key and r["field"] == field and r["scope"] == scope),
        None,
    )


@pytest.fixture(scope="module")
def data(client: TestClient, world: World) -> dict[str, Any]:
    h = bearer(login(client, world, "lwadmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "871",
                "name": "Lernhaus",
                "management_type": "rental",
                "street": "Lernallee",
                "postal_code": "12345",
                "city": "Musterstadt",
            },
            headers=h,
        ),
        201,
    )
    return {"property": prop["id"]}


def _later() -> datetime:
    # The rule job leaves events younger than PROCESS_LAG for the next run.
    return datetime.now(UTC) + timedelta(seconds=30)


def test_threshold_not_reached_then_fifth_decision_proposes(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "lwadmin"))
    prop = data["property"]
    ids = []
    for _ in range(4):
        mid = _mail_with_question(client, h, S1, prop)
        _decide(client, h, mid, "accept", prop)
        ids.append(mid)
    assert _pattern(_proposals(client, h), S1) is None  # 4 < 5

    mid = _mail_with_question(client, h, S1, prop)
    _decide(client, h, mid, "accept", prop)
    row = _pattern(_proposals(client, h), S1)
    assert row is not None
    assert row["status"] == "proposed"
    assert row["entity_type"] == "message"
    assert row["value"] == prop
    assert row["value_label"] == "871 Lernhaus"
    assert row["evidence_count"] == 5
    assert row["threshold"] == 5
    assert len(row["evidence"]["decision_ids"]) == 5
    assert row["evidence"]["addresses"] == [S1]
    assert row["rule_id"] is None
    # One address only: no domain pattern.
    assert _pattern(_proposals(client, h), S1.split("@")[1], scope="domain") is None
    # Nothing is active before a member accepts: the next mail stays a question.
    rules = _ok(client.get("/api/v1/automation/rules", headers=h))
    assert not [r for r in rules if S1 in r["name"]]


def test_contradicting_decision_resets(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "lwadmin"))
    prop = data["property"]
    for _ in range(3):
        _decide(client, h, _mail_with_question(client, h, S2, prop), "accept", prop)
    # A Nein on the proposal of exactly this property contradicts the pattern.
    _decide(client, h, _mail_with_question(client, h, S2, prop), "reject", None)
    for _ in range(4):
        _decide(client, h, _mail_with_question(client, h, S2, prop), "accept", prop)
    # 3 + 4 accepts, but only the 4 after the contradiction count.
    assert _pattern(_proposals(client, h), S2) is None
    _decide(client, h, _mail_with_question(client, h, S2, prop), "accept", prop)
    row = _pattern(_proposals(client, h), S2)
    assert row is not None
    assert row["evidence_count"] == 5

    # A contradiction after the proposal withdraws it.
    _decide(client, h, _mail_with_question(client, h, S2, prop), "reject", None)
    assert _pattern(_proposals(client, h), S2) is None
    withdrawn = _pattern(_proposals(client, h, "withdrawn"), S2)
    assert withdrawn is not None
    assert withdrawn["status"] == "withdrawn"
    # Withdrawn is no rejection: five new consistent decisions propose it again.
    for _ in range(5):
        _decide(client, h, _mail_with_question(client, h, S2, prop), "accept", prop)
    again = _pattern(_proposals(client, h), S2)
    assert again is not None
    assert again["id"] == withdrawn["id"]
    assert again["evidence_count"] == 5


def test_reject_suppresses_until_evidence_doubles(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "lwadmin"))
    prop = data["property"]
    # Configurable threshold: 2 for this test (tenant setting, change recorded).
    settings = _ok(client.get("/api/v1/tenant/settings", headers=h))
    assert settings["rule_proposal_threshold"] == 5
    assert (
        client.patch(
            "/api/v1/tenant/settings", json={"rule_proposal_threshold": 1}, headers=h
        ).status_code
        == 422
    )
    _ok(client.patch("/api/v1/tenant/settings", json={"rule_proposal_threshold": 2}, headers=h))
    try:
        for _ in range(2):
            _decide(client, h, _mail_with_question(client, h, S3, prop), "accept", prop)
        row = _pattern(_proposals(client, h), S3)
        assert row is not None
        assert row["evidence_count"] == 2
        assert row["threshold"] == 2

        rejected = _ok(
            client.post(
                f"{P}/{row['id']}/reject", json={"reason": "Hausmeister wechselt oft"}, headers=h
            )
        )
        assert rejected["status"] == "rejected"
        assert rejected["decision_reason"] == "Hausmeister wechselt oft"
        assert rejected["rejected_evidence_count"] == 2
        assert rejected["decided_by"] == str(world.users["lwadmin"])
        assert rejected["decided_at"]
        # Deciding again is refused, nothing changes.
        again = client.post(f"{P}/{row['id']}/reject", json={}, headers=h)
        assert again.status_code == 409
        assert again.json()["code"] == "MHVP-AUTO-0001"
        assert client.post(f"{P}/{row['id']}/accept", headers=h).status_code == 409

        # Evidence 3 < 2 * 2: stays rejected.
        _decide(client, h, _mail_with_question(client, h, S3, prop), "accept", prop)
        assert _pattern(_proposals(client, h), S3) is None
        # Evidence 4 = 2 * 2: proposed again.
        _decide(client, h, _mail_with_question(client, h, S3, prop), "accept", prop)
        back = _pattern(_proposals(client, h), S3)
        assert back is not None
        assert back["id"] == row["id"]
        assert back["evidence_count"] == 4
        assert back["decided_by"] is None
    finally:
        _ok(client.patch("/api/v1/tenant/settings", json={"rule_proposal_threshold": 5}, headers=h))


def test_accept_activates_rule_and_assigns_next_mail(
    client: TestClient, world: World, data: dict[str, Any], database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lwadmin"))
    prop = data["property"]
    row = _pattern(_proposals(client, h), S1)
    assert row is not None

    # Standard members read proposals but cannot accept (tenant_settings:update).
    std = bearer(login(client, world, "lwstd"))
    assert _pattern(_proposals(client, std), S1) is not None
    denied = client.post(f"{P}/{row['id']}/accept", headers=std)
    assert denied.status_code == 403

    accepted = _ok(client.post(f"{P}/{row['id']}/accept", headers=h))
    assert accepted["status"] == "accepted"
    assert accepted["decided_by"] == str(world.users["lwadmin"])
    assert accepted["rule_id"]
    rule = _ok(client.get(f"/api/v1/automation/rules/{accepted['rule_id']}", headers=h))
    assert rule["active"] is True
    assert rule["trigger_event_type"] == "message.received"
    assert rule["owner_user_id"] == str(world.users["lwadmin"])
    assert rule["conditions"] == {
        "op": "and",
        "conditions": [{"field": "entity.from_address", "op": "eq", "value": S1}],
    }
    assert rule["actions"] == [
        {"type": "assign_record", "target": "message", "dimension": "property", "value": prop}
    ]
    assert _pattern(_proposals(client, h), S1) is None
    assert _pattern(_proposals(client, h, "accepted"), S1) is not None

    # The rule job: the first pass per tenant only positions the watermark.
    asyncio.run(process_events_once(settings))
    nxt = _ingest(client, h, S1, "Kurze Nachricht ohne Adresse.")
    other = _ingest(client, h, S2, "Kurze Nachricht ohne Adresse.")
    assert nxt["property_id"] is None
    assert other["property_id"] is None
    asyncio.run(process_events_once(settings, now=_later()))

    assigned = _ok(client.get(f"{M}/messages/{nxt['id']}", headers=h))
    assert assigned["property_id"] == prop
    review = _property_review(client, h, nxt["id"])
    assert review["status"] == "auto"
    assert review["decision"] == "rule"
    assert review["reason"].startswith("Regel Lernregel Mail")
    # S2 has only a proposal, no rule: nothing assigned.
    assert _ok(client.get(f"{M}/messages/{other['id']}", headers=h))["property_id"] is None
    runs = _ok(client.get("/api/v1/automation/runs", params={"limit": 50}, headers=h))["items"]
    mine = [r for r in runs if r["rule_id"] == accepted["rule_id"]]
    assert mine
    assert mine[0]["status"] == "executed"
    assert any(a["detail"].startswith("Zugeordnet") for r in mine for a in r["actions"])

    # An accepted proposal is final here; the rule is switched off in the rule admin.
    _ok(client.post(f"{P}/{row['id']}/reject", json={}, headers=h), 409)


def test_ticket_topic_and_assignee_per_domain(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lwadmin"))
    member = str(world.users["lwstd"])
    senders = [f"anna@{D4}", f"bernd@{D4}", f"anna@{D4}", f"bernd@{D4}", f"anna@{D4}"]
    for index, sender in enumerate(senders):
        msg = _ingest(
            client, h, sender, "Bitte um Rückmeldung zu meinem Anliegen.", auto_ticket=True
        )
        assert msg["ticket_id"]
        _ok(
            client.patch(
                f"{T}/{msg['ticket_id']}",
                json={"topic": "vertrag", "assignee_user_id": member},
                headers=h,
            )
        )
        rows = _proposals(client, h)
        topic = _pattern(rows, D4, field="topic", scope="domain")
        assert (topic is None) == (index < 4)
    rows = _proposals(client, h)
    topic = _pattern(rows, D4, field="topic", scope="domain")
    assignee = _pattern(rows, D4, field="assignee_user_id", scope="domain")
    assert topic is not None
    assert assignee is not None
    assert topic["entity_type"] == "ticket"
    assert topic["value"] == "vertrag"
    assert topic["value_label"] == "Vertrag"
    assert topic["evidence"]["addresses"] == [f"anna@{D4}", f"bernd@{D4}"]
    assert assignee["value"] == member
    assert assignee["value_label"] == "lwstd"
    # Per address only 3 and 2 decisions: no address pattern.
    assert _pattern(rows, f"anna@{D4}", field="topic") is None

    accepted = _ok(client.post(f"{P}/{topic['id']}/accept", headers=h))
    rule = _ok(client.get(f"/api/v1/automation/rules/{accepted['rule_id']}", headers=h))
    assert rule["actions"] == [{"type": "set_ticket_field", "field": "topic", "value": "vertrag"}]
    assert {"field": "entity.opens_ticket", "op": "eq", "value": True} in rule["conditions"][
        "conditions"
    ]

    asyncio.run(process_events_once(settings))
    nxt = _ingest(client, h, f"carla@{D4}", "Eine neue Frage zum Anliegen.", auto_ticket=True)
    asyncio.run(process_events_once(settings, now=_later()))
    ticket = _ok(client.get(f"{T}/{nxt['ticket_id']}", headers=h))
    assert ticket["topic"] == "vertrag"
    # The assignee proposal stays a proposal: no assignee set by it.
    assert ticket["assignee_user_id"] is None
    assert _pattern(_proposals(client, h), D4, field="assignee_user_id", scope="domain")


def test_accept_rechecks_evidence(client: TestClient, world: World, data: dict[str, Any]) -> None:
    """The accept recomputes the evidence from the decision log: once the stored evidence (5
    decisions of S2) no longer qualifies, here because the threshold was raised to 6, the
    accept answers 409 and writes nothing."""
    h = bearer(login(client, world, "lwadmin"))
    row = _pattern(_proposals(client, h), S2)
    assert row is not None
    _ok(client.patch("/api/v1/tenant/settings", json={"rule_proposal_threshold": 6}, headers=h))
    try:
        stale = client.post(f"{P}/{row['id']}/accept", headers=h)
        assert stale.status_code == 409, stale.text
        assert stale.json()["code"] == "MHVP-AUTO-0002"
        assert _pattern(_proposals(client, h), S2) is not None  # nothing written
    finally:
        _ok(client.patch("/api/v1/tenant/settings", json={"rule_proposal_threshold": 5}, headers=h))


def test_permissions_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "lwadmin"))
    care = bearer(login(client, world, "lwcare"))
    other = bearer(login(client, world, "lwadminb"))
    assert client.get(P, headers=care).status_code == 403
    rows = _proposals(client, h, "all")
    assert rows
    assert _proposals(client, other, "all") == []
    target = rows[0]["id"]
    assert client.post(f"{P}/{target}/accept", headers=other).status_code == 404
    assert client.post(f"{P}/{target}/reject", json={}, headers=other).status_code == 404
    assert client.post(f"{P}/{target}/reject", json={"x": 1}, headers=h).status_code == 422
    assert client.get(P, params={"status": "unknown"}, headers=h).status_code == 422


# Fix 28.09.2026 (review of 1.40.2): a member's decision always wins over a learned rule, the
# rule job runs asynchronously; one learned value per pattern group; Ja on a rule's value.
D5 = f"lernvorrang{RUN}.example"  # learned topic and assignee against manual decisions
D6 = f"adminregel{RUN}.example"  # hand written admin rule keeps its overwrite semantics
NEUTRAL = "Bitte um Rückmeldung zu meinem Anliegen."
R = "/api/v1/automation/rules"
FIELD_SET = "Feld bereits gesetzt; die Lernregel füllt nur ein leeres Feld."
MEMBER_DECIDED = "Von einem Mitglied entschieden; die Lernregel ändert nichts."


def _ticket(client: TestClient, h: dict[str, str], ticket_id: str) -> dict[str, Any]:
    ticket: dict[str, Any] = _ok(client.get(f"{T}/{ticket_id}", headers=h))
    return ticket


def _assigned_notes(client: TestClient, h: dict[str, str], ticket_id: str) -> list[Any]:
    rows = _ok(client.get("/api/v1/workspace/notifications", params={"limit": 200}, headers=h))
    return [n for n in rows if n["kind"] == "ticket_assigned" and n["entity_id"] == ticket_id]


def _run_details(client: TestClient, h: dict[str, str], rule_ids: set[str]) -> dict[Any, str]:
    """``(rule id, ticket id)``: detail of the rule's action for that ticket."""
    runs = _ok(client.get("/api/v1/automation/runs", params={"limit": 200}, headers=h))["items"]
    return {
        (r["rule_id"], a.get("entity_id")): a["detail"]
        for r in runs
        if r["rule_id"] in rule_ids
        for a in r["actions"]
    }


def _clear_ticket_field(database: Database, tenant_id: Any, ticket_id: str, column: str) -> None:
    """Empties a field behind the API (no endpoint clears topic or assignee today) so that the
    event check of the guard is reached: the member's decision is in the log only."""
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            conn.execute(
                text(f"UPDATE ticket SET {column} = NULL WHERE id = :id"), {"id": ticket_id}
            )
    finally:
        engine.dispose()


def test_learned_rule_never_overrides_a_member(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """The probe of the review: a mail opens a ticket, a member sets topic and assignee, only
    then the rule job runs. The learned rules keep the member's values and send no
    notification; an empty field without a decision is still filled; a topic of the automatic
    classification stays (a member who kept it leaves no trace); a field emptied after a
    member's decision stays empty."""
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lwadmin"))
    std = bearer(login(client, world, "lwstd"))
    member, care = str(world.users["lwstd"]), str(world.users["lwcare"])
    for sender in [f"a@{D5}", f"b@{D5}", f"a@{D5}", f"b@{D5}", f"a@{D5}"]:
        msg = _ingest(client, h, sender, NEUTRAL, auto_ticket=True)
        body = {"topic": "vertrag", "assignee_user_id": member}
        _ok(client.patch(f"{T}/{msg['ticket_id']}", json=body, headers=h))
    rows = _proposals(client, h)
    rules: dict[str, str] = {}
    for field in ("topic", "assignee_user_id"):
        row = _pattern(rows, D5, field=field, scope="domain")
        assert row is not None, field
        accepted = _ok(client.post(f"{P}/{row['id']}/accept", headers=h))
        assert accepted["superseded_rules"] == []
        rules[field] = accepted["rule_id"]

    asyncio.run(process_events_once(settings, now=_later()))
    empty = _ingest(client, h, f"c@{D5}", NEUTRAL, auto_ticket=True)
    manual = _ingest(client, h, f"d@{D5}", NEUTRAL, auto_ticket=True)
    classified = _ingest(client, h, f"e@{D5}", "Neue Frage zum Verkauf.", auto_ticket=True)
    emptied = _ingest(client, h, f"g@{D5}", NEUTRAL, auto_ticket=True)
    assert _ticket(client, h, classified["ticket_id"])["topic"] == "verkauf"
    # Members decide on two tickets before the rule job runs.
    body = {"topic": "verkauf", "assignee_user_id": care}
    _ok(client.patch(f"{T}/{manual['ticket_id']}", json=body, headers=h))
    _ok(client.patch(f"{T}/{emptied['ticket_id']}", json=body, headers=h))
    _clear_ticket_field(database, world.tenant_a, emptied["ticket_id"], "topic")
    asyncio.run(process_events_once(settings, now=_later()))

    filled = _ticket(client, h, empty["ticket_id"])
    assert (filled["topic"], filled["assignee_user_id"]) == ("vertrag", member)
    assert len(_assigned_notes(client, std, empty["ticket_id"])) == 1
    kept = _ticket(client, h, manual["ticket_id"])
    assert (kept["topic"], kept["assignee_user_id"]) == ("verkauf", care)
    assert _assigned_notes(client, std, manual["ticket_id"]) == []
    auto = _ticket(client, h, classified["ticket_id"])
    assert (auto["topic"], auto["assignee_user_id"]) == ("verkauf", member)
    assert _ticket(client, h, emptied["ticket_id"])["topic"] is None

    details = _run_details(client, h, set(rules.values()))
    assert details[(rules["topic"], empty["ticket_id"])] == "topic gesetzt."
    assert details[(rules["topic"], manual["ticket_id"])] == FIELD_SET
    assert details[(rules["assignee_user_id"], manual["ticket_id"])] == FIELD_SET
    assert details[(rules["topic"], classified["ticket_id"])] == FIELD_SET
    assert details[(rules["topic"], emptied["ticket_id"])] == MEMBER_DECIDED


def test_admin_rule_keeps_overwrite_semantics(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """A hand written rule (no proposal) still sets the field when the job runs, also over a
    member's value (compatibility, rule M9-02); only learned rules fill empty fields."""
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lwadmin"))
    conditions = [
        {"field": "entity.from_domain", "op": "eq", "value": D6},
        {"field": "entity.opens_ticket", "op": "eq", "value": True},
    ]
    rule = _ok(
        client.post(
            R,
            json={
                "name": f"Adminregel Thema {RUN}",
                "active": True,
                "trigger_event_type": "message.received",
                "conditions": {"op": "and", "conditions": conditions},
                "actions": [{"type": "set_ticket_field", "field": "topic", "value": "verkauf"}],
            },
            headers=h,
        ),
        201,
    )
    try:
        asyncio.run(process_events_once(settings, now=_later()))
        msg = _ingest(client, h, f"x@{D6}", NEUTRAL, auto_ticket=True)
        _ok(client.patch(f"{T}/{msg['ticket_id']}", json={"topic": "vertrag"}, headers=h))
        asyncio.run(process_events_once(settings, now=_later()))
        assert _ticket(client, h, msg["ticket_id"])["topic"] == "verkauf"
    finally:
        _ok(client.post(f"{R}/{rule['id']}/activate", json={"active": False}, headers=h))


def test_accept_supersedes_learned_rule_of_same_group(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Members now choose another topic for D5: accepting the new proposal deactivates the
    learned rule of the same group (who and when in the answer and the rule log), leaves the
    learned rule of another group and a hand written rule on the same sender alone, and the
    new value takes effect (with both active the older rule would fill the field first)."""
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lwadmin"))
    old = _pattern(_proposals(client, h, "accepted"), D5, field="topic", scope="domain")
    assert old is not None
    assert old["value"] == "vertrag"
    # Two "verkauf" decisions exist already (the members' tickets of the previous test).
    for sender in [f"a@{D5}", f"b@{D5}", f"a@{D5}"]:
        msg = _ingest(client, h, sender, NEUTRAL, auto_ticket=True)
        _ok(client.patch(f"{T}/{msg['ticket_id']}", json={"topic": "verkauf"}, headers=h))
    new = _pattern(_proposals(client, h), D5, field="topic", scope="domain")
    assert new is not None
    assert new["value"] == "verkauf"
    admin = _ok(
        client.post(
            R,
            json={
                "name": f"Adminregel Priorität {RUN}",
                "active": True,
                "trigger_event_type": "message.received",
                "conditions": {"field": "entity.from_domain", "op": "eq", "value": D5},
                "actions": [{"type": "set_ticket_field", "field": "priority", "value": "high"}],
            },
            headers=h,
        ),
        201,
    )
    try:
        accepted = _ok(client.post(f"{P}/{new['id']}/accept", headers=h))
        assert [s["rule_id"] for s in accepted["superseded_rules"]] == [old["rule_id"]]
        superseded = accepted["superseded_rules"][0]
        assert superseded["proposal_id"] == old["id"]
        assert superseded["value"] == "vertrag"
        assert superseded["rule_name"].startswith("Lernregel Ticket")
        assert superseded["deactivated_by"] == str(world.users["lwadmin"])
        assert superseded["deactivated_at"]
        assert _ok(client.get(f"{R}/{old['rule_id']}", headers=h))["active"] is False
        assert _ok(client.get(f"{R}/{accepted['rule_id']}", headers=h))["active"] is True
        assert _ok(client.get(f"{R}/{admin['id']}", headers=h))["active"] is True
        assignee = _pattern(_proposals(client, h, "accepted"), D5, "assignee_user_id", "domain")
        assert assignee is not None
        assert _ok(client.get(f"{R}/{assignee['rule_id']}", headers=h))["active"] is True
        # The list keeps the answer lean; the deactivation stays in the rule's history.
        listed = _pattern(_proposals(client, h, "accepted"), D5, field="topic", scope="domain")
        assert listed is not None
        assert listed["superseded_rules"] == []

        asyncio.run(process_events_once(settings, now=_later()))
        nxt = _ingest(client, h, f"f@{D5}", NEUTRAL, auto_ticket=True)
        asyncio.run(process_events_once(settings, now=_later()))
        assert _ticket(client, h, nxt["ticket_id"])["topic"] == "verkauf"
        details = _run_details(client, h, {old["rule_id"]})
        assert (old["rule_id"], nxt["ticket_id"]) not in details
        # An accepted proposal is final.
        again = _ok(client.post(f"{P}/{new['id']}/accept", headers=h), 409)
        assert again["code"] == "MHVP-AUTO-0001"
    finally:
        _ok(client.post(f"{R}/{admin['id']}/activate", json={"active": False}, headers=h))


def test_ja_confirms_or_corrects_a_rule_assignment(
    client: TestClient, world: World, data: dict[str, Any], database: Database, redis_url: str
) -> None:
    """A field set by a learned rule lists the rule's value first and the check's proposals
    after it: a Ja confirms the rule's value or corrects it to another proposal directly,
    without Nein first (formerly 409, the row had no candidates). A record outside the list
    still needs Nein first (manual choice)."""
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lwadmin"))
    prop = data["property"]
    other = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "872",
                "name": "Zweithaus",
                "management_type": "rental",
                "street": "Lernweg",
                "postal_code": "12345",
                "city": "Musterstadt",
            },
            headers=h,
        ),
        201,
    )["id"]
    asyncio.run(process_events_once(settings, now=_later()))
    plain = _ingest(client, h, S1, "Kurze Nachricht ohne Adresse.")
    hinted = _ingest(client, h, S1, "Guten Tag, im Lernweg klemmt die Haustür.")
    third = _ingest(client, h, S1, "Kurze Nachricht ohne Adresse.")
    question = _property_review(client, h, hinted["id"])
    assert question["status"] == "open"
    assert [c["id"] for c in question["candidates"]] == [other]
    asyncio.run(process_events_once(settings, now=_later()))

    for msg, expected in ((plain, [prop]), (hinted, [prop, other]), (third, [prop])):
        review = _property_review(client, h, msg["id"])
        assert (review["status"], review["decision"]) == ("auto", "rule")
        assert [c["id"] for c in review["candidates"]] == expected
        assert review["candidates"][0]["reasons"][0].startswith("Regel Lernregel Mail")

    def decide(message_id: str, candidate: str) -> Any:
        body = {
            "dimension": "property",
            "decision": "accept",
            "candidate_id": candidate,
            "seen_value": prop,
        }
        return client.post(
            f"{M}/messages/{message_id}/assignment-review/decide", json=body, headers=h
        )

    _ok(decide(plain["id"], prop))  # Ja on the rule's value confirms it
    confirmed = _property_review(client, h, plain["id"])
    assert (confirmed["status"], confirmed["decision"]) == ("accepted", "accept")
    _ok(decide(hinted["id"], other))  # Ja on the other proposal corrects it directly
    assert _ok(client.get(f"{M}/messages/{hinted['id']}", headers=h))["property_id"] == other
    corrected = _property_review(client, h, hinted["id"])
    assert (corrected["status"], corrected["decision"]) == ("accepted", "accept")
    stale = decide(third["id"], other)
    assert stale.status_code == 409, stale.text
    assert _ok(client.get(f"{M}/messages/{third['id']}", headers=h))["property_id"] == prop
