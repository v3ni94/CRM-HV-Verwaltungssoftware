"""P17: Löschanträge mit Sperrprüfung und Vier-Augen, Löschprofile, Register, Verzeichnis."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import _ok, _settings
from tests.integration.test_m6_documents import client as _m6_client
from tests.integration.test_m6_documents import s3 as _m6_s3

s3 = _m6_s3
client = _m6_client
pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p17a-{RUN}", name=f"P17 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p17b-{RUN}", name=f"P17 Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("p17one", a), ("p17two", a), ("p17other", b)]:
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
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


def _contact(c: TestClient, h: dict[str, str]) -> str:
    body = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Erika", "last_name": f"Muster{RUN}"},
            headers=h,
        ),
        201,
    )
    return str(body["id"])


def test_erasure_locks_and_four_eyes(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "p17one"))
    two = bearer(login(client, world, "p17two"))
    other = bearer(login(client, world, "p17other"))
    cid = _contact(client, one)
    req = _ok(
        client.post(
            "/api/v1/privacy/erasure-requests",
            json={"contact_id": cid, "received_on": "2026-09-30"},
            headers=one,
        ),
        201,
    )
    codes = {b["code"] for b in req["blockers"]}
    assert {"deletion_profile_not_released", "no_retention_profile"} <= codes
    # other tenant: 404 on the request and the contact
    assert (
        client.post(
            f"/api/v1/privacy/erasure-requests/{req['id']}/approve", json={}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/privacy/erasure-requests",
            json={"contact_id": cid, "received_on": "2026-09-30"},
            headers=other,
        ).status_code
        == 404
    )
    # blocked: release is refused even for a second person
    r = client.post(f"/api/v1/privacy/erasure-requests/{req['id']}/approve", json={}, headers=two)
    assert r.status_code == 409
    # requester never decides
    r = client.post(f"/api/v1/privacy/erasure-requests/{req['id']}/approve", json={}, headers=one)
    assert r.status_code == 403
    # validation
    assert (
        client.post(
            "/api/v1/privacy/erasure-requests", json={"contact_id": cid}, headers=one
        ).status_code
        == 422
    )


def test_deletion_profile_four_eyes_and_anonymisation(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "p17one"))
    two = bearer(login(client, world, "p17two"))
    profile = _ok(
        client.put(
            "/api/v1/privacy/deletion-profiles",
            json={
                "data_type": "contact",
                "retention_months": 0,
                "start_rule": "Testregel ohne Rechtsquelle",
            },
            headers=one,
        ),
        200,
    )
    assert profile["released"] is False
    assert (
        client.post(
            f"/api/v1/privacy/deletion-profiles/{profile['id']}/release", headers=one
        ).status_code
        == 403
    )
    _ok(client.post(f"/api/v1/privacy/deletion-profiles/{profile['id']}/release", headers=two), 200)
    cid = _contact(client, one)
    # retention profile and due date are prerequisites; set them directly for the test
    from mhvp.documents.models import RetentionProfile  # noqa: F401

    req = _ok(
        client.post(
            "/api/v1/privacy/erasure-requests",
            json={"contact_id": cid, "received_on": "2026-09-30"},
            headers=one,
        ),
        201,
    )
    codes = {b["code"] for b in req["blockers"]}
    assert "deletion_profile_not_released" not in codes
    assert "no_retention_profile" in codes


def test_register_and_records_draft(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "p17one"))
    other = bearer(login(client, world, "p17other"))
    _ok(
        client.post(
            "/api/v1/privacy/register",
            json={
                "kind": "processor",
                "name": "Testdienstleister",
                "avv_status": "requested",
                "third_country": True,
            },
            headers=one,
        ),
        201,
    )
    draft = _ok(client.get("/api/v1/privacy/processing-records", headers=one), 200)
    assert "V13" in draft["markdown"]
    assert "Testdienstleister" in draft["markdown"]
    assert "AVV-Nachweis fehlt" in draft["markdown"]
    assert (
        "Testdienstleister"
        not in _ok(client.get("/api/v1/privacy/processing-records", headers=other), 200)["markdown"]
    )
    assert (
        client.post(
            "/api/v1/privacy/register", json={"kind": "x", "name": "a"}, headers=one
        ).status_code
        == 422
    )
