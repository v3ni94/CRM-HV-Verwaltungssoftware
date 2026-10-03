"""AK01 (GAI-202, GAI-214, GAI-204): persistent tenant switches of the calculation rules.

Own test world (prefix ``ak01-<run>``): two tenants, an administrator in each and a read only
user in tenant A. Checks defaults, partial update, validation, the write permission and the
tenant separation (tenant B keeps its defaults).
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration

RUN = f"ak01-{uuid.uuid4().hex[:8]}"
PATH = "/api/v1/billing/calculation-settings"
DEFAULTS = {
    "heating_negative_costs_mode": "legacy_warn",
    "hoa_remainder_mode": "report_only",
    "check_amounts_tolerance_cents": 1,
}


def _email(name: str) -> str:
    return f"{name}-{RUN}@example.org"


async def _build(cfg: Any) -> None:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(cfg)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"{RUN}-a", name=f"AK01 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"{RUN}-b", name=f"AK01 B {RUN}")
        for name, tenant, role in (
            ("ak01adm", a, "tenant_admin"),
            ("ak01oth", b, "tenant_admin"),
            ("ak01rd", a, "read_only"),
        ):
            uid = await services.create_user(
                factory, email=_email(name), display_name=name, password=PASSWORD
            )
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    cfg = base_settings(database, redis_url)
    asyncio.run(_build(cfg))
    with TestClient(create_app(cfg)) as test_client:
        yield test_client


def _h(client: TestClient, name: str) -> dict[str, str]:
    step = client.post("/api/v1/auth/login", json={"email": _email(name), "password": PASSWORD})
    assert step.status_code == 200, step.text
    return {"Authorization": f"Bearer {step.json()['access_token']}"}


def test_defaults_update_validation_permission_and_tenant_separation(client: TestClient) -> None:
    adm, oth, rd = _h(client, "ak01adm"), _h(client, "ak01oth"), _h(client, "ak01rd")

    got = client.get(PATH, headers=adm)
    assert got.status_code == 200, got.text
    assert got.json() == DEFAULTS

    # Validation: unknown value, unknown field, tolerance outside 0/1.
    for body in (
        {"heating_negative_costs_mode": "always"},
        {"hoa_remainder_mode": "middle_month"},
        {"check_amounts_tolerance_cents": 2},
        {"unknown": 1},
    ):
        assert client.put(PATH, headers=adm, json=body).status_code == 422, body

    # Read only user: may read, may not write.
    assert client.get(PATH, headers=rd).status_code == 200
    denied = client.put(PATH, headers=rd, json={"hoa_remainder_mode": "last_month"})
    assert denied.status_code == 403, denied.text

    # Partial update keeps the other fields.
    put = client.put(PATH, headers=adm, json={"hoa_remainder_mode": "last_month"})
    assert put.status_code == 200, put.text
    assert put.json() == {**DEFAULTS, "hoa_remainder_mode": "last_month"}
    put = client.put(
        PATH,
        headers=adm,
        json={"heating_negative_costs_mode": "distribute", "check_amounts_tolerance_cents": 0},
    )
    assert put.json() == {
        "heating_negative_costs_mode": "distribute",
        "hoa_remainder_mode": "last_month",
        "check_amounts_tolerance_cents": 0,
    }
    assert client.get(PATH, headers=adm).json() == put.json()

    # Tenant B is untouched.
    assert client.get(PATH, headers=oth).json() == DEFAULTS
