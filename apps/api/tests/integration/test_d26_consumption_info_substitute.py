"""D26 (SD-01): the consumption information is due although the portal is not in use. The
substitute process works without any portal account: the CRM generates the month, shows the
frozen snapshot for print or e-mail, lists the units still undelivered and records the
delivery with channel, day and evidence. No reference to a later phase replaces it."""

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
from tests.integration.test_h03_consumption_info import _owner, _seed_metering, _tenancy
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"d26a-{RUN}", name=f"D26 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"d26b-{RUN}", name=f"D26 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("d26admin", a, "tenant_admin"),
            ("d26read", a, "read_only"),
            ("d26other", b, "tenant_admin"),
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


def test_d26_substitute_process_without_portal(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    c = client
    h = bearer(login(c, world, "d26admin"))
    pid = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "926", "name": "Ersatzhaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )["id"]
    _owner(c, h, pid)
    building = _ok(
        c.post(f"/api/v1/properties/{pid}/buildings", json={"name": "Haus"}, headers=h), 201
    )["id"]
    unit = _ok(
        c.post(
            f"/api/v1/properties/{pid}/units",
            json={"building_id": building, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    party, _ = _party(c, h, "MieterOhnePortal")
    _tenancy(c, h, unit, party, "2024-01-01")
    asyncio.run(_seed_metering(_settings(database, redis_url), world.tenant_a, pid, unit))
    base = f"/api/v1/properties/{pid}/consumption-info"
    _ok(c.patch("/api/v1/tenant/settings", json={"consumption_info_enabled": True}, headers=h))
    _ok(c.put(f"{base}/settings", json={"enabled": True}, headers=h))
    _ok(c.post(f"{base}/run", json={"month": "2025-08-01"}, headers=h))

    listing = _ok(c.get(base, headers=h))
    (month,) = listing["months"]
    assert month["undelivered"] == 1  # no portal account, no notification: still owed
    (row,) = listing["rows"]
    assert row["delivered_on"] is None
    detail = _ok(c.get(f"{base}/{row['id']}", headers=h))
    assert "Verbrauchsinformation 08.2025" in detail["snapshot_html"]  # printable version

    url = f"{base}/{row['id']}/delivery"
    delivery = {
        "channel": "post",
        "delivered_on": "2025-09-05",
        "evidence": "Brief an Mieter, Postausgangsbuch Nr. 17",
    }
    assert c.put(url, json=delivery | {"channel": "portal"}, headers=h).status_code == 422
    assert c.put(url, json=delivery | {"evidence": ""}, headers=h).status_code == 422
    assert c.put(url, json=delivery | {"delivered_on": "2025-07-31"}, headers=h).status_code == 422
    assert c.put(url, json=delivery, headers=bearer(login(c, world, "d26read"))).status_code == 403
    other = bearer(login(c, world, "d26other"))
    assert c.put(url, json=delivery, headers=other).status_code == 404
    assert c.get(f"{base}/{row['id']}", headers=other).status_code == 404
    stored = _ok(c.put(url, json=delivery, headers=h))
    assert (stored["delivery_channel"], stored["delivered_on"]) == ("post", "2025-09-05")
    assert _ok(c.get(base, headers=h))["months"][0]["undelivered"] == 0
