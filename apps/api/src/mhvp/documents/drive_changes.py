"""Drive Changes API (11.2 ``subscribe_changes``, M6-05): follows changes of files the platform
knows in Google Drive, with a cursor per tenant in ``DmsConnection.options``.

The platform stays the master of its documents (6.7): a change in Drive never overwrites or
deletes an index entry or an original. A mirror file removed or trashed in Drive is marked on
the mirror (``last_error``) and journaled as ``document.drive_removed``, so staff can mirror it
again; a Drive stored takeover document (M35) gets the same event. Other changes are counted
only. The first run only stores the start cursor, earlier changes are not replayed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import emit
from mhvp.documents.dms import DmsError, GoogleDriveStore
from mhvp.documents.models import DmsConnection, Document, DocumentMirror, StorageKind

CURSOR_KEY = "changes_page_token"
REMOVED_NOTE = "In Google Drive entfernt oder in den Papierkorb gelegt (Änderungsabgleich)."


@dataclass
class SyncResult:
    started: bool = False
    changes: int = 0
    matched: int = 0
    removed: int = 0


async def _connection(session: AsyncSession) -> DmsConnection | None:
    row: DmsConnection | None = await session.scalar(
        select(DmsConnection).where(
            DmsConnection.kind == StorageKind.GOOGLE_DRIVE, DmsConnection.enabled.is_(True)
        )
    )
    if row is None or not row.secret:
        return None
    return row


async def sync_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    store: GoogleDriveStore,
    connection: DmsConnection,
    actor_user_id: uuid.UUID | None = None,
) -> SyncResult:
    result = SyncResult()
    cursor = (connection.options or {}).get(CURSOR_KEY)
    if not cursor:
        token = await store.start_page_token()
        connection.options = {**(connection.options or {}), CURSOR_KEY: token}
        result.started = True
        return result
    changes, token = await store.list_changes(str(cursor))
    result.changes = len(changes)
    for change in changes:
        mirrors = (
            await session.scalars(
                select(DocumentMirror).where(
                    DocumentMirror.kind == StorageKind.GOOGLE_DRIVE,
                    DocumentMirror.external_ref == change.file_id,
                )
            )
        ).all()
        documents = (
            await session.scalars(
                select(Document.id).where(
                    Document.storage == StorageKind.GOOGLE_DRIVE,
                    Document.storage_ref == change.file_id,
                )
            )
        ).all()
        if not mirrors and not documents:
            continue
        result.matched += 1
        if not change.removed:
            continue
        result.removed += 1
        targets = [m.document_id for m in mirrors] + list(documents)
        for mirror in mirrors:
            mirror.last_error = REMOVED_NOTE
        for document_id in targets:
            await emit(
                session,
                tenant_id=tenant_id,
                type="document.drive_removed",
                entity_type="document",
                entity_id=document_id,
                actor_user_id=actor_user_id,
                payload={"file_id": change.file_id},
            )
    connection.options = {**(connection.options or {}), CURSOR_KEY: token}
    return result


async def sync_session(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    client: httpx.AsyncClient,
    actor_user_id: uuid.UUID | None = None,
) -> SyncResult | None:
    """None when the tenant has no enabled Drive connection."""
    from mhvp.documents.intake import _drive_store  # local: intake imports much of the app

    connection = await _connection(session)
    if connection is None:
        return None
    return await sync_tenant(
        session, tenant_id, _drive_store(connection, client), connection, actor_user_id
    )


__all__ = ["CURSOR_KEY", "DmsError", "SyncResult", "sync_session", "sync_tenant"]
