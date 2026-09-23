"""M9 workspace: dashboard tiles by permission, cross entity search, notifications from the
maintenance reminder job (idempotent), calendar with own, shared and derived dates, saved
filters per user, all-or-nothing bulk actions, tenant separation."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from mhvp.workspace.tasks import reminders_once
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"w-{RUN}", name=f"Arbeit {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"w2-{RUN}", name=f"Arbeit2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m9admin", a, "tenant_admin"),
            ("m9colleague", a, "standard"),
            ("m9caretaker", a, "caretaker"),
            ("m9other", b, "tenant_admin"),
            ("m9padmin", None, ""),
        ]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=tenant is None,
            )
            world.users[name] = uid
            if tenant is not None:
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


def test_workspace_flow(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "m9admin"))
    colleague = bearer(login(client, world, "m9colleague"))
    caretaker = bearer(login(client, world, "m9caretaker"))
    other = bearer(login(client, world, "m9other"))
    today = local_today()

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "901",
                "name": f"Suchhaus {RUN}",
                "management_type": "rental",
                "city": "Monheim am Rhein",
                "manager_user_id": str(world.users["m9admin"]),
            },
            headers=h,
        ),
        201,
    )
    due = today.replace(day=1) if today.day > 1 else today
    item = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/maintenance",
            json={"kind": "inspection", "title": "Prüfung Aufzug", "due_date": due.isoformat()},
            headers=h,
        ),
        201,
    )
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Suche", "last_name": f"Treffer{RUN}"},
            headers=h,
        ),
        201,
    )

    # Dashboard: tiles follow permissions; money stays locked.
    board = _ok(client.get(f"{W}/dashboard", headers=h))
    assert board["tiles"]["properties"] == 1
    assert board["tiles"]["maintenance_due_30d"] == 1
    assert board["accounting"] == "locked_until_g1"
    assert any(u["entity_id"] == item["id"] for u in board["upcoming"])
    care_board = _ok(client.get(f"{W}/dashboard", headers=caretaker))
    assert "contacts" not in care_board["tiles"]
    assert "properties" in care_board["tiles"]

    # Search across entities, filtered by permission and tenant.
    hits = _ok(client.get(f"{W}/search", params={"q": f"{RUN}"}, headers=h))
    kinds = {x["entity_type"] for x in hits}
    assert {"property", "contact"} <= kinds
    care_hits = _ok(client.get(f"{W}/search", params={"q": f"{RUN}"}, headers=caretaker))
    assert {x["entity_type"] for x in care_hits} == {"property"}
    assert _ok(client.get(f"{W}/search", params={"q": f"Suchhaus {RUN}"}, headers=other)) == []

    # Reminder job: one notification for the manager, not repeated on the next run.
    settings = _settings(database, redis_url)
    assert asyncio.run(reminders_once(settings, today))["created"] >= 1
    assert asyncio.run(reminders_once(settings, today))["created"] == 0
    notes = _ok(client.get(f"{W}/notifications", params={"unread": True}, headers=h))
    mine = [n for n in notes if n["entity_id"] == item["id"]]
    assert len(mine) == 1
    assert mine[0]["kind"] in {"maintenance_due", "maintenance_overdue"}
    assert _ok(client.get(f"{W}/notifications", headers=colleague)) == []
    _ok(client.post(f"{W}/notifications/read", headers=h), 204)
    assert _ok(client.get(f"{W}/notifications", params={"unread": True}, headers=h)) == []

    # Calendar: own entry, shared entry of a colleague, derived maintenance date.
    start, end = today.replace(day=1).isoformat(), date(today.year + 1, 1, 31).isoformat()
    own = _ok(
        client.post(
            f"{W}/calendar",
            json={"title": "Begehung", "starts_on": today.isoformat(), "property_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{W}/calendar",
            json={"title": "Privat", "starts_on": today.isoformat()},
            headers=colleague,
        ),
        201,
    )
    _ok(
        client.post(
            f"{W}/calendar",
            json={"title": "Teamtermin", "starts_on": today.isoformat(), "shared": True},
            headers=colleague,
        ),
        201,
    )
    cal = _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=h))
    titles = {c["title"] for c in cal}
    assert {"Begehung", "Teamtermin"} <= titles
    assert "Privat" not in titles
    assert any(c["kind"] == "maintenance" for c in cal)
    shared = next(c for c in cal if c["title"] == "Teamtermin")
    assert shared["editable"] is False
    assert client.delete(f"{W}/calendar/{shared['entity_id']}", headers=h).status_code == 404
    _ok(client.delete(f"{W}/calendar/{own['entity_id']}", headers=h), 204)
    bad = client.get(f"{W}/calendar", params={"start": end, "end": start}, headers=h)
    assert bad.status_code == 422
    bad_entry = client.post(
        f"{W}/calendar",
        json={"title": "x", "starts_on": "2026-05-02", "ends_on": "2026-05-01"},
        headers=h,
    )
    assert bad_entry.status_code == 422
    assert (
        _ok(client.get(f"{W}/calendar", params={"start": start, "end": end}, headers=other)) == []
    )

    # Saved filters: per user, same name replaces.
    body = {"resource": "contacts", "name": "Monheim", "params": {"city": "Monheim"}}
    f1 = _ok(client.put(f"{W}/filters", json=body, headers=h))
    f2 = _ok(client.put(f"{W}/filters", json=body | {"params": {"city": "Baumberg"}}, headers=h))
    assert f1["id"] == f2["id"]
    assert f2["params"] == {"city": "Baumberg"}
    assert _ok(client.get(f"{W}/filters", params={"resource": "contacts"}, headers=colleague)) == []
    assert client.put(f"{W}/filters", json=body | {"resource": "x"}, headers=h).status_code == 422
    assert client.delete(f"{W}/filters/{f1['id']}", headers=colleague).status_code == 404
    _ok(client.delete(f"{W}/filters/{f1['id']}", headers=h), 204)

    # Bulk: all or nothing, permission checked, idempotent.
    tag = {"action": "contacts.add_tag", "ids": [contact["id"]], "tag": "Beirat"}
    assert _ok(client.post(f"{W}/bulk", json=tag, headers=h))["changed"] == 1
    assert _ok(client.post(f"{W}/bulk", json=tag, headers=h))["changed"] == 0
    unknown = tag | {"ids": [contact["id"], str(uuid.uuid4())]}
    assert client.post(f"{W}/bulk", json=unknown, headers=h).status_code == 404
    assert client.post(f"{W}/bulk", json=tag, headers=caretaker).status_code == 403
    assert client.post(f"{W}/bulk", json=tag | {"tag": None}, headers=h).status_code == 422
    remove = tag | {"action": "contacts.remove_tag"}
    assert _ok(client.post(f"{W}/bulk", json=remove, headers=h))["changed"] == 1
    done = {"action": "maintenance.done", "ids": [item["id"]]}
    assert client.post(f"{W}/bulk", json=done, headers=other).status_code == 404
    assert _ok(client.post(f"{W}/bulk", json=done, headers=h))["changed"] == 1
    assert _ok(client.post(f"{W}/bulk", json=done, headers=h))["changed"] == 0
    assert _ok(client.get(f"{W}/dashboard", headers=h))["tiles"]["maintenance_due_30d"] == 0


def test_workspace_requires_login(client: TestClient) -> None:
    assert client.get(f"{W}/dashboard").status_code == 401


def test_ops_metrics_platform_admin_only(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "m9padmin"))
    body = _ok(client.get("/api/v1/platform/ops/metrics", headers=admin))
    assert body["metrics"]["tenants_active"] >= 2
    assert isinstance(body["alerts"], list)
    text = client.get("/api/v1/platform/ops/metrics?format=prometheus", headers=admin)
    assert text.status_code == 200
    assert "mhvp_webhook_deliveries_failed " in text.text
    tenant_admin = bearer(login(client, world, "m9admin"))
    assert client.get("/api/v1/platform/ops/metrics", headers=tenant_admin).status_code == 403
