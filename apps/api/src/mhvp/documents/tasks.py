"""Celery job: mirror documents to Paperless-ngx and Google Drive (11.1, 11.2)."""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from botocore.exceptions import ClientError
from celery import shared_task
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.contacts.models import Contact
from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.problems import ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.dms import (
    DmsError,
    DocumentStore,
    GoogleDriveStore,
    MirrorMeta,
    PaperlessStore,
    property_folder_name,
)
from mhvp.documents.models import (
    DmsConnection,
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentMirror,
    MirrorStatus,
    StorageKind,
    TextStatus,
)
from mhvp.objektakte.drive_quota import drive_http_client
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.properties.models import Property

log = logging.getLogger(__name__)
BACKOFF_SECONDS = (60, 300, 1800, 7200, 21600, 86400)
BATCH = 20
TIMEOUT_SECONDS = 60.0
TEXT_LIMIT = 200_000  # same cap as mhvp.documents.intake


def store_for(connection: DmsConnection, client: httpx.AsyncClient) -> DocumentStore:
    if connection.kind is StorageKind.PAPERLESS:
        if not connection.base_url or not connection.secret:
            raise DmsError("Paperless: base_url or token missing")
        return PaperlessStore(connection.base_url, connection.secret, client)
    secret = json.loads(connection.secret or "{}")
    options = connection.options or {}
    return GoogleDriveStore(
        root_folder_id=str(options.get("root_folder_id", "")),
        client_id=str(options.get("client_id", "")),
        client_secret=str(secret.get("client_secret", "")),
        refresh_token=str(secret.get("refresh_token", "")),
        client=client,
    )


async def _meta(session: AsyncSession, tenant_slug: str, document: Document) -> MirrorMeta:
    meta = MirrorMeta(
        document_id=document.id,
        title=document.title,
        filename=document.filename,
        mime_type=document.mime_type,
        tenant_slug=tenant_slug,
    )
    if document.category_id:
        category = await session.get(DocumentCategory, document.category_id)
        if category is not None:
            meta.document_type = category.paperless_document_type
            meta.drive_folder = category.drive_folder
            if category.paperless_tag:  # M6-09
                meta.tags.append(category.paperless_tag)
    links = (
        await session.scalars(select(DocumentLink).where(DocumentLink.document_id == document.id))
    ).all()
    if links:  # M6-07: first link as Paperless custom fields entity_type / entity_id
        meta.entity_type, meta.entity_id = links[0].entity_type, str(links[0].entity_id)
    for link in links:
        if link.entity_type == "property" and meta.property_number is None:
            prop = await session.get(Property, link.entity_id)
            if prop is not None:
                meta.property_number = prop.number
                meta.property_folder = property_folder_name(
                    prop.number, prop.city, prop.street, prop.house_number
                )
        if link.entity_type == "contact" and meta.correspondent is None:
            contact = await session.get(Contact, link.entity_id)
            if contact is not None:
                meta.correspondent = contact.display_name
    return meta


async def mirror_tenant(
    session: AsyncSession,
    tenant: Tenant,
    blobs: BlobStore,
    client: httpx.AsyncClient,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    due = (
        await session.scalars(
            select(DocumentMirror)
            .where(
                DocumentMirror.status.in_((MirrorStatus.PENDING, MirrorStatus.SUBMITTED)),
                or_(
                    DocumentMirror.next_attempt_at.is_(None), DocumentMirror.next_attempt_at <= now
                ),
            )
            .order_by(DocumentMirror.next_attempt_at)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        )
    ).all()
    connections = {c.kind: c for c in (await session.scalars(select(DmsConnection))).all()}
    for mirror in due:
        connection = connections.get(mirror.kind)
        if connection is None or not connection.enabled:
            continue
        mirror.attempts += 1
        try:
            store = store_for(connection, client)
            if mirror.status is MirrorStatus.PENDING:
                document = await session.get(Document, mirror.document_id)
                if document is None:  # pragma: no cover - cascade deletes the mirror
                    continue
                result = await store.put(
                    blobs.get(document.storage_ref), await _meta(session, tenant.slug, document)
                )
                mirror.external_ref = result.ref
                mirror.status = MirrorStatus.DONE if result.final else MirrorStatus.SUBMITTED
            if mirror.status is MirrorStatus.SUBMITTED and mirror.external_ref:
                resolved = await store.resolve(mirror.external_ref)
                if resolved is not None:
                    mirror.external_ref, mirror.status = resolved, MirrorStatus.DONE
                    # Paperless takes custom fields only on a PATCH after the consume task.
                    mirror.meta_dirty = mirror.kind is StorageKind.PAPERLESS
                    if isinstance(store, PaperlessStore):
                        await _adopt_paperless_text(session, store, mirror)
            mirror.last_error = None
            mirror.next_attempt_at = now + timedelta(seconds=60)
        except (DmsError, httpx.HTTPError, ClientError, ProblemError, ValueError, KeyError) as exc:
            # ProblemError: the original is not readable from object storage (blobs.py wraps
            # S3 errors); one unreadable document must not abort the run for the others.
            message = str(exc) if isinstance(exc, DmsError) else type(exc).__name__
            mirror.last_error = message[:500]
            index = min(mirror.attempts - 1, len(BACKOFF_SECONDS) - 1)
            if mirror.attempts > len(BACKOFF_SECONDS):
                mirror.status = MirrorStatus.FAILED
            mirror.next_attempt_at = now + timedelta(seconds=BACKOFF_SECONDS[index])
            log.warning(
                "document_mirror_failed", extra={"kind": mirror.kind.value, "error": message}
            )
    await _push_dirty_meta(session, tenant, connections, client, now)
    await session.flush()
    return len(due)


async def _adopt_paperless_text(
    session: AsyncSession, store: PaperlessStore, mirror: DocumentMirror
) -> bool:
    """GAB-04 (11.2, 11.4): once Paperless consumed the mirror, its full text (text layer or
    OCR) replaces a pending text status. The search vector is a generated column; the
    embedding job picks the document up through ``updated_at`` on its next run. An existing
    text is never overwritten."""
    if mirror.external_ref is None:
        return False
    document = await session.get(Document, mirror.document_id)
    if document is None or document.text_status is not TextStatus.PENDING:
        return False
    text = await store.content(mirror.external_ref)
    if text is None:
        return False
    document.ocr_text = text[:TEXT_LIMIT]
    document.text_status = TextStatus.EXTRACTED
    return True


async def _push_dirty_meta(
    session: AsyncSession,
    tenant: Tenant,
    connections: dict[StorageKind, DmsConnection],
    client: httpx.AsyncClient,
    now: datetime,
) -> int:
    """M6-06: pushes metadata changes of the index into finished mirrors (update_meta)."""
    dirty = (
        await session.scalars(
            select(DocumentMirror)
            .where(
                DocumentMirror.status == MirrorStatus.DONE,
                DocumentMirror.meta_dirty.is_(True),
                DocumentMirror.external_ref.is_not(None),
            )
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for mirror in dirty:
        connection = connections.get(mirror.kind)
        if connection is None or not connection.enabled or mirror.external_ref is None:
            continue
        try:
            document = await session.get(Document, mirror.document_id)
            if document is not None:
                meta = await _meta(session, tenant.slug, document)
                await store_for(connection, client).update_meta(mirror.external_ref, meta)
            mirror.meta_dirty = False
            mirror.last_error = None
        except (DmsError, httpx.HTTPError) as exc:
            message = str(exc) if isinstance(exc, DmsError) else type(exc).__name__
            mirror.last_error = message[:500]
            mirror.next_attempt_at = now + timedelta(seconds=BACKOFF_SECONDS[0])
    return len(dirty)


async def mirror_once(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    blobs: BlobStore | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    # M35-06: Drive requests are rate limited with backoff (mhvp.objektakte.drive_quota).
    http = client or drive_http_client(timeout=TIMEOUT_SECONDS)
    store = blobs or BlobStore(settings)
    processed = 0
    try:
        async with platform_transaction(factory) as session:
            tenants = list(
                await session.scalars(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant in tenants:
            tenant_id: uuid.UUID = tenant.id
            async with tenant_transaction(factory, tenant_id) as session:
                processed += await mirror_tenant(session, tenant, store, http, now)
    finally:
        if client is None:
            await http.aclose()
        await engine.dispose()
    return {"processed": processed}


@shared_task(name="mhvp.documents.mirror")
def mirror() -> dict[str, int]:
    return asyncio.run(mirror_once(get_settings()))


# Drive changes (M6-05) and temporary objects (M6-08) ---------------------------------------

TMP_MAX_AGE = timedelta(days=1)


async def drive_changes_once(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> dict[str, int]:
    from mhvp.documents import drive_changes

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    http = client or drive_http_client(timeout=TIMEOUT_SECONDS)
    totals = {"tenants": 0, "changes": 0, "removed": 0}
    try:
        async with platform_transaction(factory) as session:
            tenant_ids = [
                t.id
                for t in await session.scalars(
                    select(Tenant).where(Tenant.status == TenantStatus.ACTIVE)
                )
            ]
        for tenant_id in tenant_ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    result = await drive_changes.sync_session(session, tenant_id, http)
            except (DmsError, httpx.HTTPError) as exc:
                log.warning("drive changes failed for %s: %s", tenant_id, type(exc).__name__)
                continue
            if result is not None:
                totals["tenants"] += 1
                totals["changes"] += result.changes
                totals["removed"] += result.removed
    finally:
        if client is None:
            await http.aclose()
        await engine.dispose()
    return totals


@shared_task(name="mhvp.documents.drive_changes")
def drive_changes_task() -> dict[str, int]:
    return asyncio.run(drive_changes_once(get_settings()))


def cleanup_tmp_once(settings: Settings, now: datetime | None = None) -> dict[str, int]:
    """Lifecycle rule plus a sweep of ``tmp/`` (M6-08): the rule is set again every run (a
    store without lifecycle support answers False), the sweep removes staged uploads older
    than one day in any case."""
    try:
        store = BlobStore(settings)
    except ProblemError:
        return {"lifecycle": 0, "removed": 0}
    lifecycle = store.ensure_tmp_lifecycle()
    removed = store.purge_tmp((now or datetime.now(UTC)) - TMP_MAX_AGE)
    return {"lifecycle": int(lifecycle), "removed": removed}


@shared_task(name="mhvp.documents.cleanup_tmp")
def cleanup_tmp() -> dict[str, int]:
    return cleanup_tmp_once(get_settings())
