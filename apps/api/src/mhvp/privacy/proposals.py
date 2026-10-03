"""Deletion proposals per data type from the deletion profile (GAI-501, GAI-503, GAI-504, AJ12).

Nothing is deleted or anonymised here (V17 open, rule 0.1.3). The run only looks at profiles
that are released *and* have ``auto_propose`` switched on (default off):

* ``contact``: contacts whose ``delete_after`` has passed, not anonymised and without an open
  request, get a ``privacy_erasure_request`` with status ``proposed``. A person accepts it
  (``requested``), a second person releases it (``approved``), the lock check of
  ``mhvp.privacy.erasure`` runs again at every step.
* ``communication``, ``ticket``, ``portal_account``, ``domain_event``: candidates are only
  counted for the preview (older than the retention months; tickets only when done, closed
  or rejected; portal accounts only when expired, revoked or locked). There is no deletion
  path for these types yet; the counts are the work list for the operator.
* ``platform_user``, ``bank_raw``, ``other``: no automatic candidates (platform scope or
  storage class open, see docs/rules/AJ12-loeschvorschlaege.md).

The candidate criteria are a technical work list, not a legal start of the period; the
``start_rule`` text of the profile stays the binding description (ASSUMPTIONS AJ12).
"""

from __future__ import annotations

import asyncio
import calendar
import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.communication.models import Message
from mhvp.contacts.models import Contact
from mhvp.core.clock import local_today
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import DomainEvent, emit
from mhvp.core.logging import get_logger
from mhvp.portal.models import PortalAccount
from mhvp.privacy.erasure import ANONYMIZED_PREFIX, blockers
from mhvp.privacy.models import PrivacyDeletionProfile, PrivacyErasureRequest
from mhvp.tickets.models import Ticket, TicketStatus

log = get_logger("mhvp.privacy.proposals")

OPEN_STATUSES = ("proposed", "requested", "approved")
MAX_PROPOSALS_PER_RUN = 200
COUNTED_TYPES = (
    "communication",
    "ticket",
    "portal_account",
    "domain_event",
    # GAM-404 (AP13, migration 0465): counted only, the period is the operator's (V17, AP13-03).
    "ai_run",
    "call_log",
    "webhook_delivery",
    "postal_job",
)
NOT_PROPOSED = {
    "platform_user": "Plattformbenutzer sind mandantenübergreifend, kein automatischer Vorschlag.",
    "bank_raw": "Aufbewahrungsklasse der Bankrohdaten ist offen (V17), nur dokumentiert.",
    "other": "Keine Datenart hinterlegt, kein automatischer Vorschlag.",
}


def cutoff_for(today: date, months: int) -> datetime:
    """Start of the day ``months`` calendar months before ``today`` (day clamped to month end)."""
    total = today.year * 12 + today.month - 1 - months
    year, month = divmod(total, 12)
    month += 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return datetime.combine(date(year, month, day), time.min, tzinfo=UTC)


async def _contact_candidates(session: AsyncSession, today: date) -> list[uuid.UUID]:
    open_request = (
        select(PrivacyErasureRequest.id)
        .where(
            PrivacyErasureRequest.contact_id == Contact.id,
            PrivacyErasureRequest.status.in_(OPEN_STATUSES),
        )
        .exists()
    )
    rows = await session.scalars(
        select(Contact.id)
        .where(
            Contact.delete_after.is_not(None),
            Contact.delete_after <= today,
            ~Contact.display_name.startswith(ANONYMIZED_PREFIX),
            ~open_request,
        )
        .order_by(Contact.delete_after, Contact.id)
        .limit(MAX_PROPOSALS_PER_RUN)
    )
    return list(rows)


_CREATED_AT_TYPES = ("ai_run", "call_log", "webhook_delivery", "postal_job")


def _created_at_model(data_type: str) -> Any:
    """GAM-404: rows counted by creation time (no deletion path, V17)."""
    if data_type == "ai_run":
        from mhvp.ai.models import AiTaskRun

        return AiTaskRun
    if data_type == "call_log":
        from mhvp.communication.telephony import CallLog

        return CallLog
    if data_type == "webhook_delivery":
        from mhvp.core.webhooks import WebhookDelivery

        return WebhookDelivery
    from mhvp.communication.models import PostalJob

    return PostalJob


async def _count(session: AsyncSession, data_type: str, cutoff: datetime) -> int:
    if data_type == "communication":
        stmt = select(func.count()).select_from(Message).where(Message.created_at < cutoff)
    elif data_type == "ticket":
        stmt = (
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.updated_at < cutoff,
                Ticket.status.in_([TicketStatus.DONE, TicketStatus.CLOSED, TicketStatus.REJECTED]),
            )
        )
    elif data_type == "portal_account":
        stmt = (
            select(func.count())
            .select_from(PortalAccount)
            .where(
                PortalAccount.updated_at < cutoff,
                PortalAccount.status.in_(["expired", "revoked", "locked"]),
            )
        )
    elif data_type in _CREATED_AT_TYPES:
        model = _created_at_model(data_type)
        stmt = select(func.count()).select_from(model).where(model.created_at < cutoff)
    else:  # domain_event
        stmt = select(func.count()).select_from(DomainEvent).where(DomainEvent.occurred_at < cutoff)
    return int(await session.scalar(stmt) or 0)


async def preview(session: AsyncSession, today: date) -> list[dict[str, Any]]:
    """Work list per profile; counts only, nothing changes."""
    out: list[dict[str, Any]] = []
    profiles = await session.scalars(
        select(PrivacyDeletionProfile).order_by(PrivacyDeletionProfile.data_type)
    )
    for profile in profiles:
        cutoff = cutoff_for(today, profile.retention_months)
        item: dict[str, Any] = {
            "data_type": profile.data_type,
            "released": profile.released,
            "auto_propose": profile.auto_propose,
            "retention_months": profile.retention_months,
            "cutoff": cutoff.date(),
            "candidates": None,
            "note": None,
        }
        if profile.data_type == "contact":
            item["candidates"] = len(await _contact_candidates(session, today))
            item["note"] = "Kontakte mit abgelaufenem Löschdatum ohne offenen Antrag."
        elif profile.data_type in COUNTED_TYPES:
            item["candidates"] = await _count(session, profile.data_type, cutoff)
            item["note"] = "Nur Zählung, kein Löschpfad (V17 offen)."
        else:
            item["note"] = NOT_PROPOSED.get(profile.data_type)
        out.append(item)
    return out


async def run_proposals(session: AsyncSession, tenant_id: uuid.UUID, today: date) -> dict[str, Any]:
    """Creates ``proposed`` erasure requests for contacts; only with a released contact profile
    that has ``auto_propose`` on. Returns the counts of the preview as well."""
    created = 0
    profile = await session.scalar(
        select(PrivacyDeletionProfile).where(PrivacyDeletionProfile.data_type == "contact")
    )
    if profile is not None and profile.released and profile.auto_propose:
        for contact_id in await _contact_candidates(session, today):
            contact = await session.get(Contact, contact_id)
            if contact is None:
                continue
            session.add(
                PrivacyErasureRequest(
                    tenant_id=tenant_id,
                    contact_id=contact_id,
                    status="proposed",
                    received_on=today,
                    reason="Löschvorschlag aus dem Löschprofil (automatisch, ohne Wirkung).",
                    blockers=await blockers(session, contact, today),
                )
            )
            created += 1
        await session.flush()
    counts = {
        p["data_type"]: p["candidates"]
        for p in await preview(session, today)
        if p["auto_propose"] and p["released"]
    }
    if created or counts:
        await emit(
            session,
            tenant_id=tenant_id,
            type="privacy.deletion_proposals_created",
            entity_type="privacy_deletion_profile",
            entity_id=profile.id if profile is not None else None,
            actor_user_id=None,
            payload={"created": created, "counts": counts},
        )
    return {"created": created, "counts": counts}


async def proposals_once(settings: Settings, today: date | None = None) -> dict[str, Any]:
    from mhvp.platform.models import Tenant, TenantStatus

    day = today or local_today()
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    report: dict[str, Any] = {"tenants": 0, "created": 0, "errors": []}
    try:
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    result = await run_proposals(session, tenant_id, day)
            except Exception as exc:  # the other tenants must still run
                log.exception("privacy proposals failed", tenant_id=str(tenant_id))
                report["errors"].append(f"{tenant_id}: {type(exc).__name__}")
                continue
            report["tenants"] += 1
            report["created"] += result["created"]
    finally:
        await engine.dispose()
    return report


@shared_task(name="mhvp.privacy.deletion_proposals")
def deletion_proposals() -> dict[str, Any]:
    return asyncio.run(proposals_once(get_settings()))
