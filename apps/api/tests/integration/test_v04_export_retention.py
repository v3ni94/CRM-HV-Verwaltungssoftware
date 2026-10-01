"""V04 (T01-01): retention of tenant export archives. Expected values follow from the set
retention (7 days) and the explicit clock passed to the purge."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m27_market_readiness import BUCKET, _settings

pytestmark = pytest.mark.integration
URL = "/api/v1/tenant/export-jobs"
SETTINGS = "/api/v1/tenant/settings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"v04a-{RUN}", name=f"V04A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"v04b-{RUN}", name=f"V04B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "v04admin": (a, "tenant_admin"),
            "v04reader": (a, "read_only"),
            "v04badmin": (b, "tenant_admin"),
        }
        for name, (tenant_id, role) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=False,
            )
            world.users[name] = uid
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _run_job(client: TestClient, h: dict[str, str], tenant: uuid.UUID, settings: Any) -> dict:
    from mhvp.platform import export_job

    job = client.post(URL, headers=h).json()
    assert (
        asyncio.run(export_job.run_tenant_export_job(settings, uuid.UUID(job["id"]), tenant))
        == "ready"
    )
    return next(r for r in client.get(URL, headers=h).json() if r["id"] == job["id"])


def test_retention_setting_validation_and_permission(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "v04admin"))
    reader = bearer(login(client, world, "v04reader"))
    assert client.get(SETTINGS, headers=admin).json()["export_retention_days"] is None
    assert (
        client.patch(SETTINGS, json={"export_retention_days": 0}, headers=admin).status_code == 422
    )
    assert (
        client.patch(SETTINGS, json={"export_retention_days": 3651}, headers=admin).status_code
        == 422
    )
    assert (
        client.patch(SETTINGS, json={"export_retention_days": 7}, headers=reader).status_code == 403
    )
    ok = client.patch(SETTINGS, json={"export_retention_days": 7}, headers=admin)
    assert ok.status_code == 200, ok.text
    assert ok.json()["export_retention_days"] == 7
    cleared = client.patch(SETTINGS, json={"clear_export_retention_days": True}, headers=admin)
    assert cleared.json()["export_retention_days"] is None
    # Other tenant keeps its own (empty) value.
    other = bearer(login(client, world, "v04badmin"))
    assert client.get(SETTINGS, headers=other).json()["export_retention_days"] is None


def test_purge_expires_archive_and_keeps_tenants_without_retention(
    client: TestClient, world: World, database: Database, redis_url: str, monkeypatch: Any
) -> None:
    from mhvp.platform import export_job

    settings = _settings(database, redis_url)
    monkeypatch.setattr(export_job, "dispatch_tenant_export_job", lambda j, t: None)
    admin = bearer(login(client, world, "v04admin"))
    other = bearer(login(client, world, "v04badmin"))
    s3 = boto3.client("s3", region_name="us-east-1")

    # Tenant B without retention, tenant A with 7 days.
    b_row = _run_job(client, other, world.tenant_b, settings)
    assert b_row["expires_at"] is None
    assert (
        client.patch(SETTINGS, json={"export_retention_days": 7}, headers=admin).status_code == 200
    )
    a_row = _run_job(client, admin, world.tenant_a, settings)
    finished = datetime.fromisoformat(a_row["finished_at"])
    assert datetime.fromisoformat(a_row["expires_at"]) - finished == timedelta(days=7)
    key = export_job.tenant_export_key(world.tenant_a, uuid.UUID(a_row["id"]))
    s3.head_object(Bucket=BUCKET, Key=key)

    # Before expiry nothing happens.
    early = asyncio.run(
        export_job.purge_expired_exports_once(settings, now=finished + timedelta(days=6))
    )
    assert early["expired"] == 0
    assert client.get(f"{URL}/{a_row['id']}/download", headers=admin).status_code == 200

    # After expiry the archive is gone, the row stays as evidence; B is untouched.
    late = asyncio.run(
        export_job.purge_expired_exports_once(settings, now=finished + timedelta(days=8))
    )
    assert late["expired"] >= 1
    assert late["failed"] == 0
    with pytest.raises(ClientError):
        s3.head_object(Bucket=BUCKET, Key=key)
    rows = {r["id"]: r for r in client.get(URL, headers=admin).json()}
    assert rows[a_row["id"]]["status"] == "expired"
    assert rows[a_row["id"]]["expired_at"] is not None
    assert rows[a_row["id"]]["sha256"] == a_row["sha256"]
    assert client.get(f"{URL}/{a_row['id']}/download", headers=admin).status_code == 409
    b_after = next(r for r in client.get(URL, headers=other).json() if r["id"] == b_row["id"])
    assert b_after["status"] == "ready"
    events = client.get("/api/v1/tenant/events", params={"page_size": 200}, headers=admin).json()
    assert "tenant_export.expired" in {e["type"] for e in events if e["entity_id"] == a_row["id"]}

    # Idempotent: a second run expires nothing more for tenant A.
    again = asyncio.run(
        export_job.purge_expired_exports_once(settings, now=finished + timedelta(days=9))
    )
    assert again["failed"] == 0
    assert datetime.now(UTC) > finished


def test_download_refused_once_retention_ended_before_purge(
    client: TestClient, world: World, database: Database, redis_url: str, monkeypatch: Any
) -> None:
    """Review W79: between ``expires_at`` and the next purge run the archive is not handed out
    any more (409); the row stays ``ready`` until the purge deletes the object."""
    from sqlalchemy import create_engine, text

    from mhvp.platform import export_job

    settings = _settings(database, redis_url)
    monkeypatch.setattr(export_job, "dispatch_tenant_export_job", lambda j, t: None)
    admin = bearer(login(client, world, "v04admin"))
    client.patch(SETTINGS, json={"export_retention_days": 7}, headers=admin)
    row = _run_job(client, admin, world.tenant_a, settings)
    assert client.get(f"{URL}/{row['id']}/download", headers=admin).status_code == 200
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
            )
            conn.execute(
                text(
                    "UPDATE tenant_export_job SET expires_at = now() - interval '1 hour' "
                    "WHERE id = :i"
                ),
                {"i": row["id"]},
            )
    finally:
        engine.dispose()
    resp = client.get(f"{URL}/{row['id']}/download", headers=admin)
    assert resp.status_code == 409, resp.text
    status = next(r for r in client.get(URL, headers=admin).json() if r["id"] == row["id"])
    assert status["status"] == "ready"


def test_purge_applies_retention_set_after_the_export(
    client: TestClient, world: World, database: Database, redis_url: str, monkeypatch: Any
) -> None:
    from mhvp.platform import export_job

    settings = _settings(database, redis_url)
    monkeypatch.setattr(export_job, "dispatch_tenant_export_job", lambda j, t: None)
    admin = bearer(login(client, world, "v04admin"))
    assert (
        client.patch(
            SETTINGS, json={"clear_export_retention_days": True}, headers=admin
        ).status_code
        == 200
    )
    row = _run_job(client, admin, world.tenant_a, settings)
    assert row["expires_at"] is None
    finished = datetime.fromisoformat(row["finished_at"])
    far = finished + timedelta(days=4000)
    asyncio.run(export_job.purge_expired_exports_once(settings, now=far))
    assert (
        next(r for r in client.get(URL, headers=admin).json() if r["id"] == row["id"])["status"]
        == "ready"
    )
    client.patch(SETTINGS, json={"export_retention_days": 30}, headers=admin)
    asyncio.run(export_job.purge_expired_exports_once(settings, now=finished + timedelta(days=29)))
    assert (
        next(r for r in client.get(URL, headers=admin).json() if r["id"] == row["id"])["status"]
        == "ready"
    )
    asyncio.run(export_job.purge_expired_exports_once(settings, now=finished + timedelta(days=31)))
    assert (
        next(r for r in client.get(URL, headers=admin).json() if r["id"] == row["id"])["status"]
        == "expired"
    )
