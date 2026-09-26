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

    missing = client.patch(f"{T}/{ticket['id']}", json={"status": "done"}, headers=h)
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
    refused = _ok(
        client.post(f"{T}/bulk-status", json={"ticket_ids": ids, "status": "done"}, headers=h)
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
    assert _ok(client.get(f"{T}/{c['id']}", headers=h))["resolution_kind"] == "weitergeleitet"
