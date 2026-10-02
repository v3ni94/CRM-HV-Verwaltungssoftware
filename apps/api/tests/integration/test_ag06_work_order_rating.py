"""AG06 (GAF-35, 14 Dienstleister, AE30-02): rating of a completed work order by the
management and by the affected resident, one per party, display only per tenant switch."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a55_a58_portal_attachments import _rental, _tenancy
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
FEATURES = "/api/v1/portal-admin/features"
USERS = (("ag06admin", "a", "tenant_admin"), ("ag06reader", "a", "read_only"))


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag06-a-{RUN}", name=f"AG06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag06-b-{RUN}", name=f"AG06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        members = (
            ("ag06admin", a, "tenant_admin"),
            ("ag06reader", a, "read_only"),
            ("ag06adminb", b, "tenant_admin"),
        )
        for name, tenant, role in members:
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _setup(c: TestClient, world: World, number: str) -> dict[str, Any]:
    h = bearer(login(c, world, "ag06admin", tenant_id=world.tenant_a))
    prop_id, _ = _rental(c, h, number)
    tenancy = _tenancy(c, h, prop_id, "A")
    other = _tenancy(c, h, prop_id, "B")
    resident = _portal_user(c, h, world, f"ag06res{number}", _contact_of(c, h, tenancy["party_id"]))
    stranger = _portal_user(c, h, world, f"ag06str{number}", _contact_of(c, h, other["party_id"]))
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Bewertet {number} {RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    pv = _portal_user(c, h, world, f"ag06prov{number}", provider)
    ticket = _ok(
        c.post(
            f"{P}/tickets",
            json={"title": "Rohr", "description": "Tropft", "unit_id": tenancy["unit_id"]},
            headers=resident,
        ),
        201,
    )
    oid = _ok(
        c.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": prop_id,
                "provider_contact_id": provider,
                "description": "Rohr dichten",
            },
            headers=h,
        ),
        201,
    )["id"]
    return {"h": h, "res": resident, "str": stranger, "pv": pv, "oid": oid}


def _finish(c: TestClient, s: dict[str, Any]) -> None:
    oid, h = s["oid"], s["h"]
    for status in ("requested", "approved"):
        _ok(c.post(f"/api/v1/work-orders/{oid}/steps", json={"status": status}, headers=h))
    _ok(
        c.post(
            f"/api/v1/work-orders/{oid}/steps",
            json={"status": "scheduled", "scheduled_at": "2026-10-06T14:00:00Z"},
            headers=h,
        )
    )
    _ok(c.post(f"/api/v1/work-orders/{oid}/steps", json={"status": "in_progress"}, headers=h))
    _ok(
        c.post(
            f"/api/v1/work-orders/{oid}/steps",
            json={"status": "done", "completion_report": "erledigt"},
            headers=h,
        )
    )


def test_rating_only_after_completion_one_per_party(client: TestClient, world: World) -> None:
    s = _setup(client, world, "861")
    oid, h = s["oid"], s["h"]
    body = {"stars": 4, "comment": "pünktlich"}
    # Not completed yet: 409 for both parties.
    assert client.post(f"/api/v1/work-orders/{oid}/rating", json=body, headers=h).status_code == 409
    assert (
        client.post(f"{P}/work-orders/{oid}/rating", json=body, headers=s["res"]).status_code == 409
    )
    state = _ok(client.get(f"{P}/work-orders/{oid}/rating", headers=s["res"]))
    assert state["can_rate"] is False
    _finish(client, s)
    # Validation.
    for bad in ({"stars": 0}, {"stars": 6}, {"stars": 3, "x": 1}):
        assert (
            client.post(f"/api/v1/work-orders/{oid}/rating", json=bad, headers=h).status_code == 422
        )
    staff = _ok(client.post(f"/api/v1/work-orders/{oid}/rating", json=body, headers=h), 201)
    assert staff["party"] == "staff"
    assert staff["stars"] == 4
    assert client.post(f"/api/v1/work-orders/{oid}/rating", json=body, headers=h).status_code == 409
    own = _ok(
        client.post(f"{P}/work-orders/{oid}/rating", json={"stars": 5}, headers=s["res"]), 201
    )
    assert own["stars"] == 5
    assert (
        client.post(f"{P}/work-orders/{oid}/rating", json=body, headers=s["res"]).status_code == 409
    )
    state = _ok(client.get(f"{P}/work-orders/{oid}/rating", headers=s["res"]))
    assert state["can_rate"] is False
    assert state["own"]["stars"] == 5


def test_rating_permissions_and_tenant_separation(client: TestClient, world: World) -> None:
    s = _setup(client, world, "862")
    _finish(client, s)
    oid = s["oid"]
    reader = bearer(login(client, world, "ag06reader", tenant_id=world.tenant_a))
    other_tenant = bearer(login(client, world, "ag06adminb", tenant_id=world.tenant_b))
    body = {"stars": 3}
    assert (
        client.post(f"/api/v1/work-orders/{oid}/rating", json=body, headers=reader).status_code
        == 403
    )
    assert client.get(f"/api/v1/work-orders/{oid}/rating", headers=reader).status_code == 200
    assert (
        client.post(
            f"/api/v1/work-orders/{oid}/rating", json=body, headers=other_tenant
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/work-orders/{oid}/rating", headers=other_tenant).status_code == 404
    # Provider and unrelated resident get not found in the portal.
    for key in ("pv", "str"):
        assert (
            client.post(f"{P}/work-orders/{oid}/rating", json=body, headers=s[key]).status_code
            == 404
        )
        assert client.get(f"{P}/work-orders/{oid}/rating", headers=s[key]).status_code == 404


def test_display_follows_switch(client: TestClient, world: World) -> None:
    s = _setup(client, world, "863")
    _finish(client, s)
    oid, h = s["oid"], s["h"]
    _ok(
        client.post(
            f"/api/v1/work-orders/{oid}/rating", json={"stars": 4, "comment": "gut"}, headers=h
        ),
        201,
    )
    _ok(
        client.post(
            f"{P}/work-orders/{oid}/rating", json={"stars": 2, "comment": "spät"}, headers=s["res"]
        ),
        201,
    )
    assert _ok(client.get(FEATURES, headers=h))["provider_rating_display"] == "off"
    off = _ok(client.get(f"/api/v1/work-orders/{oid}/rating", headers=h))
    assert off["mode"] == "off"
    assert off["ratings"] == []
    assert off["staff_rated"] is True
    assert (
        _ok(client.get(f"{P}/work-orders/{oid}/rating", headers=s["res"]))["provider_summary"]
        is None
    )
    _ok(client.patch(FEATURES, json={"provider_rating_display": "staff"}, headers=h))
    staff = _ok(client.get(f"/api/v1/work-orders/{oid}/rating", headers=h))
    assert {r["party"] for r in staff["ratings"]} == {"staff", "resident"}
    assert (
        _ok(client.get(f"{P}/work-orders/{oid}/rating", headers=s["res"]))["provider_summary"]
        is None
    )
    overview = _ok(client.get("/api/v1/portal-admin/provider-ratings", headers=h))
    assert sum(p["rated_count"] for p in overview["providers"]) >= 2
    _ok(client.patch(FEATURES, json={"provider_rating_display": "all"}, headers=h))
    summary = _ok(client.get(f"{P}/work-orders/{oid}/rating", headers=s["res"]))["provider_summary"]
    assert summary == {"rated_count": 2, "average": "3.0"}
    # The provider never gets a rating view; invalid mode stays rejected.
    assert client.get(f"{P}/work-orders/{oid}/rating", headers=s["pv"]).status_code == 404
    assert (
        client.patch(FEATURES, json={"provider_rating_display": "public"}, headers=h).status_code
        == 422
    )
    _ok(client.patch(FEATURES, json={"provider_rating_display": "off"}, headers=h))
