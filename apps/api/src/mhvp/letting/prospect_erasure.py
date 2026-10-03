"""Deletion proposal for the contact and documents of a deleted prospect (AN18, GAK-201).

Deleting a prospect removes only the prospect row (with viewings and self disclosure links).
The contact and linked documents are not deleted automatically: when the contact carries no
role other than ``prospect`` and has no open erasure request, a ``privacy_erasure_request``
with status ``proposed`` is created that names the documents linked to the prospect or the
contact. The privacy process (acceptance, second person release, lock check) decides; how
contacts with further roles and self disclosure documents are kept is question AN18-02.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact
from mhvp.documents.models import DocumentLink
from mhvp.letting.models import Prospect

OPEN_STATUSES = ("proposed", "requested", "approved")
_MAX_IDS = 10


async def linked_documents(
    session: AsyncSession, prospect_id: uuid.UUID, contact_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = await session.scalars(
        select(DocumentLink.document_id)
        .where(
            or_(
                (DocumentLink.entity_type == "prospect") & (DocumentLink.entity_id == prospect_id),
                (DocumentLink.entity_type == "contact") & (DocumentLink.entity_id == contact_id),
            )
        )
        .distinct()
    )
    return sorted(set(rows))


async def propose_for(
    session: AsyncSession, tenant_id: uuid.UUID, prospect: Prospect, today: date
) -> str:
    """Record the proposal before ``prospect`` is deleted; returns the outcome code
    (``proposed``, ``other_roles``, ``open_request``, ``other_prospect``, ``missing``)."""
    from mhvp.privacy.erasure import blockers
    from mhvp.privacy.models import PrivacyErasureRequest

    contact = await session.get(Contact, prospect.contact_id)
    if contact is None:
        return "missing"
    if any(r != "prospect" for r in contact.roles or []):
        return "other_roles"
    other = await session.scalar(
        select(Prospect.id)
        .where(Prospect.contact_id == contact.id, Prospect.id != prospect.id)
        .limit(1)
    )
    if other is not None:
        return "other_prospect"
    pending = await session.scalar(
        select(PrivacyErasureRequest.id)
        .where(
            PrivacyErasureRequest.contact_id == contact.id,
            PrivacyErasureRequest.status.in_(OPEN_STATUSES),
        )
        .limit(1)
    )
    if pending is not None:
        return "open_request"
    docs = await linked_documents(session, prospect.id, contact.id)
    listed = ", ".join(str(d) for d in docs[:_MAX_IDS])
    reason = (
        "Löschvorschlag nach Löschung des Interessenten (GAK-201, ohne Wirkung). "
        f"Verknüpfte Dokumente: {len(docs)}"
        + (f" ({listed}{', ...' if len(docs) > _MAX_IDS else ''})" if docs else "")
        + ". Dokumente nach den Löschregeln des Dokumentenarchivs prüfen."
    )[:1000]
    session.add(
        PrivacyErasureRequest(
            tenant_id=tenant_id,
            contact_id=contact.id,
            status="proposed",
            received_on=today,
            reason=reason,
            blockers=await blockers(session, contact, today),
        )
    )
    return "proposed"
