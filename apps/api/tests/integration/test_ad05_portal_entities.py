"""AD05: GET /portal-admin/legal-entities with a real legal entity of a foreign tenant.

Expected values by hand: each of the two tenants owns one entity with a distinct name. The admin of
tenant A sees exactly its own entity (id and name only), never the one of tenant B, and vice versa.
Using the foreign entity id for a class grant of an own portal account returns 404 (RLS), the same
as an unknown id."""

import asyncio
import uuid
from collections.abc import Iterator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.properties.models import LegalEntity, LegalEntityKind
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _ok

pytestmark = pytest.mark.integration
PA = "/api/v1/portal-admin"
NAME_A = f"AD05 Rechtstraeger A {RUN}"
NAME_B = f"AD05 Rechtstraeger B {RUN}"


async def _world_ad05(settings: object) -> tuple[World, dict[str, uuid.UUID]]:
    from mhvp.core import crypto
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)  # type: ignore[arg-type]
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ad05a-{RUN}", name=f"AD05 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ad05b-{RUN}", name=f"AD05 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())  # type: ignore[attr-defined]
        for name, tenant in (("ad05admina", a), ("ad05adminb", b)):
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
        ids: dict[str, uuid.UUID] = {}
        for key, tenant, entity_name in (("a", a, NAME_A), ("b", b, NAME_B)):
            async with tenant_transaction(factory, tenant) as session:
                entity = LegalEntity(
                    tenant_id=tenant, kind=LegalEntityKind.MANAGER, name=entity_name
                )
                session.add(entity)
                await session.flush()
                ids[key] = entity.id
        return world, ids
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world_ids(database: Database, redis_url: str) -> tuple[World, dict[str, uuid.UUID]]:
    return asyncio.run(_world_ad05(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def test_foreign_tenant_legal_entity_is_neither_listed_nor_usable(
    client: TestClient, world_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_ids
    ha = bearer(login(client, world, "ad05admina"))
    hb = bearer(login(client, world, "ad05adminb"))

    rows_a = _ok(client.get(f"{PA}/legal-entities", headers=ha))
    assert {(r["id"], r["name"]) for r in rows_a if r["name"].startswith("AD05")} == {
        (str(ids["a"]), NAME_A)
    }
    assert str(ids["b"]) not in {r["id"] for r in rows_a}
    rows_b = _ok(client.get(f"{PA}/legal-entities", headers=hb))
    assert str(ids["a"]) not in {r["id"] for r in rows_b}
    assert str(ids["b"]) in {r["id"] for r in rows_b}

    # The foreign entity cannot be released for an own portal account: 404 like an unknown id.
    _, person = _party(client, ha, "AD05Person")
    account = _ok(
        client.post(
            f"{PA}/accounts",
            json={
                "contact_id": str(person["id"]),
                "email": world.email("ad05portal"),
                "display_name": "ad05portal",
            },
            headers=ha,
        ),
        201,
    )
    url = f"{PA}/accounts/{account['id']}/document-class-grants"
    good = {"document_class": "abrechnungsbeleg", "role": "board"}
    foreign = client.post(url, json={**good, "legal_entity_id": str(ids["b"])}, headers=ha)
    unknown = client.post(url, json={**good, "legal_entity_id": str(uuid.uuid4())}, headers=ha)
    assert foreign.status_code == 404
    assert unknown.status_code == 404
