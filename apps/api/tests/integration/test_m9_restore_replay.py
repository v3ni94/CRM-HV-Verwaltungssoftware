"""D47 (M9-03 technical part): a backup restored after a lawful deletion contains the deleted
document again. The exported deletion journal is replayed: the lawfully deleted document is
deleted a second time and recorded, a document under a deletion hold in the restored state is
kept and the refusal is recorded, a document that is absent needs nothing.

The restore is simulated by re-inserting the row and the blob exactly as they were before the
deletion (the dump would contain both). The store code itself is not touched."""

import asyncio
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import Table, insert, select

from mhvp.core.events import DomainEvent
from mhvp.documents import deletion_journal as dj
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import BUCKET, _ok, _settings, _upload

pytestmark = pytest.mark.integration
D = "/api/v1/documents"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rr-{RUN}", name=f"Restore {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("m9rradmin", "m9rrsecond"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _factory(settings: Any) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    return engine, create_session_factory(engine)


async def _snapshot(settings: Any, world: World, document_id: str) -> dict[str, Any]:
    """Row of the document as a dump would hold it (without the generated search vector)."""
    from mhvp.core.db.tenancy import tenant_transaction

    engine, factory = _factory(settings)
    try:
        async with tenant_transaction(factory, world.tenant_a) as session:
            row = (
                (
                    await session.execute(
                        select(Document.__table__).where(Document.__table__.c.id == document_id)
                    )
                )
                .mappings()
                .one()
            )
            return {k: v for k, v in row.items() if k != "search_vector"}
    finally:
        await engine.dispose()


async def _restore(
    settings: Any, world: World, row: dict[str, Any], data: bytes, **overrides: Any
) -> None:
    """Simulated restore: the row (with the backup's state) and the blob come back."""
    from mhvp.core.db.tenancy import tenant_transaction

    engine, factory = _factory(settings)
    try:
        async with tenant_transaction(factory, world.tenant_a) as session:
            await session.execute(
                insert(cast(Table, Document.__table__)).values({**row, **overrides})
            )
        BlobStore(settings).put(row["storage_ref"], data, row["mime_type"], row["sha256"])
    finally:
        await engine.dispose()


async def _events(settings: Any, world: World, type_: str) -> list[DomainEvent]:
    from mhvp.core.db.tenancy import tenant_transaction

    engine, factory = _factory(settings)
    try:
        async with tenant_transaction(factory, world.tenant_a) as session:
            rows = (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.type == type_)
                    .order_by(DomainEvent.occurred_at)
                )
            ).all()
            for r in rows:
                session.expunge(r)
            return list(rows)
    finally:
        await engine.dispose()


def _released_profile(client: TestClient, world: World, h: dict[str, str]) -> str:
    profile = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"restore_{RUN}",
                "legal_basis": "Testprofil ohne Rechtsquelle",
                "retention_years": 1,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )
    second = bearer(login(client, world, "m9rrsecond"))
    _ok(client.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=second), 200)
    return str(profile["id"])


def test_d47_replay_deletion_journal_after_restore(
    client: TestClient, world: World, database: Database, redis_url: str, tmp_path: Path
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "m9rradmin"))
    profile = _released_profile(client, world, h)
    started = datetime.now(UTC) - timedelta(minutes=1)

    lawful_data, held_data = b"Beleg rechtmaessig geloescht", b"Beweisstueck mit Sperre"
    lawful = _ok(_upload(client, h, "beleg.txt", lawful_data, "text/plain"))
    held = _ok(_upload(client, h, "beweis.txt", held_data, "text/plain"))
    for doc in (lawful, held):
        _ok(
            client.patch(
                f"{D}/{doc['id']}",
                json={"retention_profile_id": profile, "retention_until": "2020-12-31"},
                headers=h,
            ),
            200,
        )
    # Backup state: the evidence document carries a deletion hold at backup time.
    _ok(client.post(f"{D}/{held['id']}/hold", json={"reason": "Rechtsstreit D47"}, headers=h), 200)
    lawful_row = asyncio.run(_snapshot(settings, world, lawful["id"]))
    held_row = asyncio.run(_snapshot(settings, world, held["id"]))
    assert held_row["retention_hold_reason"] == "Rechtsstreit D47"

    # After the backup: the hold is cleared and both documents are lawfully deleted; a refusal
    # before that is recorded too (D46) and must not delete anything on replay.
    refused = client.delete(f"{D}/{held['id']}", headers=h)
    assert refused.status_code == 409
    _ok(
        client.request(
            "DELETE", f"{D}/{held['id']}/hold", json={"reason": "Verfahren beendet"}, headers=h
        ),
        200,
    )
    assert client.delete(f"{D}/{lawful['id']}", headers=h).status_code == 204
    assert client.delete(f"{D}/{held['id']}", headers=h).status_code == 204

    # Step 1 of the runbook: export the journal before the restore.
    engine, factory = _factory(settings)
    try:
        journal = asyncio.run(
            dj.export_journal(factory, since=started, tenant_ids=[world.tenant_a])
        )
    finally:
        asyncio.run(engine.dispose())
    path = tmp_path / "journal.json"
    dj.write_journal(journal, path)
    journal = dj.read_journal(path)
    types = [e["type"] for e in journal["entries"]]
    assert types.count("document.deleted") == 2
    assert "document.deletion_refused" in types
    assert "document.hold_set" in types
    assert "document.hold_cleared" in types
    deleted_entries = [e for e in journal["entries"] if e["type"] == "document.deleted"]
    assert {e["document_id"] for e in deleted_entries} == {lawful["id"], held["id"]}
    assert all(e["payload"]["sha256"] for e in deleted_entries)

    # Step 2: restore brings both rows and blobs back in their backup state (hold included).
    asyncio.run(_restore(settings, world, lawful_row, lawful_data))
    asyncio.run(_restore(settings, world, held_row, held_data))
    assert client.get(f"{D}/{lawful['id']}", headers=h).status_code == 200
    assert client.get(f"{D}/{held['id']}", headers=h).status_code == 200

    # Step 3: dry run changes nothing.
    engine, factory = _factory(settings)
    try:
        dry = asyncio.run(dj.replay_journal(factory, journal, BlobStore(settings), apply=False))
        assert dry.counts[dj.OUTCOME_WOULD_DELETE] == 1
        assert dry.counts[dj.OUTCOME_KEPT_HOLD] == 1
        assert client.get(f"{D}/{lawful['id']}", headers=h).status_code == 200
        assert len(asyncio.run(_events(settings, world, "document.deleted"))) == 2

        # Step 3 with apply: the lawful deletion is applied again, the held evidence stays.
        report = asyncio.run(dj.replay_journal(factory, journal, BlobStore(settings), apply=True))
    finally:
        asyncio.run(engine.dispose())
    by_doc = {r.document_id: r for r in report.results if r.document_id}
    assert by_doc[lawful["id"]].outcome == dj.OUTCOME_DELETED
    assert by_doc[held["id"]].outcome == dj.OUTCOME_KEPT_HOLD
    assert "Rechtsstreit D47" in (by_doc[held["id"]].reason or "")
    assert report.counts[dj.OUTCOME_SKIPPED] >= 3  # refusal, hold set, hold cleared
    assert client.get(f"{D}/{lawful['id']}", headers=h).status_code == 404
    assert client.get(f"{D}/{held['id']}", headers=h).status_code == 200
    assert BlobStore(settings).get(held_row["storage_ref"]) == held_data
    assert hashlib.sha256(held_data).hexdigest() == held_row["sha256"]

    # Step 4: the replay is recorded in the event log (deletion and refusal, marked as replay).
    deleted_events = asyncio.run(_events(settings, world, "document.deleted"))
    assert len(deleted_events) == 3
    replayed = deleted_events[-1]
    assert replayed.entity_id is not None
    assert str(replayed.entity_id) == lawful["id"]
    assert replayed.payload["replay"] is True
    assert replayed.payload["journal_event_id"] in {e["event_id"] for e in deleted_entries}
    refusals = asyncio.run(_events(settings, world, "document.deletion_refused"))
    assert refusals[-1].payload["replay"] is True
    assert str(refusals[-1].entity_id) == held["id"]

    # A second replay of the same journal is idempotent: nothing left to delete.
    engine, factory = _factory(settings)
    try:
        again = asyncio.run(dj.replay_journal(factory, journal, BlobStore(settings), apply=True))
    finally:
        asyncio.run(engine.dispose())
    assert again.counts[dj.OUTCOME_ABSENT] == 1
    assert again.counts[dj.OUTCOME_KEPT_HOLD] == 1
    assert client.get(f"{D}/{held['id']}", headers=h).status_code == 200


def test_d47_replay_never_deletes_a_document_with_another_content(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """A row with the same id but a different hash is not the deleted document: it stays."""
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "m9rradmin"))
    profile = _released_profile(client, world, h)
    data = b"Beleg mit anderem Inhalt nach Restore"
    doc = _ok(_upload(client, h, "beleg2.txt", data, "text/plain"))
    _ok(
        client.patch(
            f"{D}/{doc['id']}",
            json={"retention_profile_id": profile, "retention_until": "2020-12-31"},
            headers=h,
        ),
        200,
    )
    row = asyncio.run(_snapshot(settings, world, doc["id"]))
    assert client.delete(f"{D}/{doc['id']}", headers=h).status_code == 204
    journal = {
        "version": dj.JOURNAL_VERSION,
        "entries": [
            {
                "tenant_id": str(world.tenant_a),
                "event_id": "01999999-0000-7000-8000-000000000001",
                "type": "document.deleted",
                "document_id": doc["id"],
                "occurred_at": datetime.now(UTC).isoformat(),
                "actor_user_id": None,
                "payload": {"sha256": "f" * 64},
            }
        ],
    }
    asyncio.run(_restore(settings, world, row, data))
    engine, factory = _factory(settings)
    try:
        report = asyncio.run(dj.replay_journal(factory, journal, BlobStore(settings), apply=True))
    finally:
        asyncio.run(engine.dispose())
    assert report.results[0].outcome == dj.OUTCOME_KEPT_HASH
    assert client.get(f"{D}/{doc['id']}", headers=h).status_code == 200
