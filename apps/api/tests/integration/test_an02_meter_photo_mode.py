"""AN02 (GAJ-401, AM06-01): tenant switch ``meter_photo_mode`` (off, hint, required) of the
portal meter reading; default hint keeps the behaviour before migration 0451."""

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
from tests.integration.test_am06_portal_photo_inspection import _no, _tenancy, _upload
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an02a-{RUN}", name=f"AN02 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"an02b-{RUN}", name=f"AN02 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("an02admin", a, "tenant_admin"),
            ("an02adminb", b, "tenant_admin"),
            ("an02reader", a, "read_only"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def test_meter_photo_mode_switch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "an02admin", tenant_id=world.tenant_a))
    hb = bearer(login(client, world, "an02adminb", tenant_id=world.tenant_b))
    reader = bearer(login(client, world, "an02reader", tenant_id=world.tenant_a))
    # default hint, tenant B unaffected by changes of A
    assert _ok(client.get(f"{PA}/features", headers=h))["meter_photo_mode"] == "hint"
    assert (
        client.patch(f"{PA}/features", json={"meter_photo_mode": "x"}, headers=h).status_code == 422
    )
    assert (
        client.patch(f"{PA}/features", json={"meter_photo_mode": "off"}, headers=reader).status_code
        == 403
    )
    t = _tenancy(client, h, _no(51))
    ta = _portal_user(client, h, world, "an02tenant", _contact_of(client, h, t["party"]))
    meter = _ok(
        client.post(
            f"/api/v1/properties/{t['property']}/meters",
            json={
                "unit_id": t["unit"],
                "meter_type_code": "cold_water",
                "number": f"AN02-{RUN}",
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    body = {"meter_id": meter["id"], "value": "3.5", "read_at": "2026-09-30"}
    assert _ok(client.get(f"{P}/me", headers=ta))["features"]["meter_photo_mode"] == "hint"
    hint = _ok(client.post(f"{P}/meter-readings", json=body, headers=ta), 201)
    assert hint["photo_missing"] is True
    assert hint["note"]

    # required: without photo 422 with the problem code, nothing recorded; with photo accepted
    _ok(client.patch(f"{PA}/features", json={"meter_photo_mode": "required"}, headers=h))
    assert _ok(client.get(f"{PA}/features", headers=hb))["meter_photo_mode"] == "hint"
    before = len(_ok(client.get(f"{PA}/change-requests", headers=h)))
    res = client.post(f"{P}/meter-readings", json=body, headers=ta)
    assert res.status_code == 422
    assert res.json()["code"] == "MHVP-PORTAL-0003"
    assert len(_ok(client.get(f"{PA}/change-requests", headers=h))) == before
    photo = _upload(client, ta, "an02.jpg")
    ok = _ok(
        client.post(f"{P}/meter-readings", json={**body, "document_ids": [photo]}, headers=ta), 201
    )
    assert ok["photo_missing"] is False

    # off: no hint, no flag
    _ok(client.patch(f"{PA}/features", json={"meter_photo_mode": "off"}, headers=h))
    off = _ok(client.post(f"{P}/meter-readings", json=body, headers=ta), 201)
    assert off["photo_missing"] is False
    assert off["note"] is None
    queue = {r["id"]: r for r in _ok(client.get(f"{PA}/change-requests", headers=h))}
    assert queue[off["id"]]["payload"]["photo_missing"] is False
    assert queue[hint["id"]]["payload"]["photo_missing"] is True
    # other tenant does not see the proposals
    assert off["id"] not in {r["id"] for r in _ok(client.get(f"{PA}/change-requests", headers=hb))}
