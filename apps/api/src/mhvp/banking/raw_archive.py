"""Archive of raw bank responses and statement files (8.2, M11-07).

Every original bank file or provider response is kept unchanged under the object key
``bank/<tenant>/<account>/<date>.<ext>`` and indexed as a document with a retention profile.
Retention: the existing standard profile class ``accounting_records`` (10 years, as named in
8.2; draft "Prüfung Steuerberatung offen", M6-04, OPEN_QUESTIONS M11-03/P09-01). No new legal
rule is defined here and a draft profile never unlocks a deletion (6.9.5). The original is
never overwritten: a second file of the same day gets a numeric suffix.
"""

import hashlib
import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.ids import uuid7
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import retention
from mhvp.documents.blobs import BlobStore
from mhvp.documents.defaults import ensure_retention_defaults
from mhvp.documents.models import (
    Document,
    DocumentLink,
    DocumentSource,
    LinkRole,
    RetentionProfile,
    StorageKind,
)

RAW_RETENTION_CLASS = "accounting_records"
RAW_SOURCE_SYSTEM = "bank_raw"
ALLOWED_EXTENSIONS = {
    "xml": "application/xml",
    "json": "application/json",
    "csv": "text/csv",
    "sta": "text/plain",
    "mt940": "text/plain",
    "txt": "text/plain",
}


def raw_object_key(
    tenant_id: uuid.UUID, account_id: uuid.UUID, day: date, ext: str, sequence: int = 1
) -> str:
    """``bank/<tenant>/<account>/<date>.<ext>`` (8.2); ``sequence`` > 1 appends ``-<n>``."""
    ext = ext.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Dateityp der Bankrohdaten nicht zulässig."
        )
    suffix = "" if sequence <= 1 else f"-{sequence}"
    return f"bank/{tenant_id}/{account_id}/{day.isoformat()}{suffix}.{ext}"


async def _free_key(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID, day: date, ext: str
) -> str:
    sequence = 1
    while True:
        key = raw_object_key(tenant_id, account_id, day, ext, sequence)
        taken = await session.scalar(select(Document.id).where(Document.storage_ref == key))
        if taken is None:
            return key
        sequence += 1


async def retention_profile_for_raw(
    session: AsyncSession, tenant_id: uuid.UUID
) -> RetentionProfile | None:
    """Tenant wide profile of class ``accounting_records`` (seeded as draft when missing)."""
    await ensure_retention_defaults(session, tenant_id)
    profile: RetentionProfile | None = await session.scalar(
        select(RetentionProfile)
        .where(
            RetentionProfile.document_class == RAW_RETENTION_CLASS,
            RetentionProfile.legal_entity_kind.is_(None),
        )
        .order_by(RetentionProfile.created_at)
        .limit(1)
    )
    return profile


async def archive_raw(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    data: bytes,
    ext: str,
    day: date,
    created_by: uuid.UUID | None,
    legal_entity_id: uuid.UUID | None = None,
    label: str = "Bankrohdaten",
) -> Document:
    """Stores the unchanged bytes under the bank key and indexes them with the 10 year
    profile. The blob is written first; a failed put leaves no index row (rule 0.1.7)."""
    ext = ext.lower().lstrip(".")
    raw_object_key(tenant_id, account_id, day, ext)  # validates the extension first
    # U15: serialise concurrent archives of the same account and day; without the lock two
    # transactions find the same free key and the second put overwrites the first original.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"bank_raw:{tenant_id}:{account_id}:{day.isoformat()}"},
    )
    key = await _free_key(session, tenant_id, account_id, day, ext)
    sha256 = hashlib.sha256(data).hexdigest()
    mime = ALLOWED_EXTENSIONS[ext]
    blobs.put(key, data, mime, sha256)
    document = Document(
        id=uuid7(),
        tenant_id=tenant_id,
        title=f"{label} {day.isoformat()}"[:300],
        filename=key.rsplit("/", 1)[-1],
        mime_type=mime,
        size=len(data),
        sha256=sha256,
        storage=StorageKind.MINIO,
        storage_ref=key,
        source=DocumentSource.IMPORT,
        source_system=RAW_SOURCE_SYSTEM,
        visibility=["tenant"],
        created_by=created_by,
    )
    session.add(document)
    await session.flush()
    await retention.assign_profile(
        session, document, await retention_profile_for_raw(session, tenant_id)
    )
    if legal_entity_id is not None:
        session.add(
            DocumentLink(
                tenant_id=tenant_id,
                document_id=document.id,
                entity_type="legal_entity",
                entity_id=legal_entity_id,
                role=LinkRole.EVIDENCE,
            )
        )
    await session.flush()
    return document
