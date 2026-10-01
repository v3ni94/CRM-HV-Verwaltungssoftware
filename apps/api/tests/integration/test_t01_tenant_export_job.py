"""T01 (M2-01): full tenant export job for the tenant administrator. Expected values follow
from the seeded rows (one document with known content, one legal entity)."""

import asyncio
import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m27_market_readiness import BUCKET, _settings

pytestmark = pytest.mark.integration
URL = "/api/v1/tenant/export-jobs"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"t01a-{RUN}", name=f"T01A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t01b-{RUN}", name=f"T01B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "t01admin": (a, "tenant_admin"),
            "t01adm": (a, "administrator"),
            "t01reader": (a, "read_only"),
            "t01badmin": (b, "tenant_admin"),
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


def test_export_job_lifecycle(
    client: TestClient, world: World, database: Database, redis_url: str, monkeypatch: Any
) -> None:
    from mhvp.platform import export_job

    h = bearer(login(client, world, "t01admin"))
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        export_job, "dispatch_tenant_export_job", lambda j, t: queued.append((j, t))
    )
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("akte.txt", b"Inhalt " + RUN.encode(), "text/plain")},
        headers=h,
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["id"]

    started = client.post(URL, headers=h)
    assert started.status_code == 202, started.text
    job = started.json()
    assert job["status"] == "queued"
    assert queued == [(job["id"], str(world.tenant_a))]
    # One running job at a time; not downloadable before it is ready.
    assert client.post(URL, headers=h).status_code == 409
    assert client.get(f"{URL}/{job['id']}/download", headers=h).status_code == 409

    result = asyncio.run(
        export_job.run_tenant_export_job(
            _settings(database, redis_url), uuid.UUID(job["id"]), world.tenant_a
        )
    )
    assert result == "ready"
    listed = client.get(URL, headers=h).json()
    row = next(r for r in listed if r["id"] == job["id"])
    assert row["status"] == "ready"
    assert row["size"] > 0
    assert len(row["sha256"]) == 64
    assert row["entities"]["documents"] >= 1
    download = client.get(f"{URL}/{job['id']}/download", headers=h)
    assert download.status_code == 200, download.text
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    names = set(archive.namelist())
    for entity in ("open_items", "bank_accounts", "bank_transactions", "contracts", "tickets"):
        assert f"data/{entity}.jsonl" in names
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["documents"]["errors"] == []
    originals = [n for n in names if n.startswith(f"documents/{doc_id}_")]
    assert archive.read(originals[0]) == b"Inhalt " + RUN.encode()
    docs = [json.loads(x) for x in archive.read("data/documents.jsonl").splitlines()]
    assert {d["tenant_id"] for d in docs} == {str(world.tenant_a)}
    # Audit: started, finished and downloaded events with the user.
    again = asyncio.run(
        export_job.run_tenant_export_job(
            _settings(database, redis_url), uuid.UUID(job["id"]), world.tenant_a
        )
    )
    assert again == "skipped"
    events = client.get("/api/v1/tenant/events", params={"page_size": 200}, headers=h).json()
    types = {e["type"] for e in events if e["entity_id"] == job["id"]}
    for event in events:
        if event["entity_id"] == job["id"]:
            assert event["actor_user_id"] is not None
    assert {"tenant_export.started", "tenant_export.finished", "tenant_export.downloaded"} <= types


def test_export_job_authorization_and_tenant_separation(
    client: TestClient, world: World, monkeypatch: Any
) -> None:
    from mhvp.platform import export_job

    monkeypatch.setattr(export_job, "dispatch_tenant_export_job", lambda j, t: None)
    reader = bearer(login(client, world, "t01reader"))
    adm = bearer(login(client, world, "t01adm"))
    other = bearer(login(client, world, "t01badmin"))
    assert client.post(URL, headers=reader).status_code == 403
    assert client.get(URL, headers=reader).status_code == 403
    # Administrator role is not the tenant administrator.
    assert client.post(URL, headers=adm).status_code == 403
    assert client.get(URL, headers=adm).status_code == 403
    assert client.post(URL).status_code == 401
    started = client.post(URL, headers=other)
    assert started.status_code == 202, started.text
    owner = bearer(login(client, world, "t01admin"))
    assert all(r["id"] != started.json()["id"] for r in client.get(URL, headers=owner).json())
    assert client.get(f"{URL}/{started.json()['id']}/download", headers=owner).status_code == 404
    assert client.get(f"{URL}/{uuid.uuid4()}/download", headers=owner).status_code == 404
