"""M2-02/S16-02 remainder of T14-01 (Welle 10, Y01): tenant wide Immoware24 file and full
imports are refused (403) for members with a property assignment, reconciliation reports are
filtered to the assigned properties, historical bank links follow the bank account and SEPA
mandate proposals of the portal administration follow the contract property. Administrators and
unassigned members keep the full view; tenant B sees nothing of tenant A."""

import asyncio
import uuid
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
from tests.integration.test_m11_banking import IBAN_A, IBAN_B
from tests.integration.test_q13_property_scope_etag import _assign, _estate, _ok
from tests.integration.test_r08_property_scope_domains import _bank

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"y01-{RUN}", name=f"Y01 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"y01b-{RUN}", name=f"Y01 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("y01admin", a, "tenant_admin"),
            ("y01admin_b", b, "tenant_admin"),
            ("y01clerk", a, "standard"),
            ("y01reader", a, "read_only"),
            ("y01reader_free", a, "read_only"),
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
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def test_property_assignment_y01(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "y01admin"))
    own = _estate(client, h, "151")
    foreign = _estate(client, h, "152")
    own.update(_bank(client, h, own["property"], IBAN_A, "151"))
    foreign.update(_bank(client, h, foreign["property"], IBAN_B, "152"))
    _assign(client, h, world.users["y01clerk"], [own["property"]])
    _assign(client, h, world.users["y01reader"], [own["property"]])
    c = bearer(login(client, world, "y01clerk"))
    r = bearer(login(client, world, "y01reader"))
    free = bearer(login(client, world, "y01reader_free"))

    # Immoware24 file and full imports without target property: admin only for assigned members.
    for path in (
        "/api/v1/imports/immoware24/fields",
        "/api/v1/imports/immoware24/overview",
        "/api/v1/imports/immoware24/vollimport/exporttypen",
        "/api/v1/imports/immoware24/vollimport",
    ):
        assert client.get(path, headers=h).status_code == 200, path
        assert client.get(path, headers=free).status_code == 200, path
        refused = client.get(path, headers=r)
        assert refused.status_code == 403, (path, refused.text)
    assert client.post("/api/v1/imports/immoware24/files", json={}, headers=c).status_code == 403

    # Reconciliation reports: list and unknown id keep their behaviour for restricted members.
    rec = "/api/v1/imports/reconciliation-reports"
    assert client.get(rec, headers=c).status_code == 200
    assert client.get(f"{rec}/{uuid.uuid4()}", headers=c).status_code == 404
    assert client.get(f"{rec}/kein-uuid", headers=c).status_code == 422

    # Historical bank links: filtered list, candidates of a foreign transaction 404.
    links = "/api/v1/imports/immoware24/history/bank-links"
    assert client.get(links, headers=c).status_code == 200
    assert client.get(f"{links}/{foreign['tx']}/candidates", headers=c).status_code == 404

    # SEPA mandate proposals of the portal administration.
    sp = "/api/v1/portal-admin/sepa-mandate-proposals"
    assert _ok(client.get(sp, headers=c)) == []
    decided = client.post(f"{sp}/{uuid.uuid4()}/decide", json={"accept": False}, headers=c)
    assert decided.status_code == 404
    assert client.post(f"{sp}/{uuid.uuid4()}/decide", json={}, headers=c).status_code == 422
    assert (
        client.post(f"{sp}/{uuid.uuid4()}/decide", json={"accept": False}, headers=r).status_code
        == 403
    )

    # Tenant B: no access to tenant A data.
    hb = bearer(login(client, world, "y01admin_b"))
    assert client.get(f"{links}/{own['tx']}/candidates", headers=hb).status_code == 404
