"""G1 opening checklist (M12-09): state derived from the platform, acceptance results per
annex D case with fixed counts, the G1 request through the existing four eyes flow that never
opens the gate, 403 without the rights, tenant separation."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.accounting.g1_opening import ALL_CASES, MANUAL_ITEMS
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
G = f"{A}/g1-opening"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"g1o-{RUN}", name=f"G1 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"g1f-{RUN}", name=f"Fremd3 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("g1admin", a, "tenant_admin"),
            ("g1reader", a, "read_only"),
            ("g1other", b, "tenant_admin"),
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


def test_g1_opening_checklist_acceptance_request_and_separation(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "g1admin"))
    r = bearer(login(client, world, "g1reader"))
    o = bearer(login(client, world, "g1other"))

    # Fixed values: 20 G1 cases plus 3 cross cutting cases, 5 manual items, nothing passed.
    state = _ok(client.get(G, headers=h))
    assert state["cases_total"] == 23 == len(ALL_CASES)
    assert state["manual_total"] == 5 == len(MANUAL_ITEMS)
    assert state["cases_passed"] == 0
    assert state["manual_passed"] == 0
    assert state["chart"]["released"] is False
    assert state["gate_open"] is False
    assert state["open_request"] is None
    assert state["can_request"] is True
    assert all(level == "L0" for level in state["automation_levels"].values())
    assert state["documents"]["abnahme-anhang-d"] == "docs/acceptance/abnahme-anhang-d.md"
    assert [c["item_key"] for c in state["cases"]][:3] == ["D04", "D05", "D07"]

    # Reading needs accounting:read (read_only has it), writing accounting:approve.
    _ok(client.get(G, headers=r))
    body = {"status": "passed", "confirmed_on": "2026-09-29", "confirmed_by_name": "T. Müller"}
    assert client.put(f"{G}/items/D04", json=body, headers=r).status_code == 403
    assert (
        client.post(f"{G}/request", json={"scope": "Testumfang G1"}, headers=r).status_code == 403
    )

    # A result without a name is refused; an unknown key is refused.
    assert client.put(f"{G}/items/D04", json={"status": "passed"}, headers=h).status_code == 422
    assert client.put(f"{G}/items/D99", json=body, headers=h).status_code == 422

    item = _ok(client.put(f"{G}/items/D04", json=body, headers=h))
    assert item["status"] == "passed"
    assert item["confirmed_on"] == "2026-09-29"
    assert item["title"] == "Interner Banktransfer"
    _ok(
        client.put(f"{G}/items/vat_review", json={**body, "note": "Schreiben liegt vor"}, headers=h)
    )
    _ok(client.put(f"{G}/items/D05", json={**body, "status": "failed"}, headers=h))
    state = _ok(client.get(G, headers=h))
    assert state["cases_passed"] == 1
    assert state["manual_passed"] == 1
    assert {
        c["item_key"]: c["status"] for c in state["cases"] if c["item_key"] in ("D04", "D05")
    } == {
        "D04": "passed",
        "D05": "failed",
    }
    # Back to open clears the date, idempotent second write keeps one row.
    _ok(client.put(f"{G}/items/D05", json={"status": "open"}, headers=h))
    assert _ok(client.get(G, headers=h))["cases_passed"] == 1

    # Chart state follows the release workflow (V8).
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    assert _ok(client.get(G, headers=h))["chart"] == {
        "released": False,
        "code": "a1",
        "version": 1,
        "released_at": None,
        "status": "draft",
    }
    _ok(client.post(f"{A}/templates/{template['id']}/release", json={}, headers=h))
    chart = _ok(client.get(G, headers=h))["chart"]
    assert chart["released"] is True
    assert chart["status"] == "released"
    assert chart["released_at"] is not None

    # Tenant separation: the other tenant sees no results and no chart of tenant A.
    other = _ok(client.get(G, headers=o))
    assert other["cases_passed"] == 0
    assert other["chart"]["released"] is False

    # Filing the request creates a regular G1 request; the gate stays closed (four eyes).
    filed = _ok(
        client.post(
            f"{G}/request",
            json={"scope": "Produktive Buchführung HVM, alle Rechtsträger", "comment": "Test"},
            headers=h,
        ),
        201,
    )
    assert filed["status"] == "requested"
    assert filed["four_eyes"] is True
    requests = _ok(client.get("/api/v1/tenant/release-gates/requests", headers=h))
    match = [x for x in requests if x["id"] == filed["id"]]
    assert match
    assert match[0]["gate"] == "G1"
    assert "Anhang D Fälle bestanden 1 von 23" in match[0]["evidence"]
    assert "Kontenrahmen a1 Version 1 freigegeben am" in match[0]["evidence"]
    assert "Kommentar: Test" in match[0]["evidence"]
    gates = {
        g["gate"]: g["open"] for g in _ok(client.get("/api/v1/tenant/release-gates", headers=h))
    }
    assert gates["G1"] is False
    state = _ok(client.get(G, headers=h))
    assert state["open_request"]["id"] == filed["id"]
    assert state["can_request"] is False
    # A second request while one is open is refused; the requester cannot approve (four eyes).
    dup = client.post(f"{G}/request", json={"scope": "Nochmals G1 beantragen"}, headers=h)
    assert dup.status_code == 409
    assert dup.json()["code"] == "MHVP-GATE-0003"
    assert not any(
        x["id"] == filed["id"]
        for x in _ok(client.get("/api/v1/tenant/release-gates/requests", headers=o))
    )
    assert _ok(client.get(G, headers=o))["open_request"] is None
