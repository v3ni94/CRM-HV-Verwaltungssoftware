"""Preview images of taken over objektakte documents (M35 technical preparation, open question
M35-02, docs/plans/M35-objektakte-uebernahme.md section 3.2).

objektakte renders one JPEG per page under ``<DATA_DIR>/previews/<document_id>/<page>.jpg``
(``apps.pipeline.previews`` there, ``0001.jpg`` ...). This module takes those files over into
the CRM object store (``tenants/<tenant>/documents/<id>/preview/<page>.jpg``) and, where no
file exists, optionally renders a new one from the original. The CRM has no PDF renderer of
its own (only Pillow, used by ``mhvp.handover.images``), so a new render works for image
originals (JPEG, PNG, TIFF, HEIC via pillow-heif) and reports a PDF as ``pending_render``
instead of inventing a picture; adding a PDF renderer (pypdfium2 or similar) is part of the
operator decision M35-02 and is recorded in ``docs/OPEN_QUESTIONS.md``.

Progress and resume: one ``ObjektaktePreviewImportRun`` per run holds counters and the cursor
(``last_document_id``); documents are visited in id order and a document that already carries
``source_meta["preview"]`` with status ``imported`` or ``rendered`` is skipped, so a run that
was interrupted (worker restart, storage outage) continues with the next document. A file that
cannot be read or stored counts as ``failed`` and is retried on the next run (its status is
``failed``, not final).

The document row keeps only a pointer (``source_meta["preview"]``: status, page count, storage
key of page 1, sha256 of page 1, source); never the image itself. Neither the run nor the
document changes any financial or legal content (rule 0.1.7).
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from mhvp.documents.models import Document
from mhvp.objektakte.models import ObjektaktePreviewImportRun, PreviewImportStatus

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "objektakte"
PREVIEW_MIME = "image/jpeg"
PAGE_FILE_RE = re.compile(r"^(\d{1,4})\.jpg$")
# Upper bound of pages taken over per document; objektakte keeps every page, the CRM preview
# needs the first pages only (a reviewer opens the original for the rest).
MAX_PAGES_PER_DOCUMENT = 20
MAX_PREVIEW_BYTES = 5 * 1024 * 1024
RENDER_LONG_EDGE_PX = 1200
RENDER_QUALITY = 80
IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/tiff", "image/heic", "image/heif", "image/webp"}
)

FetchOriginal = Callable[[Document], Awaitable[bytes]]


class PreviewStore(Protocol):
    """The subset of ``mhvp.documents.blobs.BlobStore`` used here (tests pass an in-memory
    implementation, production the S3 store)."""

    def put(self, key: str, data: bytes, mime_type: str, sha256: str) -> None: ...

    def get(self, key: str) -> bytes: ...


def preview_key(tenant_id: uuid.UUID, document_id: uuid.UUID, page_no: int) -> str:
    return f"tenants/{tenant_id}/documents/{document_id}/preview/{page_no:04d}.jpg"


def source_preview_dir(previews_dir: Path, source_id: str) -> Path | None:
    """``<previews_dir>/<objektakte document id>``; a source id that is not a plain integer
    (never the case for objektakte primary keys) is refused so no path outside the directory
    can be built from imported data."""
    if not re.fullmatch(r"\d{1,12}", source_id):
        return None
    return previews_dir / source_id


def list_page_files(directory: Path) -> list[tuple[int, Path]]:
    if not directory.is_dir():
        return []
    pages: list[tuple[int, Path]] = []
    for entry in directory.iterdir():
        match = PAGE_FILE_RE.match(entry.name)
        if match and entry.is_file():
            pages.append((int(match.group(1)), entry))
    pages.sort()
    return pages[:MAX_PAGES_PER_DOCUMENT]


def render_image_preview(data: bytes, *, long_edge_px: int = RENDER_LONG_EDGE_PX) -> bytes:
    """JPEG of an image original scaled to ``long_edge_px`` (same geometry as objektakte's
    ``previews.long_edge_px`` default 1200). Raises ``ValueError`` for unreadable data."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as opened:
            image: Image.Image = ImageOps.exif_transpose(opened) or opened
            image = image.convert("RGB")
            width, height = image.size
            longest = max(width, height)
            if longest > long_edge_px:
                scale = long_edge_px / longest
                image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))
            out = io.BytesIO()
            image.save(out, "JPEG", quality=RENDER_QUALITY, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Bilddaten nicht lesbar") from exc


@dataclass
class PreviewOutcome:
    status: str  # imported | rendered | missing | pending_render | failed | skipped
    pages: int = 0
    detail: str | None = None


def _preview_meta(doc: Document) -> dict[str, Any]:
    return dict((doc.source_meta or {}).get("preview") or {})


def _set_preview_meta(doc: Document, value: dict[str, Any]) -> None:
    meta = dict(doc.source_meta or {})
    meta["preview"] = value
    doc.source_meta = meta
    flag_modified(doc, "source_meta")


def _store_pages(
    store: PreviewStore, tenant_id: uuid.UUID, doc: Document, pages: list[tuple[int, bytes]]
) -> dict[str, Any]:
    first_key: str | None = None
    first_sha: str | None = None
    for page_no, data in pages:
        sha = hashlib.sha256(data).hexdigest()
        key = preview_key(tenant_id, doc.id, page_no)
        store.put(key, data, PREVIEW_MIME, sha)
        if first_key is None:
            first_key, first_sha = key, sha
    return {"pages": len(pages), "storage_ref": first_key, "sha256": first_sha}


async def take_over_document(
    session: AsyncSession,
    store: PreviewStore,
    tenant_id: uuid.UUID,
    doc: Document,
    *,
    previews_dir: Path | None,
    fetch_original: FetchOriginal | None,
    now: datetime,
) -> PreviewOutcome:
    """One document: copy objektakte's page files if present, otherwise render from the
    original when a fetcher is given and the original is an image, otherwise record why."""
    current = _preview_meta(doc)
    if current.get("status") in ("imported", "rendered"):
        return PreviewOutcome("skipped", int(current.get("pages") or 0))

    pages: list[tuple[int, bytes]] = []
    source_dir = (
        source_preview_dir(previews_dir, doc.source_id or "") if previews_dir is not None else None
    )
    if source_dir is not None:
        for page_no, path in list_page_files(source_dir):
            try:
                if path.stat().st_size > MAX_PREVIEW_BYTES:
                    raise OSError("preview file larger than the accepted size")
                pages.append((page_no, path.read_bytes()))
            except OSError as exc:
                log.warning(
                    "preview file of document %s not readable: %s", doc.id, type(exc).__name__
                )
                _set_preview_meta(
                    doc, {"status": "failed", "source": "objektakte", "checked_at": now.isoformat()}
                )
                return PreviewOutcome("failed", detail="Vorschaudatei nicht lesbar")
    if pages:
        try:
            stored = _store_pages(store, tenant_id, doc, pages)
        except Exception as exc:  # storage outage: retried on the next run
            log.warning("preview store failed for document %s: %s", doc.id, type(exc).__name__)
            _set_preview_meta(
                doc, {"status": "failed", "source": "objektakte", "checked_at": now.isoformat()}
            )
            return PreviewOutcome("failed", detail="Objektspeicher nicht erreichbar")
        _set_preview_meta(
            doc,
            {
                "status": "imported",
                "source": "objektakte",
                "imported_at": now.isoformat(),
                **stored,
            },
        )
        return PreviewOutcome("imported", stored["pages"])

    if fetch_original is None:
        _set_preview_meta(doc, {"status": "missing", "checked_at": now.isoformat()})
        return PreviewOutcome("missing")
    if doc.mime_type not in IMAGE_MIME_TYPES:
        _set_preview_meta(
            doc,
            {"status": "pending_render", "reason": "no_renderer", "checked_at": now.isoformat()},
        )
        return PreviewOutcome("pending_render", detail="kein Renderer für diesen Dokumenttyp")
    try:
        original = await fetch_original(doc)
        rendered = render_image_preview(original)
        stored = _store_pages(store, tenant_id, doc, [(1, rendered)])
    except Exception as exc:
        log.warning("preview render failed for document %s: %s", doc.id, type(exc).__name__)
        _set_preview_meta(doc, {"status": "failed", "source": "crm", "checked_at": now.isoformat()})
        return PreviewOutcome("failed", detail="Original nicht abrufbar oder nicht lesbar")
    _set_preview_meta(
        doc, {"status": "rendered", "source": "crm", "rendered_at": now.isoformat(), **stored}
    )
    return PreviewOutcome("rendered", 1)


async def import_previews(
    session: AsyncSession,
    store: PreviewStore,
    tenant_id: uuid.UUID,
    *,
    previews_dir: str | None,
    render_missing: bool = False,
    fetch_original: FetchOriginal | None = None,
    resume: ObjektaktePreviewImportRun | None = None,
    trigger: str = "manual",
    batch_size: int = 200,
    max_documents: int | None = None,
) -> ObjektaktePreviewImportRun:
    """Walk every objektakte document of the tenant in id order and take over its preview.

    ``resume`` continues an earlier run after its cursor; the counters of that run are kept.
    ``max_documents`` bounds one call (a Celery task may chunk a large tenant and resume). The
    run row is flushed after each batch so progress is visible while the run is going."""
    now = datetime.now(UTC)
    run = resume
    if run is None:
        run = ObjektaktePreviewImportRun(
            tenant_id=tenant_id,
            status=PreviewImportStatus.RUNNING,
            trigger=trigger,
            previews_dir=previews_dir,
            render_missing=render_missing,
            started_at=now,
        )
        session.add(run)
        total = await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == tenant_id, Document.source_system == SOURCE_SYSTEM)
        )
        run.total = int(total or 0)
        await session.flush()
    else:
        run.status = PreviewImportStatus.RUNNING
        run.finished_at = None
        run.error = None

    directory = Path(previews_dir) if previews_dir else None
    if directory is not None and not directory.is_dir():
        run.status = PreviewImportStatus.FAILED
        run.error = "Vorschauverzeichnis nicht gefunden"
        run.finished_at = datetime.now(UTC)
        await session.flush()
        return run
    fetcher = fetch_original if render_missing else None

    handled = 0
    cursor = run.last_document_id
    while True:
        query = (
            select(Document)
            .where(Document.tenant_id == tenant_id, Document.source_system == SOURCE_SYSTEM)
            .order_by(Document.id)
            .limit(batch_size)
        )
        if cursor is not None:
            query = query.where(Document.id > cursor)
        batch = (await session.scalars(query)).all()
        if not batch:
            run.status = PreviewImportStatus.DONE
            run.finished_at = datetime.now(UTC)
            break
        for doc in batch:
            outcome = await take_over_document(
                session,
                store,
                tenant_id,
                doc,
                previews_dir=directory,
                fetch_original=fetcher,
                now=datetime.now(UTC),
            )
            run.processed += 1
            if outcome.status == "imported":
                run.imported += 1
            elif outcome.status == "rendered":
                run.rendered += 1
            elif outcome.status in ("missing", "pending_render"):
                run.missing += 1
            elif outcome.status == "skipped":
                run.skipped += 1
            else:
                run.failed += 1
            cursor = doc.id
            run.last_document_id = doc.id
            handled += 1
            if max_documents is not None and handled >= max_documents:
                break
        await session.flush()
        if max_documents is not None and handled >= max_documents:
            break
    await session.flush()
    return run


def run_dict(run: ObjektaktePreviewImportRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "status": run.status.value,
        "trigger": run.trigger,
        "previews_dir": run.previews_dir,
        "render_missing": run.render_missing,
        "total": run.total,
        "processed": run.processed,
        "imported": run.imported,
        "rendered": run.rendered,
        "missing": run.missing,
        "skipped": run.skipped,
        "failed": run.failed,
        "last_document_id": str(run.last_document_id) if run.last_document_id else None,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
    }
