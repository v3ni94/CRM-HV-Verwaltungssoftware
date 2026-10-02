"""AI08 (GAH-209, GAH-213, GAH-208): as_of on validity lists, OpenAPI declaration of the
generic list parameters, upper bound of /postal/jobs."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _ok, _party, _payment, _property, _unit

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ai08-{RUN}", name=f"AI08 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ai08b-{RUN}", name=f"AI08 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ai08admin", a, "tenant_admin"),
            ("ai08admin_b", b, "tenant_admin"),
            ("ai08reader", a, "read_only"),
        ):
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


def _contract(client: TestClient, h: dict[str, str], number: str) -> tuple[str, dict[str, Any]]:
    prop = _property(client, h, number, "rental")
    unit = _unit(client, h, prop["id"], "01")
    tenant, _ = _party(client, h, "Mieter")
    owner, _ = _party(client, h, "Eigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2026-01-01",
            },
            headers=h,
        )
    )
    return str(contract["id"]), prop


def test_payments_as_of(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ai08admin"))
    cid, _ = _contract(client, h, "808")
    pay = f"/api/v1/contracts/{cid}/payments"
    _ok(client.post(pay, json=_payment("800.00", "800.00", "2026-01-01"), headers=h))
    _ok(client.post(pay, json=_payment("850.00", "850.00", "2027-01-01"), headers=h))
    everything = _ok(client.get(pay, headers=h), 200)
    assert len(everything) == 2

    def gross(day: str) -> list[str]:
        return [p["gross"] for p in _ok(client.get(pay, params={"as_of": day}, headers=h), 200)]

    assert gross("2025-06-01") == []
    assert gross("2026-06-01") == ["800.00"]
    assert gross("2027-02-01") == ["850.00"]
    assert client.get(pay, params={"as_of": "kein-datum"}, headers=h).status_code == 422
    assert client.get(pay, params={"unknown": "1"}, headers=h).status_code == 422
    other = bearer(login(client, world, "ai08admin_b"))
    assert client.get(pay, params={"as_of": "2026-06-01"}, headers=other).status_code == 404
    reader = bearer(login(client, world, "ai08reader"))
    assert client.get(pay, params={"as_of": "2026-06-01"}, headers=reader).status_code == 200


def test_other_lists_accept_as_of(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ai08admin"))
    cid, prop = _contract(client, h, "809")
    _, contact = _party(client, h, "Partei")
    for url in (
        f"/api/v1/contracts/{cid}/allocation-values",
        f"/api/v1/properties/{prop['id']}/allocation-keys",
        "/api/v1/sepa-mandates",
    ):
        ok = client.get(url, params={"as_of": "2026-06-01"}, headers=h)
        assert ok.status_code == 200, (url, ok.text)
        bad = client.get(url, params={"as_of": "morgen"}, headers=h)
        assert bad.status_code == 422, (url, bad.text)
    # Party has no validity columns (schema need, see open_points): as_of stays 422.
    rejected = client.get(
        "/api/v1/parties", params={"contact_id": contact["id"], "as_of": "2026-06-01"}, headers=h
    )
    assert rejected.status_code == 422
    assert "as_of" in rejected.text  # GAI-607: the refusal names the parameter
    # allocation keys: only keys with a unit value in force on the day
    keys = f"/api/v1/properties/{prop['id']}/allocation-keys"
    assert _ok(client.get(keys, params={"as_of": "2026-06-01"}, headers=h), 200) == []


def test_postal_jobs_limit_bound(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ai08admin"))
    assert client.get("/api/v1/postal/jobs", params={"limit": 500}, headers=h).status_code == 200
    assert client.get("/api/v1/postal/jobs", params={"limit": 501}, headers=h).status_code == 422
    assert client.get("/api/v1/postal/jobs", params={"limit": 0}, headers=h).status_code == 422


def test_openapi_declares_generic_list_parameters(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    declared = {p["name"] for p in spec["paths"]["/api/v1/tickets"]["get"].get("parameters", [])}
    assert {"sort", "fields"} <= declared
    assert any(n.startswith("filter[") for n in declared)
    assert "as_of" in {
        p["name"]
        for p in spec["paths"]["/api/v1/contracts/{contract_id}/payments"]["get"]["parameters"]
    }
    total = sum(
        1
        for item in spec["paths"].values()
        for op in [item.get("get")]
        if op and any(p["name"] == "fields" for p in op.get("parameters", []))
    )
    assert total >= 10
