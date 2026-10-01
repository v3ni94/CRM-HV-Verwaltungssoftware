"""Review W79 (01.10.2026, docs/reviews/REVIEW-W79-2026-10-01.md): security findings in the code
of waves 7 to 9.

Y04-1 (A37, M18-05): a tax advisor holds ``accounting:read`` and so reaches the WEG lists of the
``/hoa`` routers. The lists filtered by ``legal_entity_id`` answered for every community of the
tenant; the router guard now answers 404 outside ``Membership.legal_entity_ids``, also for the
id of a WEG record (``resolution_id``) of another community.
"""

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
from tests.integration.test_m21_board_portal import _hoa

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"y4-{RUN}", name=f"Review {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"y4b-{RUN}", name=f"Review B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role in (("y4admin", "tenant_admin"), ("y4tax", "tax_advisor")):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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


def test_tax_advisor_sees_weg_lists_only_of_assigned_community(
    client: TestClient, world: World
) -> None:
    from tests.integration.test_m18_tax_advisor_scope import _membership_id

    h = bearer(login(client, world, "y4admin"))
    hoa_a, _, _ = _hoa(client, h, "941")
    hoa_b, _, _ = _hoa(client, h, "942")
    resolution = client.post(
        f"{H}/resolutions",
        json={
            "legal_entity_id": hoa_b,
            "decided_on": "2025-05-01",
            "subject": "Fassadenanstrich",
            "wording": "Die Gemeinschaft beschließt den Anstrich.",
            "status": "positive",
        },
        headers=h,
    )
    assert resolution.status_code == 201, resolution.text
    member = _membership_id(client, h, world.users["y4tax"])
    scoped = client.put(
        f"/api/v1/tenant/members/{member}/legal-entities",
        json={"legal_entity_ids": [hoa_a]},
        headers=h,
    )
    assert scoped.status_code == 204, scoped.text
    tax = bearer(login(client, world, "y4tax"))
    for path in (
        "resolutions",
        "meetings",
        "special-levies",
        "loans",
        "measures",
        "insurance-claims",
    ):
        own = client.get(f"{H}/{path}", params={"legal_entity_id": hoa_a}, headers=tax)
        assert own.status_code == 200, (path, own.text)
        foreign = client.get(f"{H}/{path}", params={"legal_entity_id": hoa_b}, headers=tax)
        assert foreign.status_code == 404, (path, foreign.text)
    rid = resolution.json()["id"]
    assert client.get(f"{H}/resolutions", params={"legal_entity_id": hoa_b}, headers=h).json()
    by_id = client.patch(f"{H}/resolutions/{rid}", json={"status": "final"}, headers=tax)
    assert by_id.status_code in (403, 404), by_id.text
    # The unrestricted administrator keeps the full view.
    assert (
        client.get(f"{H}/meetings", params={"legal_entity_id": hoa_b}, headers=h).status_code == 200
    )
