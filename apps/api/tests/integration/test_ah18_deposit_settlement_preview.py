"""GAG-29: PDF preview of a deposit settlement draft
(GET /contracts/{id}/deposit-settlements/{sid}/document-preview).

The preview renders the stored draft as PDF without filing it and without any posting or
payout. Checks: content type and no-store, read permission (read_only allowed, member without
role 403), tenant separation (foreign tenant 404), unknown settlement and mismatching contract
404, and that the draft stays a draft.
"""

import asyncio
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _ok
from tests.integration.test_m5_deposit_settlement import (
    COMPANY,
    _deposit_with_address,
    _deposit_with_movements,
    _settings,
    client,  # noqa: F401  (fixture)
    s3,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"18-{RUN}-a", name=f"AH18 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"18-{RUN}-b", name=f"AH18b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, roles in [
            ("ah18admin", a, ["tenant_admin"]),
            ("ah18reader", a, ["read_only"]),
            ("ah18none", a, []),
            ("ah18other", b, ["tenant_admin"]),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=roles, actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


def test_settlement_document_preview(client: TestClient, world: World) -> None:  # noqa: F811
    h = bearer(login(client, world, "ah18admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h), 200)
    deposit, contract = _deposit_with_address(client, h)
    saved = _ok(
        client.post(
            f"/api/v1/deposits/{deposit}/settlements",
            json={
                "settlement_date": "2026-06-30",
                "interest_mode": "none",
                "deductions": [{"label": "Endreinigung", "amount": "80.00"}],
            },
            headers=h,
        ),
        201,
    )
    sid = saved["id"]
    url = f"/api/v1/contracts/{contract}/deposit-settlements/{sid}/document-preview"

    res = client.get(url, headers=h)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["cache-control"] == "no-store"
    assert res.content.startswith(b"%PDF")

    # Read permission is enough; no permission at all is refused.
    reader = bearer(login(client, world, "ah18reader"))
    assert client.get(url, headers=reader).status_code == 200
    none = bearer(login(client, world, "ah18none"))
    assert client.get(url, headers=none).status_code == 403
    assert client.get(url).status_code == 401

    # Tenant separation and unknown or mismatching ids.
    other = bearer(login(client, world, "ah18other", tenant_id=world.tenant_b))
    assert client.get(url, headers=other).status_code == 404
    unknown = f"/api/v1/contracts/{contract}/deposit-settlements/{uuid.uuid4()}/document-preview"
    assert client.get(unknown, headers=h).status_code == 404
    _, second_contract = _deposit_with_movements(client, h)
    wrong = f"/api/v1/contracts/{second_contract}/deposit-settlements/{sid}/document-preview"
    assert client.get(wrong, headers=h).status_code == 404
    assert client.get(url.replace(sid, "kein-uuid"), headers=h).status_code == 422

    # The preview does not release the draft.
    drafts = _ok(client.get(f"/api/v1/deposits/{deposit}/settlements", headers=h), 200)
    assert all(d["status"] == "draft" for d in drafts)
