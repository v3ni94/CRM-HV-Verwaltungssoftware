"""AF08 / GAA-02 (PÜ10, PÜ13, W07): consumer of ``contract.ownership_transferred``.

Reads the ownership transfer events of the tenant (outbox ``domain_event``) and adds an owner
check note to every open inspection request of the same property whose applicant is a member
of the previous owner party. The note is a hint for the manager: the request is never closed,
a provided package is never revoked automatically (open question P08-02). Idempotent through
``hoa_inspection_event.source_event_id`` (unique per request and event, migration 0402).
Runs from ``POST /hoa/inspection-requests/ownership-transfers/scan`` and the hourly beat job
``mhvp.hoa.inspection_ownership_scan``.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.events import DomainEvent, emit

EVENT_TYPE = "contract.ownership_transferred"
OPEN_STATUSES = ("requested", "released", "provided", "retrieved")
NOTE = (
    "Eigentümerwechsel der Einheit zum {day} erfasst (Vorgang {event}). Der Antragsteller gehört "
    "zur bisherigen Eigentümerseite: Eigentümerstellung und eine aktive Bereitstellung prüfen "
    "(Rechtsfrage P08-02). Die Anfrage wurde nicht geschlossen."
)


async def note_ownership_transfers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    *,
    legal_entity_ids: Any = None,
    property_ids: Any = None,
) -> dict[str, int]:
    """``legal_entity_ids`` / ``property_ids``: scope of a restricted membership (None: all)."""
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.hoa.inspection import ENTITY, InspectionEvent, InspectionRequest

    counts = {"events": 0, "noted": 0}
    events = (
        await session.scalars(
            select(DomainEvent)
            .where(DomainEvent.type == EVENT_TYPE)
            .order_by(DomainEvent.occurred_at, DomainEvent.id)
        )
    ).all()
    for event in events:
        previous = (event.payload or {}).get("previous")
        try:
            old_id = uuid.UUID(str(previous))
        except ValueError:
            continue
        old = await session.get(Contract, old_id)
        if old is None:
            continue
        counts["events"] += 1
        members = select(PartyMember.contact_id).where(PartyMember.party_id == old.party_id)
        query = select(InspectionRequest).where(
            InspectionRequest.property_id == old.property_id,
            InspectionRequest.status.in_(OPEN_STATUSES),
            InspectionRequest.applicant_contact_id.in_(members),
        )
        if legal_entity_ids is not None:
            query = query.where(InspectionRequest.legal_entity_id.in_(list(legal_entity_ids)))
        if property_ids is not None:
            query = query.where(InspectionRequest.property_id.in_(list(property_ids)))
        requests = (await session.scalars(query)).all()
        for row in requests:
            done = await session.scalar(
                select(InspectionEvent.id).where(
                    InspectionEvent.request_id == row.id,
                    InspectionEvent.source_event_id == event.id,
                )
            )
            if done is not None:
                continue
            day = str((event.payload or {}).get("title_transfer_date") or "")
            shown = day
            if len(day) == 10:
                shown = f"{day[8:10]}.{day[5:7]}.{day[0:4]}"
            session.add(
                InspectionEvent(
                    tenant_id=tenant_id,
                    request_id=row.id,
                    kind="owner_check",
                    note=NOTE.format(day=shown, event=event.id),
                    actor_user_id=actor_user_id,
                    occurred_at=datetime.now(UTC),
                    source_event_id=event.id,
                )
            )
            await emit(
                session,
                tenant_id=tenant_id,
                type="hoa_inspection.owner_check",
                entity_type=ENTITY,
                entity_id=row.id,
                actor_user_id=actor_user_id,
                payload={
                    "status": row.status,
                    "source_event_id": str(event.id),
                    "previous_contract_id": str(old.id),
                    "automatic": "true",
                },
            )
            counts["noted"] += 1
    await session.flush()
    return counts


async def run_once(settings: Settings) -> dict[str, int]:
    from mhvp.core.db.engine import create_session_factory
    from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
    from mhvp.platform.models import Tenant, TenantStatus

    totals = {"tenants": 0, "events": 0, "noted": 0}
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                totals["tenants"] += 1
                for key, value in (
                    await note_ownership_transfers(session, tenant_id, None)
                ).items():
                    totals[key] += value
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.hoa.inspection_ownership_scan")
def inspection_ownership_scan_job() -> dict[str, Any]:
    return asyncio.run(run_once(get_settings()))
