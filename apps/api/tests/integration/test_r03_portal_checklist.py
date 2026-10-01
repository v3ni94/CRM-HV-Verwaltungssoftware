"""R03: takeover checklist in the owner portal (read only): scope of the own properties, no
internal notes, residents get 403, owners of another tenant see nothing."""

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
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user
from tests.integration.test_q10_portal_w3 import _owner_setup, _tenant_setup

pytestmark = pytest.mark.integration
P = "/api/v1/portal"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r03a-{RUN}", name=f"R03 A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("r03admin"), display_name="r03admin", password=PASSWORD
        )
        world.users["r03admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def test_owner_sees_takeover_checklist_read_only(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "r03admin"))
    _contract, meta = _tenant_setup(client, ha, world, "951")
    resident = _portal_user(client, ha, world, "r03res", _contact_of(client, ha, meta["party"]))
    owner_meta = _owner_setup(client, ha, "952")
    other_meta = _owner_setup(client, ha, "953")
    owner = _portal_user(client, ha, world, "r03own", _contact_of(client, ha, owner_meta["party"]))

    assert client.get(f"{P}/owner/takeover-checklist", headers=resident).status_code == 403
    assert _ok(client.get(f"{P}/owner/takeover-checklist", headers=owner))["items"] == []

    listed = _ok(client.get("/api/v1/properties", params={"limit": 200}, headers=ha), 200)
    rows = listed["items"] if isinstance(listed, dict) else listed
    props = {p["number"]: p["id"] for p in rows}
    for number in ("952", "953"):
        url = f"/api/v1/properties/{props[number]}/takeover-checklist"
        _ok(client.post(url, headers=ha), 200)
        _ok(
            client.patch(
                f"{url}/insurance",
                json={"status": "requested", "note": "intern: Makler nachfassen"},
                headers=ha,
            ),
            200,
        )
    _ok(
        client.patch(
            f"/api/v1/properties/{props['952']}/takeover-checklist/meters",
            json={"status": "received"},
            headers=ha,
        ),
        200,
    )
    result = _ok(client.get(f"{P}/owner/takeover-checklist", headers=owner))
    assert [i["property_id"] for i in result["items"]] == [props["952"]]
    item = result["items"][0]
    assert item["open_count"] == 6
    assert item["complete"] is False
    assert len(item["points"]) == 7
    by_category = {p["category"]: p for p in item["points"]}
    assert by_category["meters"]["status_label"] == "erhalten"
    assert by_category["insurance"]["label"] == "Versicherungen"
    assert "intern" not in str(result)
    assert set(by_category["insurance"]) == {
        "category",
        "label",
        "status",
        "status_label",
        "due_date",
    }
    assert other_meta["unit"] not in str(result)
    # read only: the portal offers no write on the checklist
    assert client.post(f"{P}/owner/takeover-checklist", headers=owner).status_code in (404, 405)
