"""Learning examples (``AiExample``): tenant switch and deletion on the deletion of the
records they were built from (ADR 0010, M7-04, rule M19-07).

``ticket_resolution`` examples carry ``features.ticket_id`` and, when the ticket had a
contact, ``features.entitaeten.contact_id``. Deleting a ticket or a contact removes those rows
in the caller's transaction so that no learning example outlives its source (DSGVO, S06).
Deletion is a hard delete: the rows are derived data, not booked records (rule 0.1.7 does not
apply), and the ticket event log keeps the resolution itself.

Retention (operator decision 27.09.2026, "Vollständig speichern mit Mandantenschalter"): the
examples are stored in full while the tenant switch is on and deleted by the daily job
``mhvp.ai.examples_retention`` once they are older than
``tenant_settings.ai_learning_examples_retention_months`` (default ``DEFAULT_RETENTION_MONTHS``).
Every tenant run is journaled as the event ``ai_examples.retention`` with the counts.
"""

import calendar
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import AiExample, AiTask
from mhvp.core.events import emit
from mhvp.core.logging import get_logger

log = get_logger("mhvp.ai.examples")
DEFAULT_RETENTION_MONTHS = 24
RETENTION_EVENT = "ai_examples.retention"


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


async def retention_months(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Per tenant ``tenant_settings.ai_learning_examples_retention_months`` (default 24)."""
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(
        select(TenantSettings.ai_learning_examples_retention_months).where(
            TenantSettings.tenant_id == tenant_id
        )
    )
    return int(value) if value else DEFAULT_RETENTION_MONTHS


def retention_cutoff(now: datetime, months: int) -> datetime:
    """Examples created before this moment are deleted (calendar months, not 30 day blocks;
    the day is clamped to the last day of the target month, e.g. 31.05. minus 3 is 29.02.)."""
    index = now.year * 12 + (now.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)


async def purge_expired_examples(
    session: AsyncSession, tenant_id: uuid.UUID, now: datetime | None = None
) -> dict[str, Any]:
    """Deletes the examples of one tenant older than its retention period and journals the run
    as ``ai_examples.retention`` (counts before, deleted, remaining, cut-off, months). Runs in
    the caller's tenant transaction (RLS limits the rows to the tenant)."""
    moment = now or datetime.now(UTC)
    months = await retention_months(session, tenant_id)
    cutoff = retention_cutoff(moment, months)
    before = int(await session.scalar(select(func.count()).select_from(AiExample)) or 0)
    result = await session.execute(delete(AiExample).where(AiExample.created_at < cutoff))
    deleted = int(result.rowcount or 0)  # type: ignore[attr-defined]
    summary = {
        "retention_months": months,
        "cutoff": cutoff.isoformat(),
        "before": before,
        "deleted": deleted,
        "remaining": before - deleted,
    }
    await emit(
        session,
        tenant_id=tenant_id,
        type=RETENTION_EVENT,
        entity_type="ai_examples",
        entity_id=None,
        actor_user_id=None,
        payload=summary,
    )
    log.info("ai examples retention", tenant_id=str(tenant_id), **summary)
    return summary
