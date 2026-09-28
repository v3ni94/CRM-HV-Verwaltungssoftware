"""A43 (6.9.5, M6-03, operator decision 26.09.2026): after the platform deletion of a document
with a released, expired retention profile the Drive copy is deleted (permanent, fallback
trash) and the Paperless document is kept and tagged "gelöscht". The lock without such a
profile is unchanged (test_m6_documents); here the journal per mirror step is checked with
fake clients: step rows and request events in the deleting transaction, the Celery hand-over,
Drive delete success, failure with retry, trash fallback and "already gone", Paperless tag
creation and assignment, the deletion state "offen" until both steps are done, the retry
endpoint and tenant separation."""

import asyncio
import json
import uuid
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
        a, _ = await services.provision_tenant(factory, slug=f"mdel-{RUN}", name=f"Spiegel {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"me-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("mdmiradmin", a), ("mdsecond", a), ("mdmirother", b)]:
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
    """Paperless and Drive: upload for the mirror job, tag (Paperless) and DELETE or trash
    (Drive) for the deletion job."""

    def __init__(self) -> None:
        self.fail_tag = False
        self.drive_refuse_delete = False
        self.drive_gone = False
        self.deleted: list[str] = []
        self.trashed: list[str] = []
        self.tags: dict[int, str] = {3: "mhvp:tenant:x"}
        self.document_tags: dict[str, list[int]] = {"77": [3]}
        self.tag_created: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        if url.startswith(f"{PAPERLESS_URL}/api/"):
            assert request.headers["authorization"] == "Token paperless-token"
            assert request.method != "DELETE", "Paperless documents are kept (M6-03)"
            if path.endswith("/post_document/"):
                return httpx.Response(200, json="task-9")
            if path.endswith("/tasks/"):
                return httpx.Response(200, json=[{"status": "SUCCESS", "related_document": 77}])
            if path == "/api/tags/":
                if request.method == "GET":
                    name = request.url.params["name__iexact"]
                    hits = [{"id": i, "name": n} for i, n in self.tags.items() if n == name]
                    return httpx.Response(200, json={"results": hits})
                if self.fail_tag:
                    return httpx.Response(503)
                name = json.loads(request.content)["name"]
                new_id = max(self.tags) + 1
                self.tags[new_id] = name
                self.tag_created.append(name)
                return httpx.Response(201, json={"id": new_id})
            if path.startswith("/api/documents/"):
                doc_id = path.split("/")[3]
                if doc_id not in self.document_tags:
                    return httpx.Response(404)
                if request.method == "GET":
                    return httpx.Response(200, json={"id": 77, "tags": self.document_tags[doc_id]})
                if request.method == "PATCH":
                    if self.fail_tag:
                        return httpx.Response(503)
                    self.document_tags[doc_id] = json.loads(request.content)["tags"]
                    return httpx.Response(200, json={"id": 77})
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
                if self.drive_refuse_delete:
                    return httpx.Response(403)
                self.deleted.append(f"drive:{path}")
                return httpx.Response(204)
            if request.method == "PATCH":
                if self.drive_gone:
                    return httpx.Response(404)
                assert json.loads(request.content) == {"trashed": True}
                self.trashed.append(f"drive:{path}")
                return httpx.Response(200, json={"id": path.rsplit("/", 1)[1]})
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
    h = bearer(login(client, world, "mdmiradmin"))
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
    assert all(e["actor_user_id"] == str(world.users["mdmiradmin"]) for e in requested)
    deleted = _events(client, h, "document.deleted", doc["id"])
    assert len(deleted) == 1
    assert deleted[0]["payload"]["mirror_deletions"] == 2

    paperless_job = next(j for j in queued if j.kind == "paperless")
    drive_job = next(j for j in queued if j.kind == "google_drive")

    # The deletion is "offen" with two open steps (Drive delete, Paperless tag).
    deletions = _ok(client.get("/api/v1/documents/deletions", headers=h), 200)
    mine = next(d for d in deletions if d["document_id"] == doc["id"])
    assert mine["status"] == "open"
    assert mine["requested_by"] == str(world.users["mdmiradmin"])
    assert {(x["kind"], x["action"], x["status"]) for x in mine["steps"]} == {
        ("google_drive", "delete", "open"),
        ("paperless", "tag", "open"),
    }
    other = bearer(login(client, world, "mdmirother"))
    assert _ok(client.get("/api/v1/documents/deletions", headers=other), 200) == []
    assert (
        client.post(f"/api/v1/documents/deletions/{doc['id']}/retry", headers=other).status_code
        == 404
    )

    async def run_delete(job: MirrorDeletionJob, attempt: int) -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            return await mirror_deletion.delete_mirror_once(
                settings, job, client=http, attempt=attempt
            )

    # Paperless, first attempt fails: logged with attempt and error, raised for the retry.
    fake.fail_tag = True
    with pytest.raises(MirrorDeletionError):
        asyncio.run(run_delete(paperless_job, 1))
    failed = _events(client, h, "document.mirror_delete_failed", doc["id"])
    assert len(failed) == 1
    assert failed[0]["payload"]["attempt"] == 1
    assert failed[0]["payload"]["mirror"] == "paperless"
    assert failed[0]["payload"]["error"] == "create tags: HTTP 503"
    assert fake.document_tags["77"] == [3]
    step = next(
        x
        for x in _ok(client.get("/api/v1/documents/deletions", headers=h), 200)
        if x["document_id"] == doc["id"]
    )
    paperless_step = next(x for x in step["steps"] if x["kind"] == "paperless")
    assert paperless_step["status"] == "open"
    assert paperless_step["attempts"] == 1
    assert paperless_step["last_error"] == "create tags: HTTP 503"

    # Second attempt: tag "gelöscht" is created in Paperless and assigned, document kept.
    fake.fail_tag = False
    assert asyncio.run(run_delete(paperless_job, 2)) == "tagged"
    assert fake.tag_created.count("gelöscht") == 1
    deleted_tag = next(i for i, n in fake.tags.items() if n == "gelöscht")
    assert fake.document_tags["77"] == [3, deleted_tag]
    marked = _events(client, h, "document.mirror_marked_deleted", doc["id"])
    assert len(marked) == 1
    assert marked[0]["payload"]["result"] == "tagged"
    assert marked[0]["payload"]["tag"] == "gelöscht"
    assert marked[0]["payload"]["attempt"] == 2
    # Idempotent: a repeated run assigns nothing twice and creates no second tag.
    assert asyncio.run(run_delete(paperless_job, 3)) == "tagged"
    assert fake.tag_created.count("gelöscht") == 1
    assert fake.document_tags["77"] == [3, deleted_tag]

    # Still "offen": the Drive step is open. Retry endpoint re-queues only that step.
    queued.clear()
    retried = _ok(client.post(f"/api/v1/documents/deletions/{doc['id']}/retry", headers=h), 200)
    assert retried["status"] == "open"
    assert [(j.kind, j.external_ref) for j in queued] == [("google_drive", "drive-file-9")]

    # Drive: permanent delete refused (403), fallback to the trash, journal says which.
    fake.drive_refuse_delete = True
    assert asyncio.run(run_delete(drive_job, 1)) == "trashed"
    assert fake.deleted == []
    assert fake.trashed == ["drive:/drive/v3/files/drive-file-9"]
    done = _events(client, h, "document.mirror_deleted", doc["id"])
    assert len(done) == 1
    assert done[0]["payload"]["result"] == "trashed"
    assert "Papierkorb" in done[0]["payload"]["note"]
    assert done[0]["payload"]["external_ref"] == "drive-file-9"
    assert done[0]["payload"]["completed_at"]

    # Both steps done: the deletion is closed.
    closed = next(
        x
        for x in _ok(client.get("/api/v1/documents/deletions", headers=h), 200)
        if x["document_id"] == doc["id"]
    )
    assert closed["status"] == "done"
    assert {x["kind"]: x["result"] for x in closed["steps"]} == {
        "google_drive": "trashed",
        "paperless": "tagged",
    }
    assert [
        d["document_id"]
        for d in _ok(
            client.get("/api/v1/documents/deletions", params={"status": "open"}, headers=h), 200
        )
    ].count(doc["id"]) == 0
    # A finished deletion has no open step to retry.
    queued.clear()
    _ok(client.post(f"/api/v1/documents/deletions/{doc['id']}/retry", headers=h), 200)
    assert queued == []


def test_drive_permanent_delete_and_already_gone(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive: permanent delete is preferred; a copy that is gone already is journaled as
    such; a disabled connection is a journaled failure, never a silent drop."""
    h = bearer(login(client, world, "mdmiradmin"))
    settings = _settings(database, redis_url)
    fake = FakeMirrors()

    async def run_delete(job: MirrorDeletionJob, attempt: int) -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            return await mirror_deletion.delete_mirror_once(
                settings, job, client=http, attempt=attempt
            )

    _ok(
        client.put(
            "/api/v1/dms-connections/google_drive",
            json={
                "enabled": True,
                "secret": json.dumps({"client_secret": "s", "refresh_token": "r"}),
                "options": {"root_folder_id": "root", "client_id": "c"},
            },
            headers=h,
        ),
        200,
    )
    job = MirrorDeletionJob(
        tenant_id=world.tenant_a,
        document_id=uuid.uuid4(),
        kind="google_drive",
        external_ref="drive-file-1",
    )
    assert asyncio.run(run_delete(job, 1)) == "deleted"
    assert fake.deleted == ["drive:/drive/v3/files/drive-file-1"]
    assert fake.trashed == []
    done = _events(client, h, "document.mirror_deleted", str(job.document_id))
    assert done[0]["payload"]["result"] == "deleted"
    assert "note" not in done[0]["payload"]

    fake.drive_gone = True
    gone = MirrorDeletionJob(
        tenant_id=world.tenant_a,
        document_id=uuid.uuid4(),
        kind="google_drive",
        external_ref="drive-file-2",
    )
    assert asyncio.run(run_delete(gone, 1)) == "already_gone"

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
        asyncio.run(run_delete(job, 2))
    failed = _events(client, h, "document.mirror_delete_failed", str(job.document_id))
    assert failed[0]["payload"]["mirror"] == "google_drive"
    assert "nicht aktiv" in failed[0]["payload"]["error"]
