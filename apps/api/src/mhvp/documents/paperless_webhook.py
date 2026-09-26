"""Paperless-ngx post-consume webhook (task A30, master prompt 11.2 and 11.4, M14-05).

``POST /documents/webhooks/paperless`` (or ``.../paperless/{tenant}``) is outside the tenant
login by design: the post-consume script of Paperless calls it directly. Every delivery is
checked against the secret stored per tenant in the Paperless settings (``DmsConnection``
kind paperless, ``webhook_secret``, write only):

* ``X-MHVP-Timestamp``: Unix seconds, at most ``WINDOW_SECONDS`` away from the server clock;
* ``X-MHVP-Signature``: ``sha256=<hex>`` of HMAC-SHA256(secret, ``"<timestamp>." + raw body``);
* ``X-MHVP-Tenant`` (or the path segment): tenant slug or id.

A signature seen before within the window is refused as a replay (409). A valid delivery
indexes the Paperless document through the existing read-only client (``PaperlessSearch``,
M31): the file is stored once (``Document.source_system = "paperless"``, ``source_id`` =
Paperless id, unique) and the mirror row is marked done so the mirror job never pushes it back.
Only when the tenant switch "Belegeingang aus Paperless automatisch" is on (default off,
M14-05) a receipt draft is queued through the existing receipts functions; the draft remains a
proposal for review, never an invoice or a posting (rule 0.1.6).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

from celery import shared_task
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import services as svc
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    DmsConnection,
    Document,
    DocumentMirror,
    DocumentSource,
    MirrorStatus,
    StorageKind,
)
from mhvp.documents.paperless_search import PaperlessSearchError
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)

router = APIRouter(prefix="/documents/webhooks", tags=["Paperless Webhook"])

SOURCE_SYSTEM = "paperless"
WINDOW_SECONDS = 300
MAX_BODY_BYTES = 16 * 1024
# Column widths of Document.title and Document.filename (documents/models.py).
MAX_TITLE_CHARS = 300
MAX_FILENAME_CHARS = 255
SIGNATURE_HEADER = "X-MHVP-Signature"
TIMESTAMP_HEADER = "X-MHVP-Timestamp"
TENANT_HEADER = "X-MHVP-Tenant"


def sign(secret: str, timestamp: int | str, body: bytes) -> str:
    """Signature value the post-consume script must send (documented in the handbook)."""
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"sha256={digest.hexdigest()}"


def verify(secret: str, timestamp: str | None, signature: str | None, body: bytes) -> bool:
    if not timestamp or not signature or not signature.startswith("sha256="):
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > WINDOW_SECONDS:
        return False
    return hmac.compare_digest(sign(secret, ts, body), signature)


def _refuse() -> ProblemError:
    return ProblemError(ErrorCodes.WEBHOOK_SIGNATURE)


async def _resolve_tenant(factory: async_sessionmaker[AsyncSession], key: str | None) -> uuid.UUID:
    if not key:
        raise _refuse()
    async with platform_transaction(factory) as session:
        try:
            tenant_id: uuid.UUID | None = uuid.UUID(key)
        except ValueError:
            tenant_id = None
        query = select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        query = (
            query.where(Tenant.id == tenant_id) if tenant_id else query.where(Tenant.slug == key)
        )
        found = await session.scalar(query)
    if found is None:
        raise _refuse()
    return found


def document_names(
    filename: str | None, title: str | None, *, paperless_document_id: int
) -> tuple[str, str]:
    """(filename, title) within the column widths of ``Document`` (Sicherheitsreview 1.22,
    Befund 8): a Paperless name over the limit is cut, never refused, and an empty name falls
    back to ``paperless-<id>.pdf``."""
    name = (filename or "").strip() or f"paperless-{paperless_document_id}.pdf"
    if len(name) > MAX_FILENAME_CHARS:
        stem, dot, ext = name.rpartition(".")
        keep = MAX_FILENAME_CHARS - (len(ext) + 1 if dot and len(ext) <= 10 else 0)
        name = f"{stem[:keep]}.{ext}" if dot and len(ext) <= 10 else name[:MAX_FILENAME_CHARS]
    shown = (title or "").strip() or name
    return name, shown[:MAX_TITLE_CHARS]


async def _connection(session: AsyncSession) -> DmsConnection | None:
    row: DmsConnection | None = await session.scalar(
        select(DmsConnection).where(
            DmsConnection.kind == StorageKind.PAPERLESS, DmsConnection.enabled.is_(True)
        )
    )
    return row


async def index_paperless_document(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    tenant_id: uuid.UUID,
    settings: Settings,
    paperless_document_id: int,
    title: str | None,
) -> tuple[Document, bool]:
    """Stores the Paperless document once as a CRM document. Returns (document, created)."""
    from mhvp.documents.routers import _paperless_client

    existing = await session.scalar(
        select(Document).where(
            Document.source_system == SOURCE_SYSTEM,
            Document.source_id == str(paperless_document_id),
        )
    )
    if existing is not None:
        return existing, False
    client = await _paperless_client(session)
    try:
        file = await client.fetch_file(paperless_document_id, "download")
    except PaperlessSearchError as exc:
        raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
    finally:
        await client.aclose()
    if len(file.content) > settings.document_max_bytes:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED,
            detail="Das Paperless-Dokument überschreitet die zulässige Dateigröße.",
        )
    filename, document_title = document_names(
        file.filename, title, paperless_document_id=paperless_document_id
    )
    document = await svc.store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=file.content,
        title=document_title,
        filename=filename,
        mime_type=file.content_type,
        source=DocumentSource.IMPORT,
        category_id=None,
        links=[],
        created_by=None,
    )
    document.source_system = SOURCE_SYSTEM
    document.source_id = str(paperless_document_id)
    # The original lives in Paperless already: mark the mirror as done instead of pushing a
    # copy back (11.1 mirror job, `mhvp.documents.tasks.mirror_tenant`).
    mirror = await session.scalar(
        select(DocumentMirror).where(
            DocumentMirror.document_id == document.id,
            DocumentMirror.kind == StorageKind.PAPERLESS,
        )
    )
    if mirror is None:
        mirror = DocumentMirror(
            tenant_id=tenant_id, document_id=document.id, kind=StorageKind.PAPERLESS
        )
        session.add(mirror)
    mirror.status = MirrorStatus.DONE
    mirror.external_ref = str(paperless_document_id)
    await emit(
        session,
        tenant_id=tenant_id,
        type="paperless.document_received",
        entity_type="document",
        entity_id=document.id,
        actor_user_id=None,
        payload={"paperless_document_id": paperless_document_id, "mime_type": file.content_type},
    )
    await session.flush()
    return document, True


async def intake_document(
    factory: async_sessionmaker[AsyncSession],
    blobs: BlobStore,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
) -> uuid.UUID | None:
    """Creates the receipt draft for an indexed Paperless document with the existing receipts
    functions (`mhvp.receipts.extraction.prepare`, then the AI run of `mhvp.ai.jobs`). Returns
    the draft id, or None when nothing was started (unsupported type, open draft exists)."""
    from mhvp.ai import jobs
    from mhvp.receipts import extraction
    from mhvp.receipts.models import ReceiptDraft, ReceiptDraftSource, ReceiptDraftStatus
    from mhvp.receipts.routers import _EINVOICE_MIME, _SUPPORTED_MIME

    async with tenant_transaction(factory, tenant_id) as session:
        document = await session.get(Document, document_id)
        if document is None or document.mime_type not in _SUPPORTED_MIME:
            return None
        open_draft = await session.scalar(
            select(ReceiptDraft.id).where(
                ReceiptDraft.document_id == document_id,
                ReceiptDraft.status.in_(
                    [ReceiptDraftStatus.EXTRACTING.value, ReceiptDraftStatus.PROPOSED.value]
                ),
            )
        )
        if open_draft is not None:
            return None
        data = blobs.get(document.storage_ref) if document.mime_type in _EINVOICE_MIME else None
        draft = await extraction.prepare(
            session,
            tenant_id=tenant_id,
            user_id=None,
            document=document,
            source=ReceiptDraftSource.PAPERLESS.value,
            message_id=None,
            data=data,
        )
        await emit(
            session,
            tenant_id=tenant_id,
            type="receipt_draft.started",
            entity_type="receipt_draft",
            entity_id=draft.id,
            actor_user_id=None,
            payload={
                "source": ReceiptDraftSource.PAPERLESS.value,
                "automatic": True,
                "ai_run": draft.task_run_id is not None,
            },
        )
        draft_id, run_id = draft.id, draft.task_run_id
    if run_id is not None:
        await jobs.run_and_propose(factory, tenant_id, run_id, blobs, None)
    return draft_id


async def _intake_once(settings: Settings, tenant_id: uuid.UUID, document_id: uuid.UUID) -> str:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        draft_id = await intake_document(
            create_session_factory(engine), BlobStore(settings), tenant_id, document_id
        )
        return str(draft_id) if draft_id else ""
    finally:
        await engine.dispose()


@shared_task(name="mhvp.documents.paperless_receipt_intake", acks_late=True)
def paperless_receipt_intake(tenant_id: str, document_id: str) -> str:
    return asyncio.run(_intake_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(document_id)))


async def _receive(request: Request, tenant_key: str | None) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    resources = request.app.state.resources
    factory: async_sessionmaker[AsyncSession] = resources.session_factory
    # Size limit before anything is read or checked (Sicherheitsreview 1.22, Befund 2), same
    # bound as the telephony webhook: the payload is a document id and a title.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise ProblemError(ErrorCodes.WEBHOOK_TOO_LARGE, detail="Webhook-Inhalt zu groß.")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ProblemError(ErrorCodes.WEBHOOK_TOO_LARGE, detail="Webhook-Inhalt zu groß.")
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    signature = request.headers.get(SIGNATURE_HEADER)
    tenant_id = await _resolve_tenant(factory, tenant_key or request.headers.get(TENANT_HEADER))

    async with tenant_transaction(factory, tenant_id) as session:
        connection = await _connection(session)
        secret = connection.webhook_secret if connection is not None else None
        if not secret or not verify(secret, timestamp, signature, raw):
            log.warning("paperless webhook: invalid or missing signature")
            raise _refuse()
        auto_intake = bool(connection is not None and connection.auto_receipt_intake)

    # Replay window: the same signature (timestamp and body) is accepted once.
    assert signature is not None  # noqa: S101 - verified above
    marker = f"paperless-webhook:{tenant_id}:{hashlib.sha256(signature.encode()).hexdigest()}"
    fresh = await resources.redis.set(marker, "1", nx=True, ex=WINDOW_SECONDS * 2)
    if not fresh:
        raise ProblemError(ErrorCodes.WEBHOOK_REPLAY)

    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Webhook-Inhalt ist kein JSON.") from None
    raw_id = payload.get("document_id") if isinstance(payload, dict) else None
    if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
        raise ProblemError(ErrorCodes.VALIDATION, detail="document_id (Paperless) fehlt.")
    title = payload.get("title") if isinstance(payload.get("title"), str) else None

    blobs = BlobStore(settings)
    async with tenant_transaction(factory, tenant_id) as session:
        document, created = await index_paperless_document(
            session,
            blobs,
            tenant_id=tenant_id,
            settings=settings,
            paperless_document_id=raw_id,
            title=title,
        )
        document_id = document.id

    intake = "off"
    if auto_intake and created:
        intake = "queued"
        if settings.ai_inline:
            await intake_document(factory, blobs, tenant_id, document_id)
        else:
            paperless_receipt_intake.delay(str(tenant_id), str(document_id))
    return {
        "status": "indexed" if created else "already_indexed",
        "document_id": str(document_id),
        "receipt_intake": intake,
    }


@router.post("/paperless", summary="Paperless Post-Consume-Webhook (HMAC, je Mandant)")
async def receive(request: Request) -> dict[str, Any]:
    return await _receive(request, None)


@router.post("/paperless/{tenant_key}", summary="Paperless Post-Consume-Webhook (Mandant im Pfad)")
async def receive_for_tenant(tenant_key: str, request: Request) -> dict[str, Any]:
    return await _receive(request, tenant_key)
