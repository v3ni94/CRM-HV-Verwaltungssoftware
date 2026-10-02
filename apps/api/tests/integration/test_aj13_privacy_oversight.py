"""AJ13 (Welle 21): Auskunft mit Tickets und Kommunikation (GAI-506), Fristenüberwachung
(GAI-507), Einwilligungsübersicht (GAI-508), Art.-30-Detektoren (GAI-509), Vor-G1-Auswertung
(GAI-510). Mandantentrennung, Leserecht 403, Validierung 422."""

import asyncio
import uuid
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
SLUG_A = f"aj13a-{RUN}"
NOW = datetime(2026, 9, 1, tzinfo=UTC)


def _settings(database: Database, redis_url: str) -> Any:
    return _base_settings(database, redis_url, clamav_mode="warn", clamav_host="clamav-aj13")


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG_A, name=f"AJ13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aj13b-{RUN}", name=f"AJ13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("aj13admin", a, "tenant_admin"),
            ("aj13reader", a, "read_only"),
            ("aj13adminb", b, "tenant_admin"),
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
    return _settings(database, redis_url)


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
    admin = bearer(login(c, world, "aj13admin"))
    code = f"aj13read_{RUN}"
    role = c.post(
        "/api/v1/tenant/roles",
        json={"code": code, "name": "Datenschutz lesen", "permissions": ["privacy:read"]},
        headers=admin,
    )
    assert role.status_code in (201, 409), role.text
    members = _ok(c.get("/api/v1/tenant/members", headers=admin))
    member = next(m for m in members if m["user_id"] == str(world.users["aj13reader"]))
    put = c.put(
        f"/api/v1/tenant/members/{member['membership_id']}/roles",
        json={"role_codes": ["read_only", code]},
        headers=admin,
    )
    assert put.status_code == 204, put.text
    return bearer(login(c, world, "aj13reader"))


def _contact(c: TestClient, h: dict[str, str], name: str) -> str:
    body = {"kind": "person", "first_name": "A", "last_name": f"{name}{RUN}"}
    return str(_ok(c.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def test_consent_overview_counts_and_separation(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "aj13admin"))
    other = bearer(login(client, world, "aj13adminb"))
    reader = _reader(client, world)
    before = {
        i["kind"]: i for i in _ok(client.get(f"{P}/consent-overview", headers=admin))["items"]
    }
    cid = _contact(client, admin, "Einw")
    for kind in ("marketing", "marketing"):
        _ok(
            client.post(
                f"/api/v1/contacts/{cid}/consents",
                json={"kind": kind, "granted_at": NOW.isoformat(), "source": "Formular AJ13"},
                headers=admin,
            ),
            201,
        )
    consents = _ok(client.get(f"/api/v1/contacts/{cid}/consents", headers=admin))
    _ok(client.post(f"/api/v1/consents/{consents[0]['id']}/revoke", headers=admin))
    data = _ok(client.get(f"{P}/consent-overview", headers=reader))
    item = next(i for i in data["items"] if i["kind"] == "marketing")
    assert item["active"] == before["marketing"]["active"] + 1
    assert item["revoked"] == before["marketing"]["revoked"] + 1
    assert item["without_proof"] == before["marketing"]["without_proof"] + 1
    assert item["contacts_active"] == before["marketing"]["contacts_active"] + 1
    b = _ok(client.get(f"{P}/consent-overview", headers=other))
    assert all(i["active"] == 0 for i in b["items"])
    plain = bearer(login(client, world, "aj13reader"))
    assert client.get(f"{P}/consent-overview", params={"x": "1"}, headers=plain).status_code in (
        401,
        422,
    )


def test_deadlines_have_no_default_and_monitor(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "aj13admin"))
    other = bearer(login(client, world, "aj13adminb"))
    reader = _reader(client, world)
    got = _ok(client.get(f"{P}/request-deadlines", headers=other))
    assert got["configured"] is False
    assert got["erasure_days"] is None
    cid = _contact(client, admin, "Frist")
    received = local_today() - timedelta(days=20)
    _ok(
        client.post(
            f"{P}/erasure-requests",
            json={"contact_id": cid, "received_on": received.isoformat()},
            headers=admin,
        ),
        201,
    )
    mon = _ok(client.get(f"{P}/request-deadlines/monitor", headers=admin))
    mine = [i for i in mon["items"] if i["contact_id"] == cid]
    assert mine
    assert mine[0]["state"] == "unconfigured"
    assert mine[0]["due_on"] is None
    assert mon["access_requests_tracked"] is False
    assert (
        client.put(f"{P}/request-deadlines", json={"erasure_days": 30}, headers=reader).status_code
        == 403
    )
    assert (
        client.put(f"{P}/request-deadlines", json={"erasure_days": 0}, headers=admin).status_code
        == 422
    )
    assert client.put(f"{P}/request-deadlines", json={"x": 1}, headers=admin).status_code == 422
    _ok(
        client.put(
            f"{P}/request-deadlines", json={"erasure_days": 25, "warn_days": 7}, headers=admin
        )
    )
    mon = _ok(client.get(f"{P}/request-deadlines/monitor", headers=admin))
    item = next(i for i in mon["items"] if i["contact_id"] == cid)
    assert item["due_on"] == (received + timedelta(days=25)).isoformat()
    assert item["warn_on"] == (received + timedelta(days=18)).isoformat()
    assert item["state"] == "warn"
    _ok(client.put(f"{P}/request-deadlines", json={"erasure_days": 10}, headers=admin))
    item = next(
        i
        for i in _ok(client.get(f"{P}/request-deadlines/monitor", headers=admin))["items"]
        if i["contact_id"] == cid
    )
    assert item["state"] == "overdue"
    assert not [
        i
        for i in _ok(client.get(f"{P}/request-deadlines/monitor", headers=other))["items"]
        if i["contact_id"] == cid
    ]
    assert _ok(client.get(f"{P}/request-deadlines", headers=other))["configured"] is False


def test_detectors_and_readiness(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "aj13admin"))
    reader = _reader(client, world)
    keys = {s["key"] for s in _ok(client.get(f"{P}/register/config-sources", headers=admin))}
    assert "clamav:clamav-aj13" in keys
    ready = _ok(client.get(f"{P}/register/readiness", headers=reader))
    assert ready["complete"] is False
    clam = next(i for i in ready["items"] if i["key"] == "clamav:clamav-aj13")
    assert clam["entry_id"] is None
    _ok(
        client.post(
            f"{P}/register/config-sources/sync", json={"include_inactive": False}, headers=admin
        )
    )
    ready = _ok(client.get(f"{P}/register/readiness", headers=reader))
    clam = next(i for i in ready["items"] if i["key"] == "clamav:clamav-aj13")
    assert clam["entry_id"] is not None
    assert any("AVV" in t for t in clam["issues"])
    assert client.get(f"{P}/register/readiness", params={"x": 1}, headers=admin).status_code == 422


def test_access_export_sources_switch(client: TestClient, world: World, settings: Any) -> None:
    from mhvp.communication.models import Message
    from mhvp.contacts import access_export
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.tickets.models import Ticket

    admin = bearer(login(client, world, "aj13admin"))
    other = bearer(login(client, world, "aj13adminb"))
    cid = _contact(client, admin, "Auskunft")
    settings_path = "/api/v1/contact-access-export-settings"

    async def run(include: bool) -> dict[str, Any]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                if not include:
                    session.add_all(
                        [
                            Ticket(
                                tenant_id=world.tenant_a,
                                number=900000 + int(uuid.uuid4().int % 99999),
                                title="Heizung AJ13",
                                internal_description="intern geheim",
                                contact_id=uuid.UUID(cid),
                            ),
                            Message(
                                tenant_id=world.tenant_a,
                                direction="in",
                                subject="Anfrage AJ13",
                                body="Text",
                                to_addresses=["dritte@example.org"],
                                contact_id=uuid.UUID(cid),
                            ),
                        ]
                    )
                    await session.flush()
                options = await access_export.current_options(session)
                data = await access_export.build(
                    session, uuid.UUID(cid), datetime.now(UTC), options
                )
                assert data is not None
                return data
        finally:
            await engine.dispose()

    data = asyncio.run(run(False))
    assert "tickets" not in data
    assert data["withheld"]["tickets_count"] == 1
    assert data["withheld"]["communication_count"] == 1
    assert "tickets" in data["withheld"]["categories"]
    out = _ok(
        client.put(
            settings_path,
            json={"include_tickets": True, "include_communication": True},
            headers=admin,
        )
    )
    assert out["include_tickets"] is True
    assert out["include_documents"] is False
    assert _ok(client.get(settings_path, headers=other))["include_tickets"] is False
    data = asyncio.run(run(True))
    assert data["tickets"][0]["title"] == "Heizung AJ13"
    assert "intern geheim" not in str(data)
    assert data["communication"][0]["subject"] == "Anfrage AJ13"
    assert "dritte@example.org" not in str(data)
    # Omitted switches keep their value; reset explicitly.
    _ok(client.put(settings_path, json={}, headers=admin))
    assert _ok(client.get(settings_path, headers=admin))["include_tickets"] is True
    _ok(
        client.put(
            settings_path,
            json={"include_tickets": False, "include_communication": False},
            headers=admin,
        )
    )
