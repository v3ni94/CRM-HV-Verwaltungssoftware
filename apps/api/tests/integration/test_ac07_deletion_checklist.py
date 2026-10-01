"""AC07 (GA08-08, 7.11 S05, 6.9.5): a lawful deletion is consistent in index, original, DMS
mirrors (Paperless, Drive, fakes) and derivatives (embeddings, AI extracts); the checklist per
target shows the state, the follow up repeats open steps, and "restore plus replay" sets every
target back and deletes again. A restored document under a hold is kept (hold wins), the
follow up never deletes a restored document, and backups are listed as out of scope."""

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
from sqlalchemy import insert, select

from mhvp.core.config import Settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents import deletion_checklist, mirror_deletion
from mhvp.documents.blobs import BlobStore
from mhvp.documents.deletion_journal import export_journal, parse_since, replay_journal
from mhvp.documents.mirror_deletion import MirrorDeletionJob
from mhvp.documents.tasks import mirror_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m6_mirror_deletion import PAPERLESS_URL, FakeMirrors

pytestmark = pytest.mark.integration
BUCKET = "mhvp-ac07-del"


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

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ac07d-{RUN}", name=f"AC07 D {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ac07e-{RUN}", name=f"AC07 E {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ac07dadmin", a, "tenant_admin"),
            ("ac07dsecond", a, "tenant_admin"),
            ("ac07dview", a, "read_only"),
            ("ac07dother", b, "tenant_admin"),
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


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _status(checklist: dict[str, Any]) -> dict[str, str]:
    return {i["target"]: i["status"] for i in checklist["items"]}


async def _derivatives(settings: Settings, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """Embedding chunk, intake run, proposal and learning example of the document."""
    from mhvp.ai.models import (
        AiEmbedding,
        AiExample,
        AiProposal,
        AiTask,
        AiTaskRun,
        EmbeddingSourceKind,
        RunStatus,
    )

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            session.add(
                AiEmbedding(
                    tenant_id=tenant_id,
                    source_kind=EmbeddingSourceKind.DOCUMENT,
                    source_id=document_id,
                    chunk_index=0,
                    chunk_count=1,
                    content_hash="0" * 64,
                    model="test",
                    embedding=[0.0] * 1536,
                )
            )
            run = AiTaskRun(
                tenant_id=tenant_id,
                task=AiTask.CLASSIFY_DOCUMENT,
                prompt_version="t",
                input_hash="1" * 64,
                input_ref={"document_id": str(document_id), "source": "text"},
                output={"summary": "Mieter Max Beispiel schuldet"},
                status=RunStatus.SUCCEEDED,
            )
            session.add(run)
            await session.flush()
            proposal = AiProposal(
                tenant_id=tenant_id,
                task_run_id=run.id,
                entity_type="document_intake",
                context_id=document_id,
                proposed={"summary": "Mieter Max Beispiel schuldet"},
            )
            session.add(proposal)
            await session.flush()
            session.add(
                AiExample(
                    tenant_id=tenant_id,
                    task=AiTask.CLASSIFY_DOCUMENT,
                    features={"text": "Max Beispiel"},
                    result={"category": "x"},
                    proposal_id=proposal.id,
                )
            )
    finally:
        await engine.dispose()


async def _capture(
    settings: Settings, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> dict[str, Any]:
    from mhvp.documents.models import Document, DocumentMirror

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            table = Document.__table__
            cols = [c for c in table.c if c.computed is None]
            doc = (await session.execute(select(*cols).where(table.c.id == document_id))).one()
            mirrors = (
                await session.execute(
                    select(DocumentMirror.__table__).where(
                        DocumentMirror.__table__.c.document_id == document_id
                    )
                )
            ).all()
            return {"document": dict(doc._mapping), "mirrors": [dict(m._mapping) for m in mirrors]}
    finally:
        await engine.dispose()


async def _restore(
    settings: Settings,
    tenant_id: uuid.UUID,
    snapshot: dict[str, Any],
    hold: str | None = None,
) -> None:
    """Simulated restore of the backup taken before the deletion (document row, mirror rows,
    original, derivatives)."""
    from mhvp.documents.models import Document, DocumentMirror

    row = dict(snapshot["document"])
    row["retention_hold_reason"] = hold
    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            await session.execute(insert(Document.__table__).values(**row))
            for mirror in snapshot["mirrors"]:
                await session.execute(insert(DocumentMirror.__table__).values(**mirror))
    finally:
        await engine.dispose()
    BlobStore(settings).put(row["storage_ref"], b"Beleg AC07", "text/plain", row["sha256"])
    await _derivatives(settings, tenant_id, row["id"])


async def _drop(settings: Settings, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
    from mhvp.documents.models import Document

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            document = await session.get(Document, document_id)
            if document is not None:
                await session.delete(document)
    finally:
        await engine.dispose()


def test_deletion_checklist_restore_and_replay(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = bearer(login(client, world, "ac07dadmin"))
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
        _ok(client.put(f"/api/v1/dms-connections/{kind}", json=body, headers=h))
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("ac07.txt", b"Beleg AC07", "text/plain")},
            headers=h,
        ),
        201,
    )
    doc_id = uuid.UUID(doc["id"])
    url = f"/api/v1/documents/{doc['id']}"
    checklist_url = f"/api/v1/documents/deletions/{doc['id']}/checklist"
    # No deletion recorded yet.
    assert client.get(checklist_url, headers=h).status_code == 404

    async def run_mirror() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            await mirror_once(settings, client=http, blobs=BlobStore(settings))

    asyncio.run(run_mirror())
    asyncio.run(_derivatives(settings, world.tenant_a, doc_id))
    profile = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"ac07_{RUN}",
                "legal_basis": "Testprofil ohne Rechtsquelle",
                "retention_years": 1,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.patch(
            url,
            json={"retention_profile_id": profile["id"], "retention_until": "2020-12-31"},
            headers=h,
        )
    )
    second = bearer(login(client, world, "ac07dsecond"))
    _ok(client.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=second))
    snapshot = asyncio.run(_capture(settings, world.tenant_a, doc_id))

    queued: list[MirrorDeletionJob] = []

    def fake_enqueue(jobs: list[MirrorDeletionJob]) -> int:
        queued.extend(jobs)
        return len(jobs)

    monkeypatch.setattr(mirror_deletion, "enqueue", fake_enqueue)
    assert client.delete(url, headers=h).status_code == 204

    # Index, original and derivatives are gone in the deleting transaction; mirrors open.
    first = _ok(client.get(checklist_url, headers=h))
    assert first["status"] == "open"
    assert _status(first) == {
        "trash": "not_applicable",
        "index": "done",
        "original": "done",
        "mirror_paperless": "open",
        "mirror_google_drive": "open",
        "embeddings": "done",
        "ai_extracts": "done",
        "thumbnails": "not_applicable",
        "backup": "out_of_scope",
    }
    # Tenant separation and read permission.
    other = bearer(login(client, world, "ac07dother"))
    assert client.get(checklist_url, headers=other).status_code == 404
    viewer = bearer(login(client, world, "ac07dview"))
    assert client.get(checklist_url, headers=viewer).status_code == 200
    follow_url = f"/api/v1/documents/deletions/{doc['id']}/follow-up"
    assert client.post(follow_url, headers=viewer).status_code == 403
    assert client.post(follow_url, headers=other).status_code == 404
    assert client.get(checklist_url, params={"x": "1"}, headers=h).status_code == 422

    async def run_jobs() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            for job in list(queued):
                await mirror_deletion.delete_mirror_once(settings, job, client=http)
        queued.clear()

    asyncio.run(run_jobs())
    assert _ok(client.get(checklist_url, headers=h))["status"] == "done"

    # Follow up: a leftover original (failed delete) is removed by the Nachlauf.
    BlobStore(settings).put(
        snapshot["document"]["storage_ref"], b"x", "text/plain", snapshot["document"]["sha256"]
    )
    assert _status(_ok(client.get(checklist_url, headers=h)))["original"] == "open"
    after = _ok(client.post(follow_url, headers=h))
    assert after["status"] == "done"
    assert not BlobStore(settings).exists(snapshot["document"]["storage_ref"])

    # Restore from backup: every target is back; the follow up never deletes it.
    journal = asyncio.run(
        export_journal(
            create_session_factory(create_app_engine(settings)),
            since=parse_since("2000-01-01"),
            tenant_ids=[world.tenant_a],
        )
    )
    asyncio.run(_restore(settings, world.tenant_a, snapshot))
    restored = _ok(client.get(checklist_url, headers=h))
    assert restored["status"] == "open"
    assert _status(restored)["index"] == "open"
    assert _status(restored)["embeddings"] == "open"
    assert _status(restored)["ai_extracts"] == "open"
    _ok(client.post(follow_url, headers=h))
    assert client.get(url, headers=h).status_code == 200

    # Replay: deleted again, mirror steps reset to open and queued, derivatives gone.
    async def replay() -> Any:
        engine = create_app_engine(settings)
        try:
            return await replay_journal(
                create_session_factory(engine), journal, BlobStore(settings), apply=True
            )
        finally:
            await engine.dispose()

    asyncio.run(replay())
    assert client.get(url, headers=h).status_code == 404
    replayed = _ok(client.get(checklist_url, headers=h))
    assert {k: v for k, v in _status(replayed).items() if v != "done"} == {
        "trash": "not_applicable",
        "mirror_paperless": "open",
        "mirror_google_drive": "open",
        "thumbnails": "not_applicable",
        "backup": "out_of_scope",
    }
    assert {(j.kind, str(j.document_id)) for j in queued} == {
        ("paperless", doc["id"]),
        ("google_drive", doc["id"]),
    }
    asyncio.run(run_jobs())
    assert _ok(client.get(checklist_url, headers=h))["status"] == "done"

    # Restore under a hold: the replay keeps the document, the checklist says "held".
    asyncio.run(_restore(settings, world.tenant_a, snapshot, hold="Rechtsstreit AC07"))
    asyncio.run(replay())
    held = _ok(client.get(checklist_url, headers=h))
    assert held["status"] == "held"
    assert _status(held)["index"] == "held"
    index_item = next(i for i in held["items"] if i["target"] == "index")
    assert "Rechtsstreit AC07" in index_item["detail"]
    _ok(client.post(follow_url, headers=h))
    assert client.get(url, headers=h).status_code == 200
    assert BlobStore(settings).exists(snapshot["document"]["storage_ref"])
    # Leave no restored document with mirror rows behind for the mirror jobs of other tests.
    asyncio.run(_drop(settings, world.tenant_a, doc_id))


def test_follow_up_job_runs_over_tenants(
    database: Database,
    redis_url: str,
    s3: None,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued: list[MirrorDeletionJob] = []
    monkeypatch.setattr(mirror_deletion, "enqueue", lambda jobs: queued.extend(jobs) or len(jobs))
    report = asyncio.run(
        deletion_checklist.follow_up_all_tenants_once(_settings(database, redis_url))
    )
    assert report["errors"] == []
    assert report["mirror_jobs"] == len(queued)
