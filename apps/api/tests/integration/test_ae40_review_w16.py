"""AE40 (review of wave 16): fixes found in the security and money flow review.

Own test world (prefix ``ae40``, RUN suffix): tenant a (real) and tenant d (demo flag), users:
two tenant administrators of a, a tenant administrator of d, a platform administrator.

Expected values by hand:

* AE40-1: a demo tenant never gets an open release gate. The request is stored as usual, the
  approval by a second person (platform administrator) answers 409 ``MHVP-DEMO-0001`` and the
  request stays ``requested``; a real tenant is not affected by the check (its approval fails
  later, on the missing released chart of accounts, ``MHVP-GATE-0004``).
* AE40-2: four eyes of the text blocks (legal texts, notices) cover every person who wrote the
  version: an administrator who edited the draft of another person cannot approve it after
  that person submitted it (403 ``GATE_FOUR_EYES``); a third person who did not write can.
"""

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
P = "/api/v1/platform"
REQ = "/api/v1/tenant/release-gates/requests"
B = "/api/v1/document-text-blocks"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae40a-{RUN}", name=f"AE40 A {RUN}")
        d, _ = await services.provision_tenant(
            factory, slug=f"ae40d-{RUN}", name=f"AE40 Demo {RUN}", is_demo=True
        )
        world = World(tenant_a=a, tenant_b=d, app_url=settings.database_url.get_secret_value())
        specs: dict[str, tuple[bool, list[tuple[Any, str]]]] = {
            "ae40first": (False, [(a, "tenant_admin")]),
            "ae40second": (False, [(a, "tenant_admin")]),
            "ae40third": (False, [(a, "tenant_admin")]),
            "ae40demo": (False, [(d, "tenant_admin")]),
            "ae40padmin": (True, []),
        }
        for name, (is_admin, memberships) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            for tenant_id, role in memberships:
                await services.add_member(
                    factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _gate_request(client: TestClient, headers: dict[str, str]) -> str:
    body = {
        "gate": "G1",
        "scope": "Produktive Buchhaltung des Mandanten",
        "evidence": "Abnahmeprotokoll AE40",
    }
    return str(_ok(client.post(REQ, json=body, headers=headers), 201)["id"])


def test_demo_tenant_gate_cannot_be_opened(client: TestClient, world: World) -> None:
    demo = bearer(login(client, world, "ae40demo"))
    padmin = bearer(login(client, world, "ae40padmin"))
    request_id = _gate_request(client, demo)
    approve = f"{P}/tenants/{world.tenant_b}/release-gates/requests/{request_id}/approve"
    refused = client.post(approve, json={"comment": "Demo"}, headers=padmin)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "MHVP-DEMO-0001"
    listed = _ok(client.get(REQ, headers=demo))
    row = next(r for r in listed if r["id"] == request_id)
    assert row["status"] == "requested"
    # Real tenant: the demo check does not apply; the approval stops at the G1 precondition.
    real = bearer(login(client, world, "ae40first"))
    real_id = _gate_request(client, real)
    other = client.post(
        f"{P}/tenants/{world.tenant_a}/release-gates/requests/{real_id}/approve",
        json={"comment": "x"},
        headers=padmin,
    )
    assert other.status_code != 200
    assert other.json()["code"] != "MHVP-DEMO-0001"


def test_text_block_editor_cannot_approve(client: TestClient, world: World) -> None:
    h1 = bearer(login(client, world, "ae40first"))
    h2 = bearer(login(client, world, "ae40second"))
    h3 = bearer(login(client, world, "ae40third"))
    created = _ok(
        client.post(
            B,
            json={"code": "info_sheet_objection", "title": "Einwendungen", "body": "Text A"},
            headers=h1,
        ),
        201,
    )
    bid = created["id"]
    # the second administrator writes the text of the draft, the first one submits it
    _ok(client.patch(f"{B}/{bid}", json={"body": "Text von B"}, headers=h2))
    _ok(client.patch(f"{B}/{bid}", json={"title": "Einwendungen (A)"}, headers=h1))
    _ok(client.post(f"{B}/{bid}/submit", headers=h1))
    refused = client.post(f"{B}/{bid}/approve", headers=h2)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "MHVP-GATE-0002"
    assert client.post(f"{B}/{bid}/approve", headers=h1).status_code in (403, 409)
    done = _ok(client.post(f"{B}/{bid}/approve", headers=h3))
    assert done["status"] == "approved"
    assert done["body"] == "Text von B"
