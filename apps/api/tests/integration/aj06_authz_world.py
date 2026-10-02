"""AJ06 (GAI-303): own test world for the table driven authorisation tests.

Two tenants (prefix ``aj06-<run>``), an administrator in each and a read only user in
tenant A. Only the generic login and settings helpers are shared with other modules.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD
from tests.integration.test_m2_platform import _settings as base_settings

RUN = f"aj06-{uuid.uuid4().hex[:8]}"


@dataclass
class AuthzWorld:
    tenant_a: uuid.UUID
    tenant_b: uuid.UUID
    users: dict[str, uuid.UUID] = field(default_factory=dict)

    def email(self, name: str) -> str:
        return f"{name}-{RUN}@example.org"


def settings(database: Database, redis_url: str) -> Any:
    return base_settings(database, redis_url)


async def _build(cfg: Any) -> AuthzWorld:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(cfg)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"{RUN}-a", name=f"AJ06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"{RUN}-b", name=f"AJ06 B {RUN}")
        world = AuthzWorld(tenant_a=a, tenant_b=b)
        for name, tenant, role in (
            ("aj06adm", a, "tenant_admin"),
            ("aj06oth", b, "tenant_admin"),
            ("aj06rd", a, "read_only"),
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


_CACHE: dict[str, AuthzWorld] = {}


def build_world(database: Database, redis_url: str) -> AuthzWorld:
    """Builds the world once per test run (both AJ06 modules share it)."""
    if "world" not in _CACHE:
        _CACHE["world"] = asyncio.run(_build(settings(database, redis_url)))
    return _CACHE["world"]


def headers(client: TestClient, world: AuthzWorld, name: str) -> dict[str, str]:
    step = client.post(
        "/api/v1/auth/login", json={"email": world.email(name), "password": PASSWORD}
    )
    assert step.status_code == 200, step.text
    assert step.json()["status"] == "ok", step.text
    return {"Authorization": f"Bearer {step.json()['access_token']}"}


def ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def call(client: TestClient, method: str, path: str, h: dict[str, str], body: Any) -> Any:
    if body is None:
        return client.request(method, path, headers=h)
    return client.request(method, path, headers=h, json=body)
