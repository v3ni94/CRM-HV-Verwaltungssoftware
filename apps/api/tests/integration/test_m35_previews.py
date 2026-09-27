"""M35-02 technical preparation: preview image takeover (`mhvp.objektakte.previews`). Files
from an objektakte `/data/previews` tree land in the object store, a document without a file
is rendered from an image original or reported, a second run skips what is done, an
interrupted run resumes at its cursor, the endpoints serve state and image with the
objektakte permission keys, tenant separation over RLS."""

from __future__ import annotations

import asyncio
import io
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.models import Document, DocumentSource, StorageKind, TextStatus
from mhvp.main import create_app
from mhvp.objektakte import previews, previews_routers
from mhvp.objektakte.models import ObjektaktePreviewImportRun
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte/previews"


class MemoryStore:
    def __init__(self, fail_keys: set[str] | None = None) -> None:
        self.blobs: dict[str, bytes] = {}
        self.fail_keys = fail_keys or set()

    def put(self, key: str, data: bytes, mime_type: str, sha256: str) -> None:
        if key in self.fail_keys:
            raise RuntimeError("store down")
        self.blobs[key] = data

    def get(self, key: str) -> bytes:
        return self.blobs[key]


def _jpeg(width: int = 40, height: int = 20) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 10, 10)).save(out, "JPEG")
    return out.getvalue()


def _png(width: int = 3000, height: int = 1000) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (10, 200, 10)).save(out, "PNG")
    return out.getvalue()


async def _doc(session: Any, tenant_id: uuid.UUID, source_id: str, **overrides: Any) -> Document:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "title": f"Doc {source_id}",
        "filename": f"doc-{source_id}.pdf",
        "mime_type": "application/pdf",
        "size": 10,
        "sha256": uuid.uuid4().hex + uuid.uuid4().hex,
        "storage": StorageKind.GOOGLE_DRIVE,
        "storage_ref": f"drive-{source_id}",
        "text_status": TextStatus.PENDING,
        "source": DocumentSource.IMPORT,
        "visibility": ["tenant"],
        "source_system": "objektakte",
        "source_id": source_id,
    }
    values.update(overrides)
    doc = Document(**values)
    session.add(doc)
    await session.flush()
    return doc


async def _world(settings: Any) -> tuple[World, dict[str, uuid.UUID]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=f"prev-{RUN}", name=f"Prev {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"prevb-{RUN}", name=f"Prev B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("prevadmin", a, "tenant_admin"),
            ("prevreader", a, "read_only"),
            ("prevother", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        async with tenant_transaction(factory, a) as session:
            ids["with_files"] = (await _doc(session, a, "1001")).id
            ids["image"] = (await _doc(session, a, "1002", mime_type="image/png")).id
            ids["pdf_no_file"] = (await _doc(session, a, "1003")).id
            ids["evil"] = (await _doc(session, a, "../1001")).id
        async with tenant_transaction(factory, b) as session:
            ids["other"] = (await _doc(session, b, "1001")).id
        return world, ids
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world_and_ids(database: Database, redis_url: str) -> tuple[World, dict[str, uuid.UUID]]:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def previews_dir(tmp_path: Path) -> Path:
    root = tmp_path / "previews"
    (root / "1001").mkdir(parents=True)
    (root / "1001" / "0001.jpg").write_bytes(_jpeg())
    (root / "1001" / "0002.jpg").write_bytes(_jpeg(30, 30))
    (root / "1001" / "notes.txt").write_text("ignored")
    return root


async def _run(
    settings: Any,
    tenant_id: uuid.UUID,
    store: MemoryStore,
    *,
    previews_dir: Path | None,
    render_missing: bool = False,
    fetch: Any = None,
    resume_id: uuid.UUID | None = None,
    max_documents: int | None = None,
) -> dict[str, Any]:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            resume = await session.get(ObjektaktePreviewImportRun, resume_id) if resume_id else None
            run = await previews.import_previews(
                session,
                store,
                tenant_id,
                previews_dir=str(previews_dir) if previews_dir else None,
                render_missing=render_missing,
                fetch_original=fetch,
                resume=resume,
                max_documents=max_documents,
            )
            return previews.run_dict(run)
    finally:
        await engine.dispose()


async def _meta(settings: Any, tenant_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, Any]:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            doc = await session.get(Document, document_id)
            assert doc is not None
            return dict((doc.source_meta or {}).get("preview") or {})
    finally:
        await engine.dispose()


async def _reset(settings: Any, tenant_id: uuid.UUID) -> None:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            for doc in (
                await session.scalars(select(Document).where(Document.tenant_id == tenant_id))
            ).all():
                meta = dict(doc.source_meta or {})
                meta.pop("preview", None)
                doc.source_meta = meta or None
            for run in (
                await session.scalars(
                    select(ObjektaktePreviewImportRun).where(
                        ObjektaktePreviewImportRun.tenant_id == tenant_id
                    )
                )
            ).all():
                await session.delete(run)
    finally:
        await engine.dispose()


def test_import_copies_files_renders_images_and_reports_the_rest(
    database: Database,
    redis_url: str,
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
    previews_dir: Path,
) -> None:
    settings = _settings(database, redis_url)
    world, ids = world_and_ids
    asyncio.run(_reset(settings, world.tenant_a))
    store = MemoryStore()
    fetched: list[uuid.UUID] = []

    async def fetch(doc: Document) -> bytes:
        fetched.append(doc.id)
        return _png()

    run = asyncio.run(
        _run(
            settings,
            world.tenant_a,
            store,
            previews_dir=previews_dir,
            render_missing=True,
            fetch=fetch,
        )
    )
    assert run["status"] == "done"
    assert run["total"] == 4
    assert run["processed"] == 4
    assert run["imported"] == 1
    assert run["rendered"] == 1
    assert run["missing"] == 2
    assert run["failed"] == 0

    with_files = asyncio.run(_meta(settings, world.tenant_a, ids["with_files"]))
    assert with_files["status"] == "imported"
    assert with_files["pages"] == 2
    assert with_files["storage_ref"] == previews.preview_key(world.tenant_a, ids["with_files"], 1)
    assert store.blobs[with_files["storage_ref"]] == _jpeg()
    assert previews.preview_key(world.tenant_a, ids["with_files"], 2) in store.blobs

    image = asyncio.run(_meta(settings, world.tenant_a, ids["image"]))
    assert image["status"] == "rendered"
    assert image["pages"] == 1
    assert fetched == [ids["image"]]  # only the image original was downloaded
    rendered = Image.open(io.BytesIO(store.blobs[image["storage_ref"]]))
    assert max(rendered.size) == previews.RENDER_LONG_EDGE_PX

    pdf = asyncio.run(_meta(settings, world.tenant_a, ids["pdf_no_file"]))
    assert pdf["status"] == "pending_render"
    assert pdf["reason"] == "no_renderer"
    evil = asyncio.run(_meta(settings, world.tenant_a, ids["evil"]))
    assert evil["status"] == "pending_render"  # source id refused as path, nothing read

    # tenant B untouched (RLS scoped run)
    other = asyncio.run(_meta(settings, world.tenant_b, ids["other"]))
    assert other == {}

    # second run: everything done is skipped, the rest is re-evaluated without a fetcher
    again = asyncio.run(_run(settings, world.tenant_a, store, previews_dir=previews_dir))
    assert again["skipped"] == 2
    assert again["imported"] == 0
    assert again["rendered"] == 0
    assert again["missing"] == 2


def test_failed_store_is_retried_and_interrupted_run_resumes(
    database: Database,
    redis_url: str,
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
    previews_dir: Path,
) -> None:
    settings = _settings(database, redis_url)
    world, ids = world_and_ids
    asyncio.run(_reset(settings, world.tenant_a))
    key = previews.preview_key(world.tenant_a, ids["with_files"], 1)
    broken = MemoryStore(fail_keys={key})
    first = asyncio.run(
        _run(settings, world.tenant_a, broken, previews_dir=previews_dir, max_documents=2)
    )
    assert first["status"] == "running"
    assert first["processed"] == 2
    assert first["last_document_id"] is not None
    failed_so_far = first["failed"]
    assert failed_so_far in (0, 1)  # depends on the id order of the two documents visited

    healthy = MemoryStore()
    resumed = asyncio.run(
        _run(
            settings,
            world.tenant_a,
            healthy,
            previews_dir=previews_dir,
            resume_id=uuid.UUID(first["id"]),
        )
    )
    assert resumed["id"] == first["id"]
    assert resumed["status"] == "done"
    assert resumed["processed"] == 4  # counters continue, the first two are not revisited
    # the document whose store put failed is not final and gets picked up by the next run
    final = asyncio.run(_run(settings, world.tenant_a, healthy, previews_dir=previews_dir))
    assert final["status"] == "done"
    meta = asyncio.run(_meta(settings, world.tenant_a, ids["with_files"]))
    assert meta["status"] == "imported"
    assert key in healthy.blobs


def test_missing_directory_fails_the_run_without_touching_documents(
    database: Database,
    redis_url: str,
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
    tmp_path: Path,
) -> None:
    settings = _settings(database, redis_url)
    world, ids = world_and_ids
    asyncio.run(_reset(settings, world.tenant_a))
    run = asyncio.run(
        _run(settings, world.tenant_a, MemoryStore(), previews_dir=tmp_path / "gibt-es-nicht")
    )
    assert run["status"] == "failed"
    assert run["processed"] == 0
    assert asyncio.run(_meta(settings, world.tenant_a, ids["with_files"])) == {}


@pytest.fixture
def client(
    database: Database, redis_url: str, previews_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, MemoryStore]]:
    store = MemoryStore()
    monkeypatch.setattr(previews_routers, "BlobStore", lambda settings: store)
    settings = _settings(database, redis_url, objektakte_previews_dir=str(previews_dir))
    with TestClient(create_app(settings)) as c:
        yield c, store


def test_endpoints_state_start_and_image(
    database: Database,
    redis_url: str,
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
    client: tuple[TestClient, MemoryStore],
) -> None:
    world, ids = world_and_ids
    asyncio.run(_reset(_settings(database, redis_url), world.tenant_a))
    c, _store = client
    admin = bearer(login(c, world, "prevadmin"))
    reader = bearer(login(c, world, "prevreader"))
    other = bearer(login(c, world, "prevother"))

    state = c.get(f"{BASE}/import", headers=reader)
    assert state.status_code == 200, state.text
    assert state.json()["run"] is None

    denied = c.post(f"{BASE}/import", json={"inline_limit": 10}, headers=reader)
    assert denied.status_code == 403

    started = c.post(f"{BASE}/import", json={"inline_limit": 10}, headers=admin)
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["mode"] == "inline"
    assert body["run"]["imported"] == 1
    assert body["run"]["status"] == "done"

    state = c.get(f"{BASE}/import", headers=reader).json()
    assert state["run"]["id"] == body["run"]["id"]

    image = c.get(f"{BASE}/documents/{ids['with_files']}", params={"page": 2}, headers=reader)
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/jpeg")
    assert image.content == _jpeg(30, 30)
    assert (
        c.get(
            f"{BASE}/documents/{ids['with_files']}", params={"page": 3}, headers=reader
        ).status_code
        == 404
    )
    assert c.get(f"{BASE}/documents/{ids['pdf_no_file']}", headers=reader).status_code == 404
    # tenant separation: the other tenant neither sees the document nor the run
    assert c.get(f"{BASE}/documents/{ids['with_files']}", headers=other).status_code == 404
    assert c.get(f"{BASE}/import", headers=other).json()["run"] is None
    assert c.get(f"{BASE}/import").status_code == 401
