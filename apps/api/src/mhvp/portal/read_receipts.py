"""Read receipts of portal documents (11.3, D34, A53).

A receipt is written when a portal account opens (metadata) or downloads (content) a document
through the portal. It is an indication only: it is neither a delivery ("Zustellung", see
``mhvp.communication`` dispatch evidence) nor a legally assessed receipt ("Zugang"), it changes
no dispatch status and starts no deadline. Listing documents writes nothing."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.portal.models import PortalAccount, PortalReadReceipt

KINDS = ("opened", "downloaded")
# Wording used by the API and both user interfaces so the legal status is never overstated.
LEGAL_NOTE = (
    "Indiz für den Abruf über das Portal. Keine Zustellung und kein rechtlich bewerteter "
    "Zugang; Zustellnachweise und Zugangsdatum werden getrennt geführt."
)


async def record(
    session: AsyncSession, account: PortalAccount, document_id: uuid.UUID, kind: str
) -> PortalReadReceipt:
    if kind not in KINDS:
        raise ValueError(kind)
    row = PortalReadReceipt(
        tenant_id=account.tenant_id,
        created_by=account.user_id,
        account_id=account.id,
        document_id=document_id,
        kind=kind,
        occurred_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


async def for_document(session: AsyncSession, document_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(PortalReadReceipt, PortalAccount.contact_id)
            .join(PortalAccount, PortalAccount.id == PortalReadReceipt.account_id)
            .where(PortalReadReceipt.document_id == document_id)
            .order_by(PortalReadReceipt.occurred_at.desc())
        )
    ).all()
    return [
        {
            "id": r.id,
            "account_id": r.account_id,
            "contact_id": contact_id,
            "kind": r.kind,
            "occurred_at": r.occurred_at,
        }
        for r, contact_id in rows
    ]


async def states_for_account(
    session: AsyncSession, account: PortalAccount, document_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, datetime]]:
    """Per document the first and last retrieval by this account (M21-02, SA-06): the basis of
    the status "neu" (no receipt yet) and "gelesen" in the portal list. Read only; same
    indication character as every receipt (see ``LEGAL_NOTE``)."""
    if not document_ids:
        return {}
    rows = (
        await session.execute(
            select(
                PortalReadReceipt.document_id,
                func.min(PortalReadReceipt.occurred_at),
                func.max(PortalReadReceipt.occurred_at),
            )
            .where(
                PortalReadReceipt.account_id == account.id,
                PortalReadReceipt.document_id.in_(document_ids),
            )
            .group_by(PortalReadReceipt.document_id)
        )
    ).all()
    return {doc: {"first": first, "last": last} for doc, first, last in rows}
