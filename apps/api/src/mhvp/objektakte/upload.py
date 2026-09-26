"""Upload of CRM documents to objektakte for filing (26.09.2026, docs/integrations/objektakte.md).

A document stored in the CRM (``mhvp.documents.services.store_document``) goes to objektakte when
the upload is switched on (``OBJEKTAKTE_UPLOAD_ENABLED`` plus the read API), the tenant is the
one in ``OBJEKTAKTE_TENANT`` and its links name exactly one property (directly, through a unit or
through a ticket). objektakte then runs its pipeline (OCR, classification, filing in the Drive
structure with owner and tenant files, transfer to Paperless); the CRM does not queue its own
Paperless and Drive mirrors for that document, so each system holds it exactly once. The S3
original and the CRM index stay authoritative.

States of ``objektakte_upload``: ``pending`` (to upload), ``submitted`` (accepted by objektakte,
polled with endpoint 7 until filed), ``done`` (filed; also set by the webhook
``document.filed``), ``failed`` (rejected for good or too many errors). A 503 of objektakte
(switch off there) postpones the upload without counting as an error.

Hints carry identifiers and labels only (unit labels, contact ids, ticket number, title and
category); names and contact data never leave the CRM this way.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentCategory, DocumentLink, DocumentSource
from mhvp.objektakte import dms_service as svc
from mhvp.objektakte.dms_models import ObjektakteUpload
from mhvp.objektakte.remote import (
    ObjektakteClient,
    ObjektakteDeferredError,
    ObjektakteError,
    ObjektakteNotFoundError,
    ObjektakteRejectedError,
)
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.properties.models import Property, Unit
from mhvp.tickets.models import Ticket

log = logging.getLogger(__name__)

# Sources that go to objektakte: what a person uploads or scans. Generated files (letters,
# exports, SEPA files), mail and portal documents and imports keep the CRM's own mirror way.
ROUTED_SOURCES = (DocumentSource.UPLOAD, DocumentSource.SCAN)
# File types objektakte accepts (apps.documents.ingest.ALLOWED_SUFFIXES there); others would
# only be rejected with 400, so they keep the mirror way as well.
ROUTED_SUFFIXES = (
    ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp",
    ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".eml", ".msg", ".html", ".htm",
)  # fmt: skip
BACKOFF_SECONDS = (60, 300, 1800, 7200, 21600, 86400)
POLL_SECONDS = 300  # objektakte works through a queue; its state changes in minutes, not seconds
DEFER_SECONDS = 900  # Retry-After of objektakte while its switch is off
BATCH = 20
MAX_HINT_ITEMS = 50


def _env_settings() -> Settings | None:
    """Settings from the environment for callers without the app settings; None when they do
    not validate (the upload then stays off instead of breaking the document storage)."""
    try:
        return get_settings()
    except ValueError:
        return None


def tenant_matches(settings: Settings, tenant: Tenant) -> bool:
    key = (settings.objektakte_tenant or "").strip()
    return bool(key) and key in (tenant.slug, str(tenant.id))


async def _hints(
    session: AsyncSession, document: Document, links: list[DocumentLink]
) -> tuple[set[uuid.UUID], dict[str, Any]]:
    property_ids: set[uuid.UUID] = set()
    units: list[str] = []
    contacts: list[str] = []
    tickets: list[str] = []
    for link in links:
        if link.entity_type == "property":
            property_ids.add(link.entity_id)
        elif link.entity_type == "unit":
            unit = await session.get(Unit, link.entity_id)
            if unit is not None:
                property_ids.add(unit.property_id)
                units.append(unit.label or unit.number)
        elif link.entity_type == "ticket":
            ticket = await session.get(Ticket, link.entity_id)
            if ticket is not None:
                tickets.append(f"TNR#{ticket.number}")
                if ticket.property_id is not None:
                    property_ids.add(ticket.property_id)
                if ticket.unit_id is not None:
                    unit = await session.get(Unit, ticket.unit_id)
                    if unit is not None:
                        units.append(unit.label or unit.number)
        elif link.entity_type == "contact":
            contacts.append(str(link.entity_id))
    hints: dict[str, Any] = {"title": document.title[:300]}
    if units:
        hints["unit_labels"] = list(dict.fromkeys(units))[:MAX_HINT_ITEMS]
    if contacts:
        hints["contact_refs"] = list(dict.fromkeys(contacts))[:MAX_HINT_ITEMS]
    if tickets:
        hints["ticket_number"] = tickets[0]
    if document.category_id:
        category = await session.get(DocumentCategory, document.category_id)
        if category is not None:
            hints["category"] = category.name[:300]
    return property_ids, hints


async def plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ObjektakteUpload | None:
    """Queues the upload of one document when all conditions hold; returns the row or None."""
    settings = settings or _env_settings()
    if settings is None or not settings.objektakte_upload_active:
        return None
    existing = await session.scalar(
        select(ObjektakteUpload).where(
            ObjektakteUpload.tenant_id == tenant_id, ObjektakteUpload.document_id == document_id
        )
    )
    if existing is not None:
        return existing
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or not tenant_matches(settings, tenant):
        return None
    document = await session.get(Document, document_id)
    if (
        document is None
        or document.source not in ROUTED_SOURCES
        or document.source_system == svc.SOURCE_SYSTEM
        or not document.filename.lower().endswith(ROUTED_SUFFIXES)
    ):
        return None
    links = list(
        (
            await session.scalars(
                select(DocumentLink).where(DocumentLink.document_id == document_id)
            )
        ).all()
    )
    property_ids, hints = await _hints(session, document, links)
    if len(property_ids) != 1:
        return None
    prop = await session.get(Property, next(iter(property_ids)))
    number = (prop.number or "").strip() if prop is not None else ""
    if prop is None or not number.isdigit():
        return None
    upload = ObjektakteUpload(
        tenant_id=tenant_id,
        document_id=document_id,
        property_id=prop.id,
        object_number=number[:16],
        status="pending",
        hints=hints,
        attempts=0,
        next_attempt_at=now or datetime.now(UTC),
    )
    session.add(upload)
    await session.flush()
    return upload


async def is_routed(session: AsyncSession, document_id: uuid.UUID) -> bool:
    return (
        await session.scalar(
            select(ObjektakteUpload.id).where(ObjektakteUpload.document_id == document_id)
        )
    ) is not None


def _fail_or_retry(upload: ObjektakteUpload, message: str, now: datetime) -> None:
    upload.last_error = message[:500]
    index = min(upload.attempts - 1, len(BACKOFF_SECONDS) - 1)
    if upload.attempts > len(BACKOFF_SECONDS):
        upload.status = "failed"
        upload.next_attempt_at = None
    else:
        upload.next_attempt_at = now + timedelta(seconds=BACKOFF_SECONDS[index])


async def _apply_state(
    session: AsyncSession,
    upload: ObjektakteUpload,
    document: Document,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Takes over the state objektakte reports for the uploaded document."""
    doc_id = state.get("id")
    if isinstance(doc_id, int) and not isinstance(doc_id, bool):
        upload.objektakte_document_id = doc_id
    status = state.get("status")
    upload.remote = {
        k: state.get(k)
        for k in ("status", "category", "subfolder", "doc_type", "drive_url", "paperless_id")
        if state.get(k) is not None
    }
    if state.get("deleted"):
        upload.status, upload.next_attempt_at = "failed", None
        upload.last_error = "In objektakte gelöscht."
        return
    filed_row: dict[str, Any] | None = None
    duplicate_of: Any = None
    if status == "filed":
        filed_row = state
    elif status == "duplicate" and isinstance(state.get("duplicate_of"), dict):
        # objektakte keeps one copy; the CRM document is linked to the filing of the original
        filed_row = {**state["duplicate_of"], "crm_document_id": str(document.id)}
        duplicate_of = state["duplicate_of"].get("id")
    if filed_row is not None and filed_row.get("status") == "filed":
        try:
            parsed = svc.parse_document(filed_row)
        except ValueError as exc:
            upload.status, upload.next_attempt_at = "failed", None
            upload.last_error = f"objektakte meldet eine ungültige Ablage: {exc}"
            return
        await svc.link_filed_document(
            session,
            upload.tenant_id,
            object_number=upload.object_number,
            doc=parsed,
            actor_user_id=None,
            existing=document,
        )
        upload.status, upload.done_at, upload.next_attempt_at = "done", now, None
        upload.last_error = None
        if duplicate_of is not None:
            upload.remote = {**(upload.remote or {}), "duplicate_of": duplicate_of}
        return
    upload.status = "submitted"
    upload.last_error = None
    upload.next_attempt_at = now + timedelta(seconds=POLL_SECONDS)


async def process_tenant(
    session: AsyncSession,
    client: ObjektakteClient,
    blobs: BlobStore,
    now: datetime | None = None,
) -> int:
    """One round for the due uploads of the tenant bound to the session."""
    now = now or datetime.now(UTC)
    due = (
        await session.scalars(
            select(ObjektakteUpload)
            .where(
                ObjektakteUpload.status.in_(("pending", "submitted")),
                or_(
                    ObjektakteUpload.next_attempt_at.is_(None),
                    ObjektakteUpload.next_attempt_at <= now,
                ),
            )
            .order_by(ObjektakteUpload.next_attempt_at)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for upload in due:
        document = await session.get(Document, upload.document_id)
        if document is None:  # pragma: no cover - the cascade deletes the row
            continue
        upload.attempts += 1
        try:
            if upload.status == "pending" or upload.objektakte_document_id is None:
                state = await client.upload_document(
                    upload.object_number,
                    crm_document_id=str(document.id),
                    filename=document.filename,
                    data=blobs.get(document.storage_ref),
                    mime_type=document.mime_type,
                    hints=upload.hints or {},
                )
            else:
                state = await client.document_status(upload.objektakte_document_id)
            await _apply_state(session, upload, document, state, now)
        except ObjektakteDeferredError as exc:
            upload.attempts -= 1  # objektakte's switch is off: wait, this is no error
            upload.last_error = str(exc)
            upload.next_attempt_at = now + timedelta(seconds=DEFER_SECONDS)
        except (ObjektakteRejectedError, ObjektakteNotFoundError) as exc:
            upload.status, upload.next_attempt_at = "failed", None
            upload.last_error = str(exc)[:500]
        except ObjektakteError as exc:
            _fail_or_retry(upload, str(exc), now)
            log.warning("objektakte_upload_failed", extra={"error": str(exc)})
        except (httpx.HTTPError, OSError) as exc:
            _fail_or_retry(upload, type(exc).__name__, now)
    await session.flush()
    return len(due)


async def upload_once(
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
    blobs: BlobStore | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    if not settings.objektakte_upload_active:
        return {"processed": 0}
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    store = blobs or BlobStore(settings)
    processed = 0
    try:
        async with platform_transaction(factory) as session:
            tenants = [
                t
                for t in await session.scalars(
                    select(Tenant).where(Tenant.status == TenantStatus.ACTIVE)
                )
                if tenant_matches(settings, t)
            ]
        async with ObjektakteClient.from_settings(settings, transport=transport) as client:
            for tenant in tenants:
                async with tenant_transaction(factory, tenant.id) as session:
                    processed += await process_tenant(session, client, store, now)
    finally:
        await engine.dispose()
    return {"processed": processed}


async def reset_failed(session: AsyncSession, document_id: uuid.UUID) -> bool:
    """Queues a failed upload again (manual retry); True when a row was reset."""
    upload = await session.scalar(
        select(ObjektakteUpload).where(ObjektakteUpload.document_id == document_id)
    )
    if upload is None or upload.status != "failed":
        return False
    upload.status = "submitted" if upload.objektakte_document_id else "pending"
    upload.attempts, upload.last_error = 0, None
    upload.next_attempt_at = datetime.now(UTC)
    await session.flush()
    return True
