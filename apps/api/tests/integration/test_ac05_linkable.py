"""AC05: documents.LINKABLE knows the asset report (``asset_report``) and the operating cost
statement run (``statement``).

Expected values (hand derived): a document uploaded with a link to an existing asset report or
statement of tenant A is created (201) and carries exactly that link; the same link as tenant B
points at a row invisible by RLS and answers 404; an unknown entity type stays 422.
"""

import asyncio
import json
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
from tests.integration.test_m17_operating_costs import _rental_world
from tests.integration.test_m21_portal_owner import _ok
from tests.integration.test_m24_hoa import _hoa_ledger

pytestmark = pytest.mark.integration
S = "/api/v1/statements"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ac05a-{RUN}", name=f"AC05 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ac05b-{RUN}", name=f"AC05 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("ac05admin", a), ("ac05other", b)]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as c:
            yield c


def _upload(c: TestClient, h: dict[str, str], kind: str, entity_id: str) -> Any:
    return c.post(
        "/api/v1/documents",
        files={"file": ("nachweis.txt", b"Nachweis", "text/plain")},
        data={
            "links": json.dumps(
                [{"entity_type": kind, "entity_id": entity_id, "role": "attachment"}]
            )
        },
        headers=h,
    )


def test_asset_report_and_statement_are_linkable(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ac05admin"))
    ho = bearer(login(client, world, "ac05other"))
    w = _hoa_ledger(client, h, "951")
    report_id = _ok(
        client.post(
            "/api/v1/hoa/asset-reports",
            json={"ledger_id": w["ledger"], "as_of": "2025-12-31"},
            headers=h,
        ),
        201,
    )["id"]
    r = _rental_world(client, h, "952")
    run_id = _ok(
        client.post(
            S,
            json={"ledger_id": r["ledger"], "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )["id"]
    for kind, entity_id in (("asset_report", report_id), ("statement", run_id)):
        doc = _ok(_upload(client, h, kind, entity_id), 201)
        links = {(x["entity_type"], x["entity_id"]) for x in doc["links"]}
        assert links == {(kind, entity_id)}
        # tenant separation: the other tenant cannot see the target
        assert _upload(client, ho, kind, entity_id).status_code == 404
    assert _upload(client, h, "asset_reports", report_id).status_code == 422
