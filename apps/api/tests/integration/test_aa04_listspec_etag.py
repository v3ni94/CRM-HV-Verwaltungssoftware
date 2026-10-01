"""GA04-05 (filter[feld], sort, fields, as_of via ListSpec on further list routers, unknown
parameters 422) and GA04-06 (ETag/If-Match on resolutions and messages): tenant separation,
403 without write permission, 412 on a stale If-Match, 422 on invalid list parameters."""

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
from tests.integration.test_m5_contracts import _property
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration

# Converted list routers (inventory of GA04-05 in this package).
LISTS = [
    "/api/v1/banking/transactions",
    "/api/v1/accounting/dunning-runs",
    "/api/v1/mail/messages",
]


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa04-{RUN}", name=f"AA04 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa04b-{RUN}", name=f"AA04 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("aa04admin", a, "tenant_admin"),
            ("aa04admin_b", b, "tenant_admin"),
            ("aa04clerk", a, "standard"),
            ("aa04reader", a, "read_only"),
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


def _h(client: TestClient, world: World, name: str, tenant: uuid.UUID) -> dict[str, str]:
    return bearer(login(client, world, name, tenant))


def _resolution(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    prop = _property(client, h, str(400 + uuid.uuid4().int % 99), "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    created = client.post(
        "/api/v1/hoa/resolutions",
        json={
            "legal_entity_id": hoa,
            "decided_on": "2026-05-01",
            "subject": "Dachsanierung",
            "wording": "Die Gemeinschaft beschließt die Sanierung.",
            "status": "positive",
        },
        headers=h,
    )
    assert created.status_code == 201, created.text
    return hoa, str(created.json()["id"])


@pytest.mark.parametrize("path", LISTS)
def test_lists_reject_unknown_parameters(
    client: TestClient,
    world: World,
    path: str,
) -> None:
    h = _h(client, world, "aa04admin", world.tenant_a)
    assert client.get(path, params={"filter[status]": "x" * 3}, headers=h).status_code in (
        200,
        422,
    )
    for bad in ({"filter[nope]": "1"}, {"sort": "nope"}, {"bogus": "1"}, {"as_of": "2026-01-01"}):
        r = client.get(path, params=bad, headers=h)
        assert r.status_code == 422, (path, bad, r.text)


def test_bank_transactions_filter_sort_fields(client: TestClient, world: World) -> None:
    h = _h(client, world, "aa04admin", world.tenant_a)
    r = client.get(
        "/api/v1/banking/transactions",
        params={"filter[status]": "new", "sort": "-amount", "fields": "amount"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert client.get(
        "/api/v1/banking/transactions", params={"fields": "nope"}, headers=h
    ).status_code in (200, 422)
    bad_value = client.get(
        "/api/v1/banking/transactions",
        params={"filter[booking_date]": "kein-datum"},
        headers=h,
    )
    assert bad_value.status_code == 422


def test_resolution_list_and_etag(client: TestClient, world: World) -> None:
    h = _h(client, world, "aa04admin", world.tenant_a)
    hoa, rid = _resolution(client, h)
    base = {"legal_entity_id": hoa}
    rows = client.get("/api/v1/hoa/resolutions", params=base, headers=h).json()
    assert [r["id"] for r in rows] == [rid]
    sparse = client.get(
        "/api/v1/hoa/resolutions", params={**base, "fields": "number"}, headers=h
    ).json()
    assert set(sparse[0]) == {"id", "number"}
    none = client.get(
        "/api/v1/hoa/resolutions", params={**base, "filter[status]": "void"}, headers=h
    ).json()
    assert none == []
    for bad in ({"filter[wording]": "x"}, {"sort": "subject"}, {"as_of": "2026-01-01"}):
        assert (
            client.get("/api/v1/hoa/resolutions", params={**base, **bad}, headers=h).status_code
            == 422
        )

    # GA04-06: stale If-Match 412, current ETag accepted, new ETag returned
    stale = client.patch(
        f"/api/v1/hoa/resolutions/{rid}",
        json={"status": "final"},
        headers={**h, "If-Match": '"t1"'},
    )
    assert stale.status_code == 412, stale.text
    first = client.patch(f"/api/v1/hoa/resolutions/{rid}", json={"status": "final"}, headers=h)
    assert first.status_code == 200, first.text
    etag = first.headers["ETag"]
    second = client.patch(
        f"/api/v1/hoa/resolutions/{rid}",
        json={"status": "legally_binding"},
        headers={**h, "If-Match": etag},
    )
    assert second.status_code == 200, second.text
    assert second.headers["ETag"] != etag
    replay = client.patch(
        f"/api/v1/hoa/resolutions/{rid}",
        json={"status": "contested"},
        headers={**h, "If-Match": etag},
    )
    assert replay.status_code == 412

    # validation, permission and tenant separation
    assert (
        client.patch(f"/api/v1/hoa/resolutions/{rid}", json={"status": "x"}, headers=h).status_code
        == 422
    )
    reader = _h(client, world, "aa04reader", world.tenant_a)
    assert (
        client.patch(
            f"/api/v1/hoa/resolutions/{rid}", json={"status": "final"}, headers=reader
        ).status_code
        == 403
    )
    other = _h(client, world, "aa04admin_b", world.tenant_b)
    assert (
        client.patch(
            f"/api/v1/hoa/resolutions/{rid}", json={"status": "final"}, headers=other
        ).status_code
        == 404
    )
    assert client.get("/api/v1/hoa/resolutions", params=base, headers=other).json() == []


def test_message_patch_if_match_unknown(client: TestClient, world: World) -> None:
    h = _h(client, world, "aa04admin", world.tenant_a)
    missing = client.patch(
        f"/api/v1/mail/messages/{uuid.uuid4()}",
        json={"status": "done"},
        headers={**h, "If-Match": '"t1"'},
    )
    assert missing.status_code == 404
