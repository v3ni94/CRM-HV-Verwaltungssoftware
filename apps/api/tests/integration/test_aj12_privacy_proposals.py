"""AJ12: Löschvorschläge je Datenart (nur Vorschlag, Vier-Augen) und Bereinigung der
Sitzungsmetadaten (GAI-501 bis GAI-504)."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
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
        a, _ = await services.provision_tenant(factory, slug=f"aj12a-{RUN}", name=f"AJ12 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aj12b-{RUN}", name=f"AJ12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aj12one", a, "tenant_admin"),
            ("aj12two", a, "tenant_admin"),
            ("aj12std", a, "standard"),
            ("aj12other", b, "tenant_admin"),
        ]:
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


@pytest.fixture(scope="module")
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


async def _set_delete_after(settings: Any, tenant: uuid.UUID, contact_id: str) -> None:
    from sqlalchemy import update

    from mhvp.contacts.models import Contact
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant) as session:
            await session.execute(
                update(Contact)
                .where(Contact.id == uuid.UUID(contact_id))
                .values(delete_after=date(2020, 1, 1))
            )
    finally:
        await engine.dispose()


def test_proposals_only_with_switch_and_four_eyes(
    client: TestClient, world: World, settings: Any
) -> None:
    one = bearer(login(client, world, "aj12one"))
    two = bearer(login(client, world, "aj12two"))
    other = bearer(login(client, world, "aj12other"))
    cid = str(
        _ok(
            client.post(
                "/api/v1/contacts",
                json={"kind": "person", "first_name": "Eva", "last_name": f"Vorschlag{RUN}"},
                headers=one,
            ),
            201,
        )["id"]
    )
    asyncio.run(_set_delete_after(settings, world.tenant_a, cid))
    profile = _ok(
        client.put(
            "/api/v1/privacy/deletion-profiles",
            json={"data_type": "contact", "retention_months": 0, "start_rule": "Test"},
            headers=one,
        ),
        200,
    )
    assert profile["auto_propose"] is False
    # switch off: no proposal even though the contact is due
    _ok(client.post(f"/api/v1/privacy/deletion-profiles/{profile['id']}/release", headers=two), 200)
    assert (
        _ok(client.post("/api/v1/privacy/deletion-proposals/run", headers=one), 200)["created"] == 0
    )
    profile = _ok(
        client.put(
            "/api/v1/privacy/deletion-profiles",
            json={
                "data_type": "contact",
                "retention_months": 0,
                "start_rule": "Test",
                "auto_propose": True,
            },
            headers=one,
        ),
        200,
    )
    assert profile["auto_propose"] is True
    assert profile["released"] is False
    # switch on but profile unreleased again: still nothing
    assert (
        _ok(client.post("/api/v1/privacy/deletion-proposals/run", headers=one), 200)["created"] == 0
    )
    _ok(client.post(f"/api/v1/privacy/deletion-profiles/{profile['id']}/release", headers=two), 200)
    preview = _ok(client.get("/api/v1/privacy/deletion-proposals", headers=one), 200)
    contact_row = next(p for p in preview if p["data_type"] == "contact")
    assert contact_row["candidates"] >= 1
    assert (
        _ok(client.post("/api/v1/privacy/deletion-proposals/run", headers=one), 200)["created"] >= 1
    )
    # idempotent: an open proposal blocks a second one
    assert (
        _ok(client.post("/api/v1/privacy/deletion-proposals/run", headers=one), 200)["created"] == 0
    )
    rows = _ok(client.get("/api/v1/privacy/erasure-requests", headers=one), 200)
    proposal = next(r for r in rows if r["contact_id"] == cid)
    assert proposal["status"] == "proposed"
    # the contact itself is unchanged (nothing deleted)
    contact = _ok(client.get(f"/api/v1/contacts/{cid}", headers=one), 200)
    assert not contact["display_name"].startswith("Anonymisiert")
    # other tenant: 404, sees no proposals
    assert (
        client.post(
            f"/api/v1/privacy/erasure-requests/{proposal['id']}/accept", headers=other
        ).status_code
        == 404
    )
    other_preview = _ok(client.get("/api/v1/privacy/deletion-proposals", headers=other), 200)
    assert all(p["data_type"] != "contact" for p in other_preview)
    # accept: first person; the same person may not approve
    accepted = _ok(
        client.post(f"/api/v1/privacy/erasure-requests/{proposal['id']}/accept", headers=one), 200
    )
    assert accepted["status"] == "requested"
    assert (
        client.post(
            f"/api/v1/privacy/erasure-requests/{proposal['id']}/approve", json={}, headers=one
        ).status_code
        == 403
    )
    # accepting twice is a state conflict
    assert (
        client.post(
            f"/api/v1/privacy/erasure-requests/{proposal['id']}/accept", headers=one
        ).status_code
        == 409
    )


def test_permissions_and_validation(client: TestClient, world: World) -> None:
    std = bearer(login(client, world, "aj12std"))
    one = bearer(login(client, world, "aj12one"))
    assert client.get("/api/v1/privacy/deletion-proposals", headers=std).status_code == 403
    assert client.post("/api/v1/privacy/deletion-proposals/run", headers=std).status_code == 403
    assert client.get("/api/v1/privacy/deletion-proposals?x=1", headers=one).status_code == 422
    assert (
        client.put(
            "/api/v1/privacy/deletion-profiles",
            json={"data_type": "nope", "retention_months": 1, "start_rule": "x"},
            headers=one,
        ).status_code
        == 422
    )
    # new data types are accepted, counted or only documented
    for data_type in ("domain_event", "platform_user", "bank_raw"):
        _ok(
            client.put(
                "/api/v1/privacy/deletion-profiles",
                json={"data_type": data_type, "retention_months": 120, "start_rule": "offen"},
                headers=one,
            ),
            200,
        )
    preview = {
        p["data_type"]: p
        for p in _ok(client.get("/api/v1/privacy/deletion-proposals", headers=one), 200)
    }
    assert isinstance(preview["domain_event"]["candidates"], int)
    assert preview["platform_user"]["candidates"] is None
    assert preview["bank_raw"]["candidates"] is None


def test_session_metadata_purge(client: TestClient, world: World, settings: Any) -> None:
    from sqlalchemy import select

    from mhvp.core.auth.session_purge import purge_session_metadata
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import platform_transaction
    from mhvp.platform.models import RefreshToken

    login(client, world, "aj12two", reuse=False)
    uid = world.users["aj12two"]

    async def run() -> tuple[int, int, int]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with platform_transaction(factory) as session:
                before = len(
                    list(
                        await session.scalars(
                            select(RefreshToken.id).where(
                                RefreshToken.user_id == uid, RefreshToken.user_agent.is_not(None)
                            )
                        )
                    )
                )
                # now: active tokens are untouched
                await purge_session_metadata(session, datetime.now(UTC))
                kept = len(
                    list(
                        await session.scalars(
                            select(RefreshToken.id).where(
                                RefreshToken.user_id == uid, RefreshToken.user_agent.is_not(None)
                            )
                        )
                    )
                )
                await purge_session_metadata(session, datetime.now(UTC) + timedelta(days=3650))
                rows = list(
                    await session.scalars(select(RefreshToken).where(RefreshToken.user_id == uid))
                )
                return before, kept, sum(1 for r in rows if r.user_agent is not None)
        finally:
            await engine.dispose()

    before, kept, after = asyncio.run(run())
    assert before >= 1
    assert kept == before
    assert after == 0
