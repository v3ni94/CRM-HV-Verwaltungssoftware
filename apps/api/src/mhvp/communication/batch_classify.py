"""Nightly classification of inbound mails without a suggestion (9.3 batch processing, M7-07).

Caller of the collective run ``mhvp.ai.batch_nightly``: mails that came in before the AI
suggestion existed (or while no provider was released) have ``suggestion_status = none``. The
nightly run gives them the same suggestion as a new mail (``suggest.suggest_for_message``, which
masks IBANs and goes through the gateway: provider release, DPA evidence, budget). Only with the
tenant switch ``ai_automation.batch_mail_classification`` (default off) and a released provider.
Nothing is sent, assigned or posted; the result is a suggestion for the clerk (rule 0.1.6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.communication.models import Message
from mhvp.core.config import Settings
from mhvp.core.logging import get_logger

log = get_logger("mhvp.communication.batch_classify")
MAX_MAILS_PER_RUN = 100
MIN_AGE = timedelta(hours=1)  # fresh mails are handled by the intake itself


async def pending_ids(session: AsyncSession, limit: int = MAX_MAILS_PER_RUN) -> list[uuid.UUID]:
    """Inbound mails with a text and no suggestion yet, oldest first, without duplicates."""
    cutoff = datetime.now(UTC) - MIN_AGE
    rows = await session.scalars(
        select(Message.id)
        .where(
            Message.direction == "in",
            Message.suggestion_status == "none",
            Message.body.is_not(None),
            Message.created_at < cutoff,
            Message.duplicate_of_id.is_(None),
        )
        .order_by(Message.created_at)
        .limit(limit)
    )
    return list(rows.all())


async def run_for_tenant(
    factory: async_sessionmaker[AsyncSession], settings: Settings, tenant_id: uuid.UUID
) -> dict[str, Any]:
    """Classifies up to ``MAX_MAILS_PER_RUN`` mails of one tenant; a failing mail stays
    ``failed`` and the others still run. Returns counts, or ``skipped`` with the reason."""
    from mhvp.ai import automation, gateway
    from mhvp.ai.models import AiTask
    from mhvp.communication.tasks import suggest_message_once
    from mhvp.core.db.tenancy import tenant_transaction

    async with tenant_transaction(factory, tenant_id) as session:
        if not await automation.is_enabled(session, "batch_mail_classification"):
            return {"skipped": "switch_off", "mails": 0}
        try:
            usable, _reasons = await gateway.routes(session, AiTask.CLASSIFY_EMAIL)
        except gateway.GatewayBlockedError:
            return {"skipped": "no_provider", "mails": 0}
        if not usable:
            return {"skipped": "no_provider", "mails": 0}
        ids = await pending_ids(session)
    report: dict[str, Any] = {"mails": 0, "ready": 0, "other": 0}
    for message_id in ids:
        status = await suggest_message_once(settings, tenant_id, message_id)
        report["mails"] += 1
        report["ready" if status == "ready" else "other"] += 1
        if status == "skipped":
            # The gateway blocked (budget or release): the mail stays eligible for the next
            # night and the run for this tenant stops.
            async with tenant_transaction(factory, tenant_id) as session:
                row = await session.get(Message, message_id)
                if row is not None and row.suggestion_status == "skipped":
                    row.suggestion, row.suggestion_status = {}, "none"
            report["blocked"] = True
            break
    return report
