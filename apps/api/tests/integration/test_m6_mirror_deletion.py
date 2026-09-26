"""A43 (6.9.5, M6-03): logged deletion of the copies in Paperless and Google Drive after the
platform deletion of a document with a released, expired retention profile. The lock without
such a profile is unchanged (test_m6_documents); here the journal per mirror is checked with
fake clients: request events in the deleting transaction, the Celery hand-over, deletion,
failure with retry and the "already gone" case."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.core.config import Settings
from mhvp.documents import mirror_deletion
from mhvp.documents.blobs import BlobStore
from mhvp.documents.mirror_deletion import MirrorDeletionError, MirrorDeletionJob
from mhvp.documents.tasks import mirror_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-mirror-del"
PAPERLESS_URL = f"https://dms-md-{RUN}.example.org"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=200_000,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"md-{RUN}", name=f"Spiegel {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"me-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("mdadmin", a), ("mdsecond", a)]:
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


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


class FakeMirrors:
    """Paperless and Drive: upload for the mirror job, DELETE for the deletion job."""

    def __init__(self) -> None:
        self.fail_delete = False
        self.deleted: list[str] = []
        self.drive_gone = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        if url.startswith(f"{PAPERLESS_URL}/api/"):
            assert request.headers["authorization"] == "Token paperless-token"
            if request.method == "DELETE":
                if self.fail_delete:
                    return httpx.Response(503)
                self.deleted.append(f"paperless:{path}")
                return httpx.Response(204)
            if path.endswith("/post_document/"):
                return httpx.Response(200, json="task-9")
            if path.endswith("/tasks/"):
                return httpx.Response(200, json=[{"status": "SUCCESS", "related_document": 77}])
            if request.method == "GET":
                return httpx.Response(200, json={"results": [{"id": 3}]})
            return httpx.Response(201, json={"id": 3})
        if url.startswith("https://oauth2.googleapis.com/token"):
            return httpx.Response(200, json={"access_token": "drive-token"})
        if url.startswith("https://www.googleapis.com/drive/v3/files"):
            assert request.headers["authorization"] == "Bearer drive-token"
            if request.method == "DELETE":
                if self.drive_gone:
                    return httpx.Response(404)
                self.deleted.append(f"drive:{path}")
                return httpx.Response(204)
            if request.method == "GET":
                return httpx.Response(200, json={"files": []})
            meta = json.loads(request.content)
            return httpx.Response(200, json={"id": f"folder-{meta['name']}"})
        if url.startswith("https://www.googleapis.com/upload/drive/v3/files"):
            return httpx.Response(200, json={"id": "drive-file-9"})
        return httpx.Response(404)


def _events(client: TestClient, h: dict[str, str], type_: str, document_id: str) -> list[Any]:
    rows = _ok(client.get("/api/v1/tenant/events", params={"type": type_}, headers=h), 200)
    return [e for e in rows if e["entity_id"] == document_id]


def test_mirror_copies_are_deleted_with_journal(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = bearer(login(client, world, "mdadmin"))
    settings = _settings(database, redis_url)
    fake = FakeMirrors()
    for kind, body in (
        ("paperless", {"enabled": True, "base_url": PAPERLESS_URL, "secret": "paperless-token"}),
        (
            "google_drive",
            {
                "enabled": True,
                "secret": json.dumps({"client_secret": "s", "refresh_token": "r"}),
                "options": {"root_folder_id": "root", "client_id": "c"},
            },
        ),
    ):
        _ok(client.put(f"/api/v1/dms-connections/{kind}", json=body, headers=h), 200)
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("beleg.txt", b"Beleg zum Loeschen", "text/plain")},
            headers=h,
        )
    )
    url = f"/api/v1/documents/{doc['id']}"

    async def run_mirror() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            await mirror_once(settings, client=http, blobs=BlobStore(settings))

    asyncio.run(run_mirror())
    mirrors = {m["kind"]: m for m in _ok(client.get(url, headers=h), 200)["mirrors"]}
    assert mirrors["paperless"]["status"] == "done"
    assert mirrors["paperless"]["external_ref"] == "77"
    assert mirrors["google_drive"]["external_ref"] == "drive-file-9"

    # Still locked: no released profile (6.9.5), the mirrors alone do not change that.
    assert client.delete(url, headers=h).status_code == 409
    profile = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"mirror_{RUN}",
                "legal_basis": "Testprofil ohne Rechtsquelle",
                "retention_years": 1,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )
    _ok(
        client.patch(
            url,
            json={"retention_profile_id": profile["id"], "retention_until": "2020-12-31"},
            headers=h,
        ),
        200,
    )
    second = bearer(login(client, world, "mdsecond"))
    _ok(client.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=second), 200)

    queued: list[MirrorDeletionJob] = []

    def fake_enqueue(jobs: list[MirrorDeletionJob]) -> int:
        queued.extend(jobs)
        return len(jobs)

    monkeypatch.setattr(mirror_deletion, "enqueue", fake_enqueue)
    assert client.delete(url, headers=h).status_code == 204
    assert client.get(url, headers=h).status_code == 404
    assert {(j.kind, j.external_ref) for j in queued} == {
        ("paperless", "77"),
        ("google_drive", "drive-file-9"),
    }
    assert all(j.tenant_id == world.tenant_a and str(j.document_id) == doc["id"] for j in queued)
    requested = _events(client, h, "document.mirror_delete_requested", doc["id"])
    assert {e["payload"]["mirror"] for e in requested} == {"paperless", "google_drive"}
    assert all(e["actor_user_id"] == str(world.users["mdadmin"]) for e in requested)
    deleted = _events(client, h, "document.deleted", doc["id"])
    assert len(deleted) == 1
    assert deleted[0]["payload"]["mirror_deletions"] == 2

    paperless_job = next(j for j in queued if j.kind == "paperless")
    drive_job = next(j for j in queued if j.kind == "google_drive")

    async def run_delete(job: MirrorDeletionJob, attempt: int) -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            return await mirror_deletion.delete_mirror_once(
                settings, job, client=http, attempt=attempt
            )

    # First attempt fails: logged with attempt and error, raised for the Celery retry.
    fake.fail_delete = True
    with pytest.raises(MirrorDeletionError):
        asyncio.run(run_delete(paperless_job, 1))
    failed = _events(client, h, "document.mirror_delete_failed", doc["id"])
    assert len(failed) == 1
    assert failed[0]["payload"]["attempt"] == 1
    assert failed[0]["payload"]["mirror"] == "paperless"
    assert failed[0]["payload"]["error"] == "delete: HTTP 503"
    assert fake.deleted == []

    fake.fail_delete = False
    assert asyncio.run(run_delete(paperless_job, 2)) == "deleted"
    fake.drive_gone = True
    assert asyncio.run(run_delete(drive_job, 1)) == "already_gone"
    assert fake.deleted == ["paperless:/api/documents/77/"]
    done = {
        e["payload"]["mirror"]: e["payload"]
        for e in _events(client, h, "document.mirror_deleted", doc["id"])
    }
    assert done["paperless"]["result"] == "deleted"
    assert done["paperless"]["attempt"] == 2
    assert done["paperless"]["external_ref"] == "77"
    assert done["paperless"]["deleted_at"]
    assert done["google_drive"]["result"] == "already_gone"
    assert done["google_drive"]["external_ref"] == "drive-file-9"

    # A disabled connection cannot delete: journaled as failure, nothing silently dropped.
    _ok(
        client.put(
            "/api/v1/dms-connections/google_drive",
            json={"enabled": False, "options": {"root_folder_id": "root", "client_id": "c"}},
            headers=h,
        ),
        200,
    )
    with pytest.raises(MirrorDeletionError):
        asyncio.run(run_delete(drive_job, 2))
    failed = _events(client, h, "document.mirror_delete_failed", doc["id"])
    assert any(
        e["payload"]["mirror"] == "google_drive" and "nicht aktiv" in e["payload"]["error"]
        for e in failed
    )
