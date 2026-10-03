"""Payment files (pain.008 direct debit, pain.001 transfer) as a locked document kind (GAJ-301).

A generated SEPA file could be submitted to the bank by hand. The domain routes hand it out
only with release gate G2 (18.0); the general document routes must not be a way around that.
A document is a payment file when its category code is ``payment_file`` or when a direct debit
run or a payment batch references it. The reference check also covers files stored before the
category existed, so no data migration is needed for the lock; ``recategorize`` only aligns
the category for display and filters.
"""

import uuid
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.documents.models import Document, DocumentCategory

PAYMENT_FILE_CATEGORY = "payment_file"
PAYMENT_FILE_CATEGORY_NAME = "Zahlungsdatei (gesperrt bis G2)"


def _referencing() -> tuple[Any, Any]:
    from mhvp.accounting.direct_debit_models import DirectDebitRun  # local: import cycle
    from mhvp.banking.models import PaymentBatch

    return DirectDebitRun, PaymentBatch


async def category_id(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's ``payment_file`` category, created on first use (idempotent)."""
    found = await session.scalar(
        select(DocumentCategory.id).where(DocumentCategory.code == PAYMENT_FILE_CATEGORY)
    )
    if found is not None:
        return found
    row = DocumentCategory(
        tenant_id=tenant_id,
        code=PAYMENT_FILE_CATEGORY,
        name=PAYMENT_FILE_CATEGORY_NAME,
        drive_folder="03_Buchhaltung",
        sort_order=900,
    )
    session.add(row)
    await session.flush()
    return row.id


async def payment_file_ids(session: AsyncSession, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Subset of ``ids`` that are payment files (category or referenced by a run or batch)."""
    if not ids:
        return set()
    run, batch = _referencing()
    by_category = select(Document.id).where(
        Document.id.in_(ids),
        Document.category_id.in_(
            select(DocumentCategory.id).where(DocumentCategory.code == PAYMENT_FILE_CATEGORY)
        ),
    )
    by_run = select(run.document_id).where(run.document_id.in_(ids))
    by_batch = select(batch.document_id).where(batch.document_id.in_(ids))
    result: set[uuid.UUID] = set()
    for stmt in (by_category, by_run, by_batch):
        result.update(x for x in (await session.scalars(stmt)).all() if x is not None)
    return result


WITHHELD_NOTE = "Inhalt zurückgehalten: Zahlungsdatei, Freigabe G2 (Zahlungsveranlassung) fehlt."


async def content_released(tenant_id: uuid.UUID, resolver: Any | None = None) -> bool:
    """True only when G2 is open for the tenant (fail closed). Without a resolver the job
    resolver installed at worker start is used (closed by default, ADR 0003). Exports use this
    to keep payment file content out of archives while G2 is closed (AM01)."""
    from mhvp.core import release_gates

    try:
        active = resolver if resolver is not None else release_gates.job_release_gate_resolver
        return await active.is_open(tenant_id, ReleaseGate.G2) is True
    except Exception:
        return False


async def is_payment_file(session: AsyncSession, document: Document) -> bool:
    return bool(await payment_file_ids(session, [document.id]))


async def ensure_released(
    session: AsyncSession, document: Document, tenant_id: uuid.UUID | None, resolver: Any
) -> None:
    """Fail closed with the G2 problem when the document is a payment file and G2 is closed."""
    if await is_payment_file(session, document):
        await ensure_release_gate_open(ReleaseGate.G2, tenant_id, resolver)


async def ensure_not_payment_file(session: AsyncSession, ids: list[uuid.UUID]) -> None:
    """Portal paths never hand out payment files; answers 404 like an invisible document."""
    if await payment_file_ids(session, ids):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


async def recategorize(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Put every referenced payment file into the ``payment_file`` category (data alignment
    for files stored before GAJ-301). Changes only the category, never the content."""
    run, batch = _referencing()
    target = await category_id(session, tenant_id)
    result = await session.execute(
        update(Document)
        .where(
            or_(
                Document.id.in_(select(run.document_id).where(run.document_id.is_not(None))),
                Document.id.in_(select(batch.document_id).where(batch.document_id.is_not(None))),
            ),
            or_(Document.category_id.is_(None), Document.category_id != target),
        )
        .values(category_id=target)
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)
