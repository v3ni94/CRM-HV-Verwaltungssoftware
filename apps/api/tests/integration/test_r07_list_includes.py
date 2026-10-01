"""R07 (Q12 remainder): ``include`` on the contact, property, contract, document and invoice
lists (S12-03).

Fixed expectations: a rental property 931 with owner "Vermieter" and one tenancy of the
person "Mietpartei"; the tenancy list with include=party,property names the party member
"Mietpartei" and property 931; the contact list with include=properties gives the tenant
contact exactly property 931; the property list with include=legal_entities lists the
owner's legal entity for 931. Unknown includes are 422; the other tenant sees nothing."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_contracts_search import _contract, _owner, _party
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _property, _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r07-{RUN}", name=f"R07 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r07b-{RUN}", name=f"R07 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("r07admin", a, "tenant_admin"),
            ("r07reader", a, "read_only"),
            ("r07other", b, "tenant_admin"),
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
    import boto3
    from moto import mock_aws

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_list_includes(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r07admin"))
    prop = _property(client, h, "931", "rental")
    _owner(client, h, prop["id"])
    unit = _unit(client, h, prop["id"], "01")
    party, contact = _party(
        client, h, {"kind": "person", "first_name": "Mia", "last_name": f"Mietpartei {RUN}"}
    )
    contract = _contract(client, h, "tenancy", unit, party)

    rows = _ok(
        client.get(
            "/api/v1/contracts",
            params={"include": "party,property", "fields": "number", "property_id": prop["id"]},
            headers=h,
        )
    )
    assert [r["id"] for r in rows] == [contract]
    assert set(rows[0]) == {"id", "number", "party", "property"}
    assert rows[0]["property"]["number"] == "931"
    assert rows[0]["party"]["id"] == party
    assert [m["contact_id"] for m in rows[0]["party"]["members"]] == [contact]

    contacts = _ok(
        client.get(
            "/api/v1/contacts",
            params={"include": "properties", "q": f"Mietpartei {RUN}"},
            headers=h,
        )
    )
    assert contacts["total"] == 1
    assert [p["number"] for p in contacts["items"][0]["properties"]] == ["931"]

    props = _ok(
        client.get(
            "/api/v1/properties",
            params={"include": "legal_entities", "q": "931"},
            headers=h,
        )
    )
    entities = next(i for i in props["items"] if i["number"] == "931")["legal_entities"]
    assert any(e["name"].startswith(f"Vermieter {RUN}") for e in entities), entities

    docs = _ok(client.get("/api/v1/documents", params={"include": "properties"}, headers=h))
    assert docs["total"] == 0
    assert (
        _ok(client.get("/api/v1/accounting/invoices", params={"include": "creditor"}, headers=h))
        == []
    )

    # Unknown includes are refused on every list.
    for path in (
        "/api/v1/contacts",
        "/api/v1/properties",
        "/api/v1/contracts",
        "/api/v1/documents",
        "/api/v1/accounting/invoices",
    ):
        assert client.get(path, params={"include": "nope"}, headers=h).status_code == 422, path

    # Read right suffices; the other tenant sees none of the rows.
    hr = bearer(login(client, world, "r07reader"))
    assert (
        _ok(client.get("/api/v1/contracts", params={"include": "party"}, headers=hr))[0]["party"][
            "id"
        ]
        == party
    )
    ho = bearer(login(client, world, "r07other"))
    other = _ok(
        client.get(
            "/api/v1/contacts",
            params={"include": "properties", "q": f"Mietpartei {RUN}"},
            headers=ho,
        )
    )
    assert other["total"] == 0
    assert _ok(client.get("/api/v1/contracts", params={"include": "party"}, headers=ho)) == []
