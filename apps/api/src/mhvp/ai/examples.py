"""Learning examples (``AiExample``): tenant switch and deletion on the deletion of the
records they were built from (ADR 0010, M7-04, rule M19-07).

``ticket_resolution`` examples carry ``features.ticket_id`` and, when the ticket had a
contact, ``features.entitaeten.contact_id``. Deleting a ticket or a contact removes those rows
in the caller's transaction so that no learning example outlives its source (DSGVO, S06).
Deletion is a hard delete: the rows are derived data, not booked records (rule 0.1.7 does not
apply), and the ticket event log keeps the resolution itself.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import AiExample, AiTask


async def learning_examples_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """Per tenant switch ``tenant_settings.ai_learning_examples_enabled`` (default false)."""
    from mhvp.platform.models import TenantSettings

    return bool(
        await session.scalar(
            select(TenantSettings.ai_learning_examples_enabled).where(
                TenantSettings.tenant_id == tenant_id
            )
        )
    )


async def delete_examples_for_ticket(session: AsyncSession, ticket_id: uuid.UUID) -> int:
    """Removes the ``ticket_resolution`` examples of one ticket. Returns the number of rows."""
    result = await session.execute(
        delete(AiExample).where(
            AiExample.task == AiTask.TICKET_RESOLUTION,
            AiExample.features["ticket_id"].astext == str(ticket_id),
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def delete_examples_for_contact(session: AsyncSession, contact_id: uuid.UUID) -> int:
    """Removes the ``ticket_resolution`` examples whose ticket was linked to the contact.
    Returns the number of rows."""
    result = await session.execute(
        delete(AiExample).where(
            AiExample.task == AiTask.TICKET_RESOLUTION,
            AiExample.features["entitaeten"]["contact_id"].astext == str(contact_id),
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
