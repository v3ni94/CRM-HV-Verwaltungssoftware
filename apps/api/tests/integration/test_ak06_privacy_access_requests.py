"""AK06 (Welle 22): Eingangsdatensatz für Auskunftsanträge mit Fristenüberwachung und
Fristenregister (GAI-507), Auskunft um Portalkonto, Zahlungs- und Vertragsdaten hinter
Mandantenschaltern (GAI-506). Mandantentrennung, Leserecht 403, Validierung 422."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.clock import local_today
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as _base_settings

pytestmark = pytest.mark.integration
P = "/api/v1/privacy"
AR = f"{P}/access-requests"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ak06a-{RUN}", name=f"AK06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ak06b-{RUN}", name=f"AK06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ak06admin", a, "tenant_admin"),
            ("ak06reader", a, "read_only"),
            ("ak06adminb", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
    finally:
        await engine.dispose()
    return world


@pytest.fixture(scope="module")
def settings(database: Database, redis_url: str) -> Any:
    return _base_settings(database, redis_url)


@pytest.fixture(scope="module")
def world(settings: Any) -> World:
    return asyncio.run(_world(settings))


@pytest.fixture
def client(settings: Any) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _reader(c: TestClient, world: World) -> dict[str, str]:
    admin = bearer(login(c, world, "ak06admin"))
    code = f"ak06read_{RUN}"
    role = c.post(
        "/api/v1/tenant/roles",
        json={"code": code, "name": "Datenschutz lesen", "permissions": ["privacy:read"]},
        headers=admin,
    )
    assert role.status_code in (201, 409), role.text
    members = _ok(c.get("/api/v1/tenant/members", headers=admin))
    member = next(m for m in members if m["user_id"] == str(world.users["ak06reader"]))
    put = c.put(
        f"/api/v1/tenant/members/{member['membership_id']}/roles",
        json={"role_codes": ["read_only", code]},
        headers=admin,
    )
    assert put.status_code == 204, put.text
    return bearer(login(c, world, "ak06reader"))


def _contact(c: TestClient, h: dict[str, str], name: str) -> str:
    body = {"kind": "person", "first_name": "A", "last_name": f"{name}{RUN}"}
    return str(_ok(c.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def _register(c: TestClient, h: dict[str, str], rid: str) -> list[dict[str, Any]]:
    rows = _ok(
        c.get(
            "/api/v1/workspace/deadlines",
            params={"kind": "privacy_access_request", "status": "all"},
            headers=h,
        )
    )
    return [r for r in rows if r["source_id"] == rid]


def test_access_request_intake_monitor_and_register(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "ak06admin"))
    other = bearer(login(client, world, "ak06adminb"))
    reader = _reader(client, world)
    cid = _contact(client, admin, "Auskunft")
    received = local_today() - timedelta(days=20)
    body = {"contact_id": cid, "received_on": received.isoformat(), "channel": "letter"}
    # Validation, permission, separation.
    assert client.post(AR, json={**body, "channel": "fax"}, headers=admin).status_code == 422
    assert client.post(AR, json={**body, "x": 1}, headers=admin).status_code == 422
    future = (local_today() + timedelta(days=1)).isoformat()
    assert client.post(AR, json={**body, "received_on": future}, headers=admin).status_code == 422
    assert client.post(AR, json=body, headers=reader).status_code == 403
    assert client.post(AR, json=body, headers=other).status_code == 404
    created = _ok(client.post(AR, json=body, headers=admin), 201)
    rid = created["id"]
    # No default period (AJ13-01): no due date, no register entry.
    assert created["state"] == "unconfigured"
    assert created["due_on"] is None
    assert _register(client, admin, rid) == []
    assert client.get(f"{AR}/{rid}", headers=other).status_code == 404
    assert _ok(client.get(f"{AR}/{rid}", headers=reader))["status"] == "received"
    assert client.get(AR, params={"x": 1}, headers=admin).status_code == 422
    assert all(r["id"] != rid for r in _ok(client.get(AR, headers=other)))
    # Configured period: monitor and register.
    _ok(
        client.put(
            f"{P}/request-deadlines", json={"access_days": 25, "warn_days": 7}, headers=admin
        )
    )
    got = _ok(client.get(f"{AR}/{rid}", headers=admin))
    assert got["due_on"] == (received + timedelta(days=25)).isoformat()
    assert got["state"] == "warn"
    mon = _ok(client.get(f"{P}/request-deadlines/monitor", headers=admin))
    item = next(i for i in mon["items"] if i["request_id"] == rid)
    assert item["kind"] == "access"
    assert item["state"] == "warn"
    status_path = f"{AR}/{rid}/status"
    _ok(client.post(status_path, json={"status": "in_progress"}, headers=admin))
    reg = _register(client, admin, rid)
    assert [r["status"] for r in reg] == ["open"]
    assert reg[0]["due_on"] == (received + timedelta(days=25)).isoformat()
    assert client.post(status_path, json={"status": "answered"}, headers=reader).status_code == 403
    assert client.post(status_path, json={"status": "answered"}, headers=other).status_code == 404
    assert client.post(status_path, json={"status": "received"}, headers=admin).status_code == 422
    done = _ok(
        client.post(status_path, json={"status": "answered", "note": "Brief"}, headers=admin)
    )
    assert done["state"] == "closed"
    assert done["closed_on"] == local_today().isoformat()
    assert [r["status"] for r in _register(client, admin, rid)] == ["done"]
    # Closed requests cannot be reopened.
    assert (
        client.post(status_path, json={"status": "in_progress"}, headers=admin).status_code != 200
    )
    assert all(
        r["id"] != rid for r in _ok(client.get(AR, params={"open_only": True}, headers=admin))
    )
    _ok(client.put(f"{P}/request-deadlines", json={}, headers=admin))


def test_access_export_account_payment_contract_switches(
    client: TestClient, world: World, settings: Any
) -> None:
    import uuid

    from mhvp.contacts import access_export
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    admin = bearer(login(client, world, "ak06admin"))
    other = bearer(login(client, world, "ak06adminb"))
    cid = _contact(client, admin, "Export")
    path = "/api/v1/contact-access-export-settings"

    async def run() -> dict[str, Any]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                options = await access_export.current_options(session)
                data = await access_export.build(
                    session, uuid.UUID(cid), datetime.now(UTC), options
                )
                assert data is not None
                return data
        finally:
            await engine.dispose()

    out = _ok(client.get(path, headers=admin))
    assert out["include_portal_account"] is False
    assert out["include_payments"] is False
    assert out["include_contracts"] is False
    data = asyncio.run(run())
    for key in ("portal_account", "payments", "contracts"):
        assert key not in data
    assert data["withheld"]["portal_account_count"] == 0
    assert data["withheld"]["payments_count"] == 0
    assert data["withheld"]["contracts_count"] == 0
    flags = {"include_portal_account": True, "include_payments": True, "include_contracts": True}
    out = _ok(client.put(path, json=flags, headers=admin))
    assert out["include_portal_account"] is True
    assert _ok(client.get(path, headers=other))["include_payments"] is False
    data = asyncio.run(run())
    assert data["portal_account"] is None
    assert data["payments"] == []
    assert data["contracts"] == []
    _ok(client.put(path, json=dict.fromkeys(flags, False), headers=admin))
