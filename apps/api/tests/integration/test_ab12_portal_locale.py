"""AB12 (GA11-01): the portal language is stored at the portal account and returned with /me.

Expected values by hand: the PATCH stores "en", /me returns "en"; another account stays at null;
"fr" and an unknown field are rejected with 422; null clears the choice; a staff user without a
portal account gets 403."""

import asyncio
from collections.abc import Iterator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"


async def _world_ab12(settings: object) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)  # type: ignore[arg-type]
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ab12a-{RUN}", name=f"AB12 A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())  # type: ignore[attr-defined]
        uid = await services.create_user(
            factory, email=world.email("ab12admin"), display_name="ab12admin", password=PASSWORD
        )
        world.users["ab12admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world_ab12(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def test_portal_locale_is_stored_per_account(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ab12admin"))
    _, one = _party(client, ha, "AB12Person1")
    _, two = _party(client, ha, "AB12Person2")
    first = _portal_user(client, ha, world, "ab12one", str(one["id"]))
    second = _portal_user(client, ha, world, "ab12two", str(two["id"]))
    assert _ok(client.get(f"{P}/me", headers=first))["locale"] is None

    assert client.patch(f"{P}/me/locale", json={"locale": "en"}, headers=first).status_code == 204
    assert _ok(client.get(f"{P}/me", headers=first))["locale"] == "en"
    assert _ok(client.get(f"{P}/me", headers=second))["locale"] is None

    for bad in ({"locale": "fr"}, {"locale": "e" * 9}, {"locale": "en", "x": 1}):
        assert client.patch(f"{P}/me/locale", json=bad, headers=first).status_code == 422
    assert _ok(client.get(f"{P}/me", headers=first))["locale"] == "en"

    assert client.patch(f"{P}/me/locale", json={"locale": None}, headers=first).status_code == 204
    assert _ok(client.get(f"{P}/me", headers=first))["locale"] is None
    # Staff without a portal account and anonymous callers have no access.
    assert client.patch(f"{P}/me/locale", json={"locale": "de"}, headers=ha).status_code == 403
    assert client.patch(f"{P}/me/locale", json={"locale": "de"}).status_code in (401, 403)
