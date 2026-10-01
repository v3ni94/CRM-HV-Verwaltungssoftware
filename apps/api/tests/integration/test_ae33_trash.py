"""AE33 (AC07-03, 6.9.5, 7.11 S05): document trash. Off by default (final deletion as before);
with the tenant switch a lawful deletion moves the document to the trash, where it is hidden
from every normal route, can be restored (logged) or deleted for good (logged, retention checks
again); a hold set meanwhile keeps it; the daily job deletes what is due; the deletion
checklist and the journal replay know the trash."""

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import func, select

from mhvp.core.config import Settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent
from mhvp.documents import mirror_deletion, trash
from mhvp.documents.blobs import BlobStore
from mhvp.documents.deletion_journal import export_journal, parse_since, replay_journal
from mhvp.documents.models import Document
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-ae33-trash"


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
        a, _ = await services.provision_tenant(factory, slug=f"ae33a-{RUN}", name=f"AE33 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae33b-{RUN}", name=f"AE33 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae33admin", a, "tenant_admin"),
            ("ae33second", a, "tenant_admin"),
            ("ae33third", a, "tenant_admin"),
            ("ae33view", a, "read_only"),
            ("ae33other", b, "tenant_admin"),
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


def _run_db(
    settings: Settings, tenant_id: uuid.UUID, work: Callable[[Any], Coroutine[Any, Any, Any]]
) -> Any:
    async def go() -> Any:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _events(settings: Settings, tenant_id: uuid.UUID, type_: str, doc_id: str) -> list[Any]:
    async def work(session: Any) -> list[Any]:
        rows = await session.scalars(
            select(DomainEvent)
            .where(DomainEvent.type == type_, DomainEvent.entity_id == uuid.UUID(doc_id))
            .order_by(DomainEvent.occurred_at)
        )
        return [dict(e.payload) for e in rows.all()]

    return _run_db(settings, tenant_id, work)  # type: ignore[no-any-return]


def _lawful(client: TestClient, world: World, name: str, content: bytes) -> dict[str, Any]:
    """A document whose released retention profile expired: deletable."""
    h = bearer(login(client, world, "ae33admin"))
    second = bearer(login(client, world, "ae33second"))
    doc = _ok(
        client.post(
            "/api/v1/documents", files={"file": (f"{name}.txt", content, "text/plain")}, headers=h
        ),
        201,
    )
    profile = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"ae33_{name}_{RUN}",
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
            f"/api/v1/documents/{doc['id']}",
            json={"retention_profile_id": profile["id"], "retention_until": "2020-12-31"},
            headers=h,
        )
    )
    _ok(client.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=second))
    return doc  # type: ignore[no-any-return]


def _switch(client: TestClient, world: World, enabled: bool, days: int = 30) -> dict[str, Any]:
    h = bearer(login(client, world, "ae33admin"))
    return _ok(  # type: ignore[no-any-return]
        client.put(
            "/api/v1/documents/trash-settings",
            json={"enabled": enabled, "retention_days": days},
            headers=h,
        )
    )


def test_trash_off_by_default_deletion_stays_final(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae33admin"))
    settings = _ok(client.get("/api/v1/documents/trash-settings", headers=h))
    assert settings == {"enabled": False, "retention_days": 30, "proposed_days": 30}
    doc = _lawful(client, world, "final", b"Beleg final AE33")
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 404
    assert _ok(client.get("/api/v1/documents/trash", headers=h)) == []
    assert _events(_settings_for(client), world.tenant_a, "document.trashed", doc["id"]) == []
    checklist = _ok(client.get(f"/api/v1/documents/deletions/{doc['id']}/checklist", headers=h))
    status = {i["target"]: i["status"] for i in checklist["items"]}
    assert status["trash"] == "not_applicable"
    assert checklist["items"][0]["target"] == "trash"
    assert checklist["purge_at"] is None


def _settings_for(client: TestClient) -> Settings:
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    return settings


def test_trash_settings_permissions_validation_and_tenant_separation(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "ae33admin"))
    viewer = bearer(login(client, world, "ae33view"))
    other = bearer(login(client, world, "ae33other"))
    url = "/api/v1/documents/trash-settings"
    assert client.put(url, json={"enabled": True}, headers=viewer).status_code == 403
    assert (
        client.put(url, json={"enabled": True, "retention_days": 0}, headers=admin).status_code
        == 422
    )
    assert (
        client.put(url, json={"enabled": True, "retention_days": 366}, headers=admin).status_code
        == 422
    )
    assert client.put(url, json={"enabled": True, "x": 1}, headers=admin).status_code == 422
    assert client.get(url, params={"x": "1"}, headers=admin).status_code == 422
    saved = _ok(client.put(url, json={"enabled": True, "retention_days": 14}, headers=admin))
    assert saved == {"enabled": True, "retention_days": 14, "proposed_days": 30}
    assert _ok(client.get(url, headers=other))["enabled"] is False
    assert _ok(client.get(url, headers=viewer))["retention_days"] == 14
    _switch(client, world, False)


def test_trash_restore_and_purge_flow(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = bearer(login(client, world, "ae33admin"))
    viewer = bearer(login(client, world, "ae33view"))
    other = bearer(login(client, world, "ae33other"))
    settings = _settings_for(client)
    queued: list[Any] = []
    monkeypatch.setattr(mirror_deletion, "enqueue", lambda jobs: queued.extend(jobs) or len(jobs))
    _switch(client, world, True, 30)
    doc = _lawful(client, world, "flow", b"Beleg Papierkorb AE33")
    ref = _run_db(settings, world.tenant_a, _storage_ref(doc["id"]))
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 204

    # Hidden everywhere, but nothing is removed.
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 404
    assert client.get(f"/api/v1/documents/{doc['id']}/content", headers=h).status_code == 404
    listed = _ok(client.get("/api/v1/documents", params={"page_size": 200}, headers=h))
    ids = {d["id"] for d in (listed["items"] if isinstance(listed, dict) else listed)}
    assert doc["id"] not in ids
    assert BlobStore(settings).exists(ref)
    assert _run_db(settings, world.tenant_a, _row_exists(doc["id"])) is True

    trash_list = _ok(client.get("/api/v1/documents/trash", headers=h))
    entry = next(e for e in trash_list if e["document_id"] == doc["id"])
    assert entry["status"] == "in_trash"
    assert entry["blocker"] is None
    assert 28 <= entry["days_left"] <= 30
    assert entry["deleted_by"] == str(world.users["ae33admin"])
    assert client.get("/api/v1/documents/trash", headers=viewer).status_code == 403
    assert all(
        e["document_id"] != doc["id"]
        for e in _ok(client.get("/api/v1/documents/trash", headers=other))
    )
    assert client.get("/api/v1/documents/trash", params={"x": "1"}, headers=h).status_code == 422

    trashed = _events(settings, world.tenant_a, "document.trashed", doc["id"])
    assert len(trashed) == 1
    assert trashed[0]["retention_days"] == 30

    checklist_url = f"/api/v1/documents/deletions/{doc['id']}/checklist"
    checklist = _ok(client.get(checklist_url, headers=h))
    assert checklist["status"] == "in_trash"
    assert checklist["purge_at"] is not None
    status = {i["target"]: i["status"] for i in checklist["items"]}
    assert status["trash"] == "open"
    assert status["index"] == status["original"] == status["embeddings"] == "pending"
    # The follow up must never touch a document in the trash.
    follow = _ok(client.post(f"/api/v1/documents/deletions/{doc['id']}/follow-up", headers=h))
    assert follow["status"] == "in_trash"
    assert BlobStore(settings).exists(ref)

    # Restore: permission, tenant, validation, log.
    restore_url = f"/api/v1/documents/trash/{doc['id']}/restore"
    assert client.post(restore_url, json={"reason": "Irrtum"}, headers=viewer).status_code == 403
    assert client.post(restore_url, json={"reason": "Irrtum"}, headers=other).status_code == 404
    assert client.post(restore_url, json={"reason": "x"}, headers=h).status_code == 422
    restored = _ok(client.post(restore_url, json={"reason": "Versehentlich gelöscht"}, headers=h))
    assert restored["id"] == doc["id"]
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 200
    assert client.post(restore_url, json={"reason": "Nochmal"}, headers=h).status_code == 404
    log = _events(settings, world.tenant_a, "document.restored", doc["id"])
    assert len(log) == 1
    assert log[0]["reason"] == "Versehentlich gelöscht"
    assert all(
        e["document_id"] != doc["id"] for e in _ok(client.get("/api/v1/documents/trash", headers=h))
    )

    # Trash again and delete for good before the period ended.
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 204
    purge_url = f"/api/v1/documents/trash/{doc['id']}/purge"
    assert client.post(purge_url, json={"reason": "Löschwunsch"}, headers=viewer).status_code == 403
    assert client.post(purge_url, json={"reason": "Löschwunsch"}, headers=other).status_code == 404
    assert client.post(purge_url, json={"reason": "Löschwunsch"}, headers=h).status_code == 204
    assert client.post(purge_url, json={"reason": "Löschwunsch"}, headers=h).status_code == 404
    assert not BlobStore(settings).exists(ref)
    assert _run_db(settings, world.tenant_a, _row_exists(doc["id"])) is False
    deleted = _events(settings, world.tenant_a, "document.deleted", doc["id"])
    assert len(deleted) == 1
    assert deleted[0]["from_trash"] is True
    assert deleted[0]["early"] is True
    assert deleted[0]["reason"] == "Löschwunsch"
    assert deleted[0]["storage_ref"] == ref
    final = _ok(client.get(checklist_url, headers=h))
    assert final["status"] == "done"
    assert final["items"][0]["target"] == "trash"
    assert final["items"][0]["status"] == "done"
    assert final["purge_at"] is None
    _switch(client, world, False)


def _storage_ref(doc_id: str) -> Callable[[Any], Coroutine[Any, Any, str]]:
    async def work(session: Any) -> str:
        return str(
            await session.scalar(
                select(Document.storage_ref).where(Document.id == uuid.UUID(doc_id))
            )
        )

    return work


def _row_exists(doc_id: str) -> Callable[[Any], Coroutine[Any, Any, bool]]:
    async def work(session: Any) -> bool:
        with trash.trashed_visible(session):
            count = await session.scalar(
                select(func.count()).select_from(Document).where(Document.id == uuid.UUID(doc_id))
            )
        return bool(count)

    return work


def _set_hold(doc_id: str, reason: str | None) -> Callable[[Any], Coroutine[Any, Any, None]]:
    async def work(session: Any) -> None:
        with trash.trashed_visible(session):
            document = await session.get(Document, uuid.UUID(doc_id))
            assert document is not None
            document.retention_hold_reason = reason

    return work


def _set_purge_at(doc_id: str, when: datetime) -> Callable[[Any], Coroutine[Any, Any, None]]:
    async def work(session: Any) -> None:
        with trash.trashed_visible(session):
            document = await session.get(Document, uuid.UUID(doc_id))
            assert document is not None
            document.purge_at = when

    return work


def test_hold_set_in_the_trash_wins_over_every_deletion(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = bearer(login(client, world, "ae33admin"))
    settings = _settings_for(client)
    monkeypatch.setattr(mirror_deletion, "enqueue", lambda jobs: len(jobs))
    _switch(client, world, True, 7)
    doc = _lawful(client, world, "hold", b"Beleg Sperre AE33")
    ref = _run_db(settings, world.tenant_a, _storage_ref(doc["id"]))
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 204
    # A hold appears while the document waits (for example through a related procedure).
    _run_db(settings, world.tenant_a, _set_hold(doc["id"], "Rechtsstreit AE33"))
    _run_db(
        settings, world.tenant_a, _set_purge_at(doc["id"], datetime.now(UTC) - timedelta(days=1))
    )

    entry = next(
        e
        for e in _ok(client.get("/api/v1/documents/trash", headers=h))
        if e["document_id"] == doc["id"]
    )
    assert entry["status"] == "held"
    assert "Rechtsstreit AE33" in entry["blocker"]
    checklist = _ok(client.get(f"/api/v1/documents/deletions/{doc['id']}/checklist", headers=h))
    assert checklist["status"] == "held"
    # Early purge: 409, refusal logged.
    purge = client.post(
        f"/api/v1/documents/trash/{doc['id']}/purge", json={"reason": "Löschwunsch"}, headers=h
    )
    assert purge.status_code == 409, purge.text
    # The daily job twice: kept, no second refusal event for the same reason.
    for _ in range(2):
        report = asyncio.run(trash.purge_due_all_tenants_once(settings, blobs=BlobStore(settings)))
        assert report["errors"] == []
    assert BlobStore(settings).exists(ref)
    assert _run_db(settings, world.tenant_a, _row_exists(doc["id"])) is True
    refusals = _events(settings, world.tenant_a, "document.deletion_refused", doc["id"])
    # One event for the early purge call; the job twice with the same reason adds none.
    assert len(refusals) == 1
    assert all(r["from_trash"] is True for r in refusals)
    assert _events(settings, world.tenant_a, "document.deleted", doc["id"]) == []

    # Hold lifted (second person in real life): the job deletes it now.
    _run_db(settings, world.tenant_a, _set_hold(doc["id"], None))
    report = asyncio.run(trash.purge_due_all_tenants_once(settings, blobs=BlobStore(settings)))
    assert report["deleted"] >= 1
    assert report["errors"] == []
    assert _run_db(settings, world.tenant_a, _row_exists(doc["id"])) is False
    assert not BlobStore(settings).exists(ref)
    deleted = _events(settings, world.tenant_a, "document.deleted", doc["id"])
    assert len(deleted) == 1
    assert deleted[0]["from_trash"] is True
    assert deleted[0]["early"] is False
    _switch(client, world, False)


def test_daily_job_only_deletes_what_is_due(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = bearer(login(client, world, "ae33admin"))
    settings = _settings_for(client)
    monkeypatch.setattr(mirror_deletion, "enqueue", lambda jobs: len(jobs))
    _switch(client, world, True, 30)
    due = _lawful(client, world, "due", b"Beleg faellig AE33")
    later = _lawful(client, world, "later", b"Beleg spaeter AE33")
    for doc in (due, later):
        assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 204
    _run_db(
        settings, world.tenant_a, _set_purge_at(due["id"], datetime.now(UTC) - timedelta(hours=1))
    )
    report = asyncio.run(trash.purge_due_all_tenants_once(settings, blobs=BlobStore(settings)))
    assert report["errors"] == []
    assert _run_db(settings, world.tenant_a, _row_exists(due["id"])) is False
    assert _run_db(settings, world.tenant_a, _row_exists(later["id"])) is True
    assert BlobStore(settings).exists(
        _run_db(settings, world.tenant_a, _storage_ref_trashed(later["id"]))
    )
    # Tidy up: restore the second one so it does not stay in the shared trash.
    _ok(
        client.post(
            f"/api/v1/documents/trash/{later['id']}/restore",
            json={"reason": "Aufräumen"},
            headers=h,
        )
    )
    _switch(client, world, False)


def _storage_ref_trashed(doc_id: str) -> Callable[[Any], Coroutine[Any, Any, str]]:
    async def work(session: Any) -> str:
        with trash.trashed_visible(session):
            return str(
                await session.scalar(
                    select(Document.storage_ref).where(Document.id == uuid.UUID(doc_id))
                )
            )

    return work


def test_proposal_execution_uses_the_trash(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = bearer(login(client, world, "ae33admin"))
    second = bearer(login(client, world, "ae33second"))
    third = bearer(login(client, world, "ae33third"))
    settings = _settings_for(client)
    monkeypatch.setattr(mirror_deletion, "enqueue", lambda jobs: len(jobs))
    _switch(client, world, True, 30)
    doc = _lawful(client, world, "proposal", b"Beleg Vorschlag AE33")
    proposal = _ok(client.post("/api/v1/deletion-proposals", headers=h), 201)
    assert doc["id"] in {i["document_id"] for i in proposal["items"]}
    _ok(client.post(f"/api/v1/deletion-proposals/{proposal['id']}/approve", headers=second))
    result = _ok(client.post(f"/api/v1/deletion-proposals/{proposal['id']}/execute", headers=third))
    assert result["deleted"] >= 1
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 404
    assert _run_db(settings, world.tenant_a, _row_exists(doc["id"])) is True
    trashed = _events(settings, world.tenant_a, "document.trashed", doc["id"])
    assert len(trashed) == 1
    assert trashed[0]["proposal_id"] == proposal["id"]
    assert trashed[0]["approved_by"] == str(world.users["ae33second"])
    # A trashed document is not proposed again.
    assert client.post("/api/v1/deletion-proposals", headers=h).status_code in (201, 409)
    again = _ok(client.get(f"/api/v1/deletion-proposals/{proposal['id']}", headers=h))
    assert all(i["document_id"] != doc["id"] or i["status"] == "deleted" for i in again["items"])
    purged = client.post(
        f"/api/v1/documents/trash/{doc['id']}/purge", json={"reason": "Fristende"}, headers=h
    )
    assert purged.status_code == 204
    _switch(client, world, False)


def test_journal_replays_trash_and_restore(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup taken before the trashing holds the document normally; replaying the journal
    puts it into the trash again. A backup taken while it was in the trash is taken out of it
    when the journal says it was restored. A hold wins."""
    h = bearer(login(client, world, "ae33admin"))
    settings = _settings_for(client)
    monkeypatch.setattr(mirror_deletion, "enqueue", lambda jobs: len(jobs))
    _switch(client, world, True, 30)
    doc = _lawful(client, world, "replay", b"Beleg Replay AE33")
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 204

    async def journal(since: str = "2000-01-01") -> dict[str, Any]:
        engine = create_app_engine(settings)
        try:
            return await export_journal(
                create_session_factory(engine),
                since=parse_since(since),
                tenant_ids=[world.tenant_a],
            )
        finally:
            await engine.dispose()

    async def replay(entries: dict[str, Any], apply: bool) -> Any:
        engine = create_app_engine(settings)
        try:
            return await replay_journal(
                create_session_factory(engine), entries, BlobStore(settings), apply=apply
            )
        finally:
            await engine.dispose()

    full = asyncio.run(journal())
    mine = {
        **full,
        "entries": [e for e in full["entries"] if e["document_id"] == doc["id"]],
    }
    assert [e["type"] for e in mine["entries"]] == ["document.trashed"]

    # Backup state: the document is a normal one again.
    _ok(
        client.post(
            f"/api/v1/documents/trash/{doc['id']}/restore", json={"reason": "Backup"}, headers=h
        )
    )
    dry = asyncio.run(replay(mine, False))
    assert [r.outcome for r in dry.results] == ["would_trash"]
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 200
    # Under a hold the journal does not touch it.
    _run_db(settings, world.tenant_a, _set_hold(doc["id"], "Beweissicherung AE33"))
    held = asyncio.run(replay(mine, True))
    assert [r.outcome for r in held.results] == ["kept_hold"]
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 200
    _run_db(settings, world.tenant_a, _set_hold(doc["id"], None))
    applied = asyncio.run(replay(mine, True))
    assert [r.outcome for r in applied.results] == ["trashed"]
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 404
    assert _run_db(settings, world.tenant_a, _row_exists(doc["id"])) is True
    again = asyncio.run(replay(mine, True))
    assert [r.outcome for r in again.results] == ["skipped"]

    # A later "restored" entry wins over the earlier "trashed" entry, and is applied.
    _ok(
        client.post(
            f"/api/v1/documents/trash/{doc['id']}/restore", json={"reason": "Fehler"}, headers=h
        )
    )
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 204
    _ok(
        client.post(
            f"/api/v1/documents/trash/{doc['id']}/restore", json={"reason": "Wieder"}, headers=h
        )
    )
    full2 = asyncio.run(journal())
    mine2 = {
        **full2,
        "entries": [e for e in full2["entries"] if e["document_id"] == doc["id"]],
    }
    kinds = [e["type"] for e in mine2["entries"]]
    assert kinds.count("document.trashed") == 3
    assert kinds[-1] == "document.restored"
    # The state the backup shows: in the trash. The journal restores it.
    _run_db(settings, world.tenant_a, _trash_row(doc["id"]))
    out = asyncio.run(replay(mine2, True))
    outcomes = [r.outcome for r in out.results]
    assert outcomes.count("restored") == 1
    assert "trashed" not in outcomes  # the earlier trash entries are superseded
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 200
    _switch(client, world, False)


def _trash_row(doc_id: str) -> Callable[[Any], Coroutine[Any, Any, None]]:
    async def work(session: Any) -> None:
        document = await session.get(Document, uuid.UUID(doc_id))
        assert document is not None
        now = datetime.now(UTC)
        document.deleted_at, document.purge_at = now, now + timedelta(days=30)

    return work


def test_database_constraint_pairs_trash_columns(client: TestClient, world: World) -> None:
    from sqlalchemy.exc import IntegrityError

    h = bearer(login(client, world, "ae33admin"))
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("pair.txt", b"Beleg Paar AE33", "text/plain")},
            headers=h,
        ),
        201,
    )

    async def work(session: Any) -> None:
        document = await session.get(Document, uuid.UUID(doc["id"]))
        document.deleted_at = datetime.now(UTC)  # purge_at missing

    with pytest.raises(IntegrityError):
        _run_db(_settings_for(client), world.tenant_a, work)
