"""Erledigungsnotiz beim Abschluss (Betreiberauftrag 26.09.2026): closing without
``resolution`` is refused with 422, with it the kind and note are stored on the ticket, as a
learning example (``AiExample``, task ``ticket_resolution``, GET /ai/examples) and as a step of
a matching playbook; bulk and merge accept a shared resolution."""

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
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rs-{RUN}", name=f"Erledigung {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("rsadmin"), display_name="rsadmin", password=PASSWORD
        )
        world.users["rsadmin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        std = await services.create_user(
            factory, email=world.email("rsstd"), display_name="rsstd", password=PASSWORD
        )
        world.users["rsstd"] = std
        await services.add_member(
            factory, tenant_id=a, user_id=std, role_codes=["standard"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url, ai_inline=True)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = _settings(database, redis_url, ai_inline=True)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ticket(c: TestClient, h: dict[str, str], title: str) -> dict[str, Any]:
    return cast(dict[str, Any], _ok(c.post(T, json={"title": title}, headers=h), 201))


S = "/api/v1/tenant/settings"
RESOLUTION = {"kind": "auskunft_erteilt", "note": "Rückruf erledigt"}


def _examples_for(client: TestClient, h: dict[str, str], ticket_id: str) -> list[dict[str, Any]]:
    examples = _ok(
        client.get("/api/v1/ai/examples", params={"task": "ticket_resolution"}, headers=h)
    )
    return [e for e in examples["data"] if e["features"].get("ticket_id") == ticket_id]


def test_examples_are_stored_only_with_the_tenant_switch(client: TestClient, world: World) -> None:
    """ADR 0010, M7-04: ``ai_learning_examples_enabled`` is off by default; closing stores the
    resolution on the ticket but no learning example until the operator enables the switch."""
    h = bearer(login(client, world, "rsadmin"))
    assert _ok(client.get(S, headers=h))["ai_learning_examples_enabled"] is False
    ticket = _ticket(client, h, f"Ohne Schalter {RUN}")
    done = _ok(
        client.patch(
            f"{T}/{ticket['id']}", json={"status": "done", "resolution": RESOLUTION}, headers=h
        )
    )
    assert done["resolution_kind"] == "auskunft_erteilt"
    assert _examples_for(client, h, ticket["id"]) == []

    enabled = _ok(client.patch(S, json={"ai_learning_examples_enabled": True}, headers=h))
    assert enabled["ai_learning_examples_enabled"] is True
    assert client.patch(S, json={"ai_learning_examples_enabled": "x"}, headers=h).status_code == 422
    ticket = _ticket(client, h, f"Mit Schalter {RUN}")
    _ok(
        client.patch(
            f"{T}/{ticket['id']}", json={"status": "done", "resolution": RESOLUTION}, headers=h
        )
    )
    assert len(_examples_for(client, h, ticket["id"])) == 1


def test_deleting_the_contact_removes_its_examples(client: TestClient, world: World) -> None:
    """DSGVO (ADR 0010): the examples built from the contact's tickets go with the contact in
    the same transaction; examples of other tickets stay."""
    h = bearer(login(client, world, "rsadmin"))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Lernbeispiel {RUN}"},
            headers=h,
        ),
        201,
    )
    linked = _ok(
        client.post(
            T, json={"title": f"Mit Kontakt {RUN}", "contact_id": contact["id"]}, headers=h
        ),
        201,
    )
    other = _ticket(client, h, f"Ohne Kontakt {RUN}")
    for t in (linked, other):
        _ok(
            client.patch(
                f"{T}/{t['id']}", json={"status": "done", "resolution": RESOLUTION}, headers=h
            )
        )
    assert (
        _examples_for(client, h, linked["id"])[0]["features"]["entitaeten"]["contact_id"]
        == contact["id"]
    )
    assert len(_examples_for(client, h, other["id"])) == 1

    assert client.delete(f"/api/v1/contacts/{contact['id']}", headers=h).status_code == 204
    assert _examples_for(client, h, linked["id"]) == []
    assert len(_examples_for(client, h, other["id"])) == 1


def test_close_requires_resolution_and_stores_it(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rsadmin"))
    title = f"Telefonnummer fehlt Mieter {RUN}"
    playbook = _ok(
        client.post(
            "/api/v1/mail/playbooks",
            json={"title": title, "keywords": ["telefonnummer"], "steps": ["Anrufen"]},
            headers=h,
        ),
        201,
    )
    ticket = _ticket(client, h, title)

    # Regular users must give a resolution; administrators may close without one
    # (Betreiber 26.09.2026).
    hs = bearer(login(client, world, "rsstd"))
    missing = client.patch(f"{T}/{ticket['id']}", json={"status": "done"}, headers=hs)
    assert missing.status_code == 422
    other = client.patch(
        f"{T}/{ticket['id']}",
        json={"status": "done", "resolution": {"kind": "sonstiges"}},
        headers=h,
    )
    assert other.status_code == 422
    unknown = client.patch(
        f"{T}/{ticket['id']}",
        json={"status": "done", "resolution": {"kind": "erfunden"}},
        headers=h,
    )
    assert unknown.status_code == 422
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["status"] == "new"

    done = _ok(
        client.patch(
            f"{T}/{ticket['id']}",
            json={
                "status": "done",
                "resolution": {"kind": "stammdaten_ergaenzt", "note": "Telefon nachgetragen"},
            },
            headers=h,
        )
    )
    assert done["resolution_kind"] == "stammdaten_ergaenzt"
    assert done["resolution_note"] == "Telefon nachgetragen"
    assert done["resolved_by"] == str(world.users["rsadmin"])

    examples = _ok(
        client.get("/api/v1/ai/examples", params={"task": "ticket_resolution"}, headers=h)
    )
    mine = [e for e in examples["data"] if e["features"].get("ticket_id") == ticket["id"]]
    assert len(mine) == 1
    assert mine[0]["decision"] == "stammdaten_ergaenzt"
    assert mine[0]["result"]["note"] == "Telefon nachgetragen"
    assert mine[0]["features"]["betreff"] == title
    assert examples["meta"]["total"] >= 1

    playbooks = _ok(client.get("/api/v1/mail/playbooks", params={"q": RUN}, headers=h))
    learned = next(p for p in playbooks if p["id"] == playbook["id"])
    assert "Erledigung: Stammdaten ergänzt: Telefon nachgetragen" in learned["steps"]

    # Reopening clears the resolution; the history stays in the learning examples.
    reopened = _ok(client.patch(f"{T}/{ticket['id']}", json={"status": "in_progress"}, headers=h))
    assert reopened["resolution_kind"] is None


def test_bulk_with_shared_resolution(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rsadmin"))
    first = _ticket(client, h, f"Bulk Erledigung 1 {RUN}")
    second = _ticket(client, h, f"Bulk Erledigung 2 {RUN}")
    ids = [first["id"], second["id"]]
    # Without a resolution a regular user is refused; administrators are exempt.
    hs = bearer(login(client, world, "rsstd"))
    refused = _ok(
        client.post(f"{T}/bulk-status", json={"ticket_ids": ids, "status": "done"}, headers=hs)
    )
    assert refused["changed"] == []
    assert len(refused["failed"]) == 2
    result = _ok(
        client.post(
            f"{T}/bulk-status",
            json={
                "ticket_ids": ids,
                "status": "rejected",
                "resolution": {"kind": "kein_handlungsbedarf", "note": "Doppelt gemeldet"},
            },
            headers=h,
        )
    )
    assert {c["id"] for c in result["changed"]} == set(ids)
    for ticket_id in ids:
        row = _ok(client.get(f"{T}/{ticket_id}", headers=h))
        assert (row["resolution_kind"], row["resolution_note"]) == (
            "kein_handlungsbedarf",
            "Doppelt gemeldet",
        )


def test_merge_sets_resolution_of_sources(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rsadmin"))
    a = _ticket(client, h, f"Merge Erledigung A {RUN}")
    b = _ticket(client, h, f"Merge Erledigung B {RUN}")
    target = _ok(client.post(f"{T}/merge", json={"ticket_ids": [a["id"], b["id"]]}, headers=h), 201)
    source = _ok(client.get(f"{T}/{a['id']}", headers=h))
    assert source["resolution_kind"] == "zusammengefuehrt"
    assert str(target["number"]) in source["resolution_note"]
    assert source["resolved_by"] == str(world.users["rsadmin"])
    # Same audit trail as transition_status: status event with the resolution and a learning
    # example, although no resolution was passed (review 1.25.0).
    status_events = [e for e in source["events"] if e["kind"] == "status"]
    assert len(status_events) == 1
    assert status_events[0]["data"]["from"] == "new"
    assert status_events[0]["data"]["to"] == "closed"
    assert status_events[0]["data"]["merge"] is True
    assert status_events[0]["data"]["resolution"]["kind"] == "zusammengefuehrt"
    assert status_events[0]["data"]["resolution"]["note"] == source["resolution_note"]
    examples = _ok(
        client.get("/api/v1/ai/examples", params={"task": "ticket_resolution"}, headers=h)
    )
    for source_id in (a["id"], b["id"]):
        mine = [e for e in examples["data"] if e["features"].get("ticket_id") == source_id]
        assert len(mine) == 1, source_id
        assert mine[0]["decision"] == "zusammengefuehrt"
        assert str(target["number"]) in mine[0]["result"]["note"]

    c = _ticket(client, h, f"Merge Erledigung C {RUN}")
    _ok(
        client.post(
            f"{T}/merge",
            json={
                "ticket_ids": [c["id"]],
                "target_ticket_id": target["id"],
                "resolution": {"kind": "weitergeleitet"},
            },
            headers=h,
        ),
        201,
    )
    third = _ok(client.get(f"{T}/{c['id']}", headers=h))
    assert third["resolution_kind"] == "weitergeleitet"
    status_events = [e for e in third["events"] if e["kind"] == "status"]
    assert len(status_events) == 1
    assert status_events[0]["data"]["resolution"] == {"kind": "weitergeleitet", "note": None}
    examples = _ok(
        client.get("/api/v1/ai/examples", params={"task": "ticket_resolution"}, headers=h)
    )
    mine = [e for e in examples["data"] if e["features"].get("ticket_id") == c["id"]]
    assert len(mine) == 1
    assert mine[0]["decision"] == "weitergeleitet"
