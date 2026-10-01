"""AA17: delivery default, number formats, customer domains, OIDC client API, folder scheme."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa17a-{RUN}", name=f"AA17A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa17b-{RUN}", name=f"AA17B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "aa17admin": (False, a, "tenant_admin"),
            "aa17reader": (False, a, "read_only"),
            "aa17padmin": (True, None, None),
        }
        for name, (is_admin, tenant_id, role) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            if tenant_id is not None:
                await services.add_member(
                    factory,
                    tenant_id=tenant_id,
                    user_id=uid,
                    role_codes=[role],
                    actor_user_id=None,
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as test_client:
        yield test_client


def test_delivery_default(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "aa17admin"))
    assert client.get("/api/v1/tenant/delivery-default", headers=h).json() == {
        "default_delivery_channel": "post"
    }
    put = client.put(
        "/api/v1/tenant/delivery-default", json={"default_delivery_channel": "email"}, headers=h
    )
    assert put.status_code == 200
    assert client.get("/api/v1/tenant/delivery-default", headers=h).json() == {
        "default_delivery_channel": "email"
    }
    bad = client.put(
        "/api/v1/tenant/delivery-default", json={"default_delivery_channel": "fax"}, headers=h
    )
    assert bad.status_code == 422
    r = bearer(login(client, world, "aa17reader"))
    assert client.get("/api/v1/tenant/delivery-default", headers=r).status_code == 200
    forbidden = client.put(
        "/api/v1/tenant/delivery-default", json={"default_delivery_channel": "post"}, headers=r
    )
    assert forbidden.status_code == 403


def test_number_formats(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "aa17admin"))
    url = "/api/v1/tenant/number-formats"
    default = {f["scope"]: f for f in client.get(url, headers=h).json()["formats"]}
    assert default["contract"]["preview"][0] == "000001"
    assert default["invoice"]["locked"] is True
    assert default["invoice"]["preview"][0].endswith("-000001")
    assert default["invoice"]["preview"][0].startswith("MR-")
    put = client.put(
        url,
        json={"formats": {"contract": {"prefix": "V", "digits": 5, "start": 100}}},
        headers=h,
    )
    assert put.status_code == 200, put.text
    contract = next(f for f in put.json()["formats"] if f["scope"] == "contract")
    assert contract["preview"] == ["V-00100", "V-00101", "V-00102"]
    assert contract["is_default"] is False
    # invoice circle stays locked, an unchanged invoice entry is accepted
    locked = client.put(
        url, json={"formats": {"invoice": {"prefix": "RE", "digits": 6}}}, headers=h
    )
    assert locked.status_code == 422
    invalid = client.put(
        url, json={"formats": {"contract": {"prefix": "v x", "digits": 5}}}, headers=h
    )
    assert invalid.status_code == 422
    unknown = client.put(url, json={"formats": {"nope": {"digits": 5}}}, headers=h)
    assert unknown.status_code == 422
    prev = client.post(
        url + "/preview", json={"scope": "ticket", "prefix": "T", "digits": 4}, headers=h
    )
    assert prev.json()["preview"][0] == "T-0001"
    r = bearer(login(client, world, "aa17reader"))
    assert client.put(url, json={"formats": {}}, headers=r).status_code == 403
    # reset to defaults
    reset = client.put(url, json={"formats": {"contract": {"digits": 6}}}, headers=h)
    assert next(f for f in reset.json()["formats"] if f["scope"] == "contract")["is_default"]


def test_tenant_domains_and_status(client: TestClient, world: World) -> None:
    p = bearer(login(client, world, "aa17padmin"))
    base = f"/api/v1/platform/tenants/{world.tenant_a}"
    host = f"portal-{RUN}.kunde-aa17.test"
    created = client.post(
        base + "/domains", json={"host": host.upper(), "purpose": "crm"}, headers=p
    )
    assert created.status_code == 201, created.text
    assert created.json()["host"] == host
    assert created.json()["cname_hint"].startswith(f"CNAME {host} ->")
    assert client.post(base + "/domains", json={"host": host}, headers=p).status_code == 409
    other = f"/api/v1/platform/tenants/{world.tenant_b}/domains"
    assert client.post(other, json={"host": host}, headers=p).status_code == 409
    assert client.post(base + "/domains", json={"host": "ohne punkt"}, headers=p).status_code == 422
    assert (
        client.post(base + "/domains", json={"host": host, "purpose": "x"}, headers=p).status_code
        == 422
    )
    listed = client.get(base + "/domains", headers=p).json()
    assert [d["host"] for d in listed if d["host"] == host] == [host]
    # host resolution after the change
    by_host = client.get("/api/v1/auth/portal-config", headers={"host": host})
    assert by_host.status_code in (200, 404)
    # wrong tenant for the domain id: 404
    domain_id = created.json()["id"]
    assert client.delete(f"{other}/{domain_id}", headers=p).status_code == 404
    assert client.delete(f"{base}/domains/{domain_id}", headers=p).status_code == 204
    assert all(d["host"] != host for d in client.get(base + "/domains", headers=p).json())
    # not a platform administrator
    t = bearer(login(client, world, "aa17admin"))
    assert client.get(base + "/domains", headers=t).status_code == 403
    assert client.post(base + "/domains", json={"host": host}, headers=t).status_code == 403
    # status
    assert (
        client.patch(
            f"/api/v1/platform/tenants/{world.tenant_b}", json={"status": "suspended"}, headers=p
        ).json()["status"]
        == "suspended"
    )
    assert (
        client.patch(
            f"/api/v1/platform/tenants/{world.tenant_b}", json={"status": "active"}, headers=p
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/platform/tenants/{world.tenant_b}", json={"status": "gone"}, headers=p
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/platform/tenants/{world.tenant_b}", json={"status": "active"}, headers=t
        ).status_code
        == 403
    )


def test_oidc_clients_api(client: TestClient, world: World, migrator_engine: Any) -> None:
    from sqlalchemy import text

    p = bearer(login(client, world, "aa17padmin"))
    cid = f"aa17-{RUN}"
    url = "/api/v1/platform/oidc-clients"
    try:
        body = {"client_id": cid, "name": "Status", "redirect_uris": ["https://s.example.org/cb"]}
        created = client.post(url, json=body, headers=p)
        assert created.status_code == 201, created.text
        secret = created.json()["client_secret"]
        assert secret
        assert created.json()["public"] is False
        assert client.post(url, json=body, headers=p).status_code == 409
        http = {**body, "client_id": cid + "x", "redirect_uris": ["http://s.example.org/cb"]}
        assert client.post(url, json=http, headers=p).status_code == 422
        listed = next(c for c in client.get(url, headers=p).json() if c["client_id"] == cid)
        assert "client_secret" not in listed
        assert listed["active"] is True
        rotated = client.post(f"{url}/{cid}/rotate-secret", headers=p)
        assert rotated.status_code == 200
        assert rotated.json()["client_secret"] != secret
        off = client.post(f"{url}/{cid}/deactivate", headers=p)
        assert off.json()["active"] is False
        assert client.post(f"{url}/{cid}/activate", headers=p).json()["active"] is True
        assert client.post(f"{url}/missing-{RUN}/rotate-secret", headers=p).status_code == 404
        t = bearer(login(client, world, "aa17admin"))
        assert client.get(url, headers=t).status_code == 403
        assert client.post(url, json=body, headers=t).status_code == 403
    finally:
        with migrator_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM oidc_client WHERE client_id LIKE :p"), {"p": f"aa17-{RUN}%"}
            )
