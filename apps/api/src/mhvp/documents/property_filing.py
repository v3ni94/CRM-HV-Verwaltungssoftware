"""Direct, synchronous filing of one document into a property's Drive year folder (M11-finapi
Stage 3, "Als Rechnung zuordnen"). Distinct from `mhvp.documents.tasks.mirror_tenant`, which
mirrors every document by its category into the fixed `DRIVE_FOLDERS` (01 to 06) on a Celery
schedule: this filing is a single, on-demand action scoped to one document and one property,
into "<Objektordner>/<Jahr>", used by `mhvp.tickets.routers` when a ticket is marked as a
"Rechnung" ticket (rule M20-05 pattern: scoped to that one property, nothing else searched or
listed).
"""

import json
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.blobs import BlobStore
from mhvp.documents.dms import DmsError, GoogleDriveStore, MirrorMeta, property_folder_name
from mhvp.documents.models import DmsConnection, Document, StorageKind
from mhvp.properties.models import Property


@dataclass(frozen=True)
class FilingResult:
    drive_file_ref: str


async def file_document_in_property_year_folder(
    session: AsyncSession,
    *,
    tenant_slug: str,
    document: Document,
    property_: Property,
    year: int,
    blobs: BlobStore,
    client: httpx.AsyncClient,
) -> FilingResult:
    """Loads the tenant's Google Drive connection, uploads `document`'s blob into
    "<Objektordner>/<Jahr>" and returns the resulting Drive file id. Raises `DmsError` if no
    enabled Google Drive connection is configured for this tenant (never invents one)."""
    connection = await session.scalar(
        select(DmsConnection).where(
            DmsConnection.kind == StorageKind.GOOGLE_DRIVE, DmsConnection.enabled.is_(True)
        )
    )
    if connection is None:
        raise DmsError("Keine aktive Google-Drive-Anbindung für diesen Mandanten hinterlegt.")
    secret = json.loads(connection.secret or "{}")
    options = connection.options or {}
    store = GoogleDriveStore(
        root_folder_id=str(options.get("root_folder_id", "")),
        client_id=str(options.get("client_id", "")),
        client_secret=str(secret.get("client_secret", "")),
        refresh_token=str(secret.get("refresh_token", "")),
        client=client,
    )
    meta = MirrorMeta(
        document_id=document.id,
        title=document.title,
        filename=document.filename,
        mime_type=document.mime_type,
        tenant_slug=tenant_slug,
        property_number=property_.number,
        property_folder=property_folder_name(
            property_.number, property_.city, property_.street, property_.house_number
        ),
    )
    data = blobs.get(document.storage_ref)
    result = await store.file_in_property_year_folder(data, meta, year)
    return FilingResult(drive_file_ref=result.ref)
