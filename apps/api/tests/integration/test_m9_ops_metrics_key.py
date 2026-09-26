"""M9-04a (operator decision 26.09.2026): the monitoring reads ``/api/v1/platform/ops/metrics``
with an API key that carries only ``platform:metrics:read``. Covered: issue by a platform
administrator only, both output formats, the key reads nothing else (platform and tenant
endpoints), revocation, the session path still works, rate limit headers, audit events and
no tenant data in the metrics output."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
METRICS = "/api/v1/platform/ops/metrics"
KEYS = "/api/v1/platform/ops/metrics-keys"
TENANT_NAME = f"Metrics {RUN} Geheim"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"mk-{RUN}", name=TENANT_NAME)
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, is_admin, role in [("mkpadmin", True, ""), ("mktenant", False, "tenant_admin")]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            if role:
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
    with TestClient(
        create_app(_settings(database, redis_url, rate_limit_enabled=True))
    ) as test_client:
        yield test_client


def _issue(client: TestClient, world: World, name: str = "Uptime Kuma") -> dict[str, Any]:
    response = client.post(
        KEYS,
        json={"name": name, "tenant_id": str(world.tenant_a)},
        headers=bearer(login(client, world, "mkpadmin")),
    )
    assert response.status_code == 201, response.text
    body = dict(response.json())
    assert body["scopes"] == ["platform:metrics:read"]
    assert body["key"].startswith("mhvp_")
    return body


def test_key_reads_metrics_in_both_formats_and_nothing_else(
    client: TestClient, world: World
) -> None:
    issued = _issue(client, world)
    headers = {"X-API-Key": issued["key"]}

    as_json = client.get(METRICS, headers=headers)
    assert as_json.status_code == 200, as_json.text
    body = as_json.json()
    assert set(body) == {"metrics", "alerts", "jobs"}
    assert all(isinstance(v, int) for v in body["metrics"].values())
    # Counts only: no tenant name, slug or id in the output (section 16, no personal data).
    text = as_json.text
    assert TENANT_NAME not in text
    assert f"mk-{RUN}" not in text
    assert str(world.tenant_a) not in text
    assert world.tenant_a.hex not in text
    assert as_json.headers["X-RateLimit-Limit"]  # rate limited like every API key

    as_prom = client.get(f"{METRICS}?format=prometheus", headers=headers)
    assert as_prom.status_code == 200, as_prom.text
    assert as_prom.headers["content-type"].startswith("text/plain")
    assert "# TYPE mhvp_tenants_active gauge" in as_prom.text
    assert "mhvp_backup_verify_stale" in as_prom.text
    assert TENANT_NAME not in as_prom.text

    # Every other platform endpoint and every tenant endpoint is closed to the key.
    for method, url, payload in [
        ("GET", "/api/v1/platform/tenants", None),
        ("POST", "/api/v1/platform/tenants", {"slug": f"x{RUN}", "name": "x"}),
        ("GET", "/api/v1/platform/settings", None),
        ("GET", "/api/v1/platform/superadmin", None),
        ("GET", KEYS, None),
        ("POST", KEYS, {"name": "zweiter", "tenant_id": str(world.tenant_a)}),
        ("DELETE", f"{KEYS}/{issued['id']}", None),
        ("GET", "/api/v1/tenant/settings", None),
        ("PATCH", "/api/v1/tenant/settings", {"company": {"name": "X"}}),
        ("GET", "/api/v1/tenant/api-keys", None),
        ("POST", "/api/v1/tenant/api-keys", {"name": "x", "scopes": ["tenant_settings:read"]}),
        ("GET", "/api/v1/tenant/members", None),
        ("GET", "/api/v1/tenant/audit-log", None),
        ("GET", "/api/v1/tenant/events", None),
        ("GET", "/api/v1/tenant/release-gates", None),
        ("GET", "/api/v1/contacts", None),
        ("GET", "/api/v1/properties", None),
    ]:
        response = client.request(method, url, json=payload, headers=headers)
        assert response.status_code == 403, (method, url, response.status_code, response.text)


def test_revoked_key_is_rejected_and_session_admin_still_works(
    client: TestClient, world: World
) -> None:
    issued = _issue(client, world, name="Widerruf")
    headers = {"X-API-Key": issued["key"]}
    assert client.get(METRICS, headers=headers).status_code == 200
    padmin = bearer(login(client, world, "mkpadmin"))

    listed = client.get(KEYS, headers=padmin)
    assert listed.status_code == 200
    assert any(k["id"] == issued["id"] for k in listed.json())
    assert all("key" not in k and "secret_hash" not in k for k in listed.json())

    revoked = client.delete(f"{KEYS}/{issued['id']}", headers=padmin)
    assert revoked.status_code == 204
    assert client.get(METRICS, headers=headers).status_code == 401
    assert client.get(f"{METRICS}?format=prometheus", headers=headers).status_code == 401
    assert client.delete(f"{KEYS}/{issued['id']}", headers=padmin).status_code == 404

    # Session of the platform administrator keeps working; forged key is rejected.
    assert client.get(METRICS, headers=padmin).status_code == 200
    forged = {"X-API-Key": issued["key"][:-2] + "xx"}
    assert client.get(METRICS, headers=forged).status_code == 401

    # Creation and revocation are audited in the storage tenant.
    events = client.get("/api/v1/tenant/events", headers=bearer(login(client, world, "mktenant")))
    assert events.status_code == 200, events.text
    by_type = {(e["type"], e["entity_id"]) for e in events.json() if e["entity_type"] == "api_key"}
    assert ("api_key.created", issued["id"]) in by_type
    assert ("api_key.revoked", issued["id"]) in by_type


def test_only_platform_admin_sessions_issue_keys(client: TestClient, world: World) -> None:
    tenant_admin = bearer(login(client, world, "mktenant"))
    denied = client.post(
        KEYS, json={"name": "Nein", "tenant_id": str(world.tenant_a)}, headers=tenant_admin
    )
    assert denied.status_code == 403
    assert client.get(KEYS, headers=tenant_admin).status_code == 403
    assert client.post(KEYS, json={"name": "Nein"}).status_code == 401

    # A tenant API key may not carry the platform permission, and a tenant key with every
    # tenant permission of the administrator still cannot read the metrics.
    rejected = client.post(
        "/api/v1/tenant/api-keys",
        json={"name": "Schleichweg", "scopes": ["platform:metrics:read"]},
        headers=tenant_admin,
    )
    assert rejected.status_code == 422, rejected.text
    tenant_key = client.post(
        "/api/v1/tenant/api-keys",
        json={"name": "Mandant", "scopes": ["tenant_settings:read", "audit:read"]},
        headers=tenant_admin,
    )
    assert tenant_key.status_code == 201, tenant_key.text
    assert client.get(METRICS, headers={"X-API-Key": tenant_key.json()["key"]}).status_code == 403

    # Without a tenant (no switch, no body tenant) the storage tenant is missing.
    padmin = bearer(login(client, world, "mkpadmin"))
    no_tenant = client.post(KEYS, json={"name": "Ohne Mandant"}, headers=padmin)
    assert no_tenant.status_code == 409, no_tenant.text
    unknown = client.post(
        KEYS,
        json={"name": "Fremd", "tenant_id": "00000000-0000-0000-0000-000000000001"},
        headers=padmin,
    )
    assert unknown.status_code == 404
