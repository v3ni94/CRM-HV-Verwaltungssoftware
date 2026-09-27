"""End of the management relationship (operator 27.09.2026).

``POST /properties/{id}/terminate`` records who gave notice, the notice date, the end of
management, optional successor contacts and the notice letter, and sets the property to
``terminated`` (``managed_to`` = end of management). ``POST /properties/{id}/reactivate`` is
reserved to the superadmin (``principal.is_superadmin``, ADR 0011) and restores the status the
property had before. ``GET /properties/{id}/termination`` returns the open termination.
Every change is a domain event with an audit diff (``mhvp.core.events``). Product protection
only, no legal rule is claimed (``docs/rules/M4-05-objekt-deaktivieren.md``).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.properties import schemas as s
from mhvp.properties.models import Property, PropertyStatus, PropertyTermination
from mhvp.properties.routers import READ, UPDATE, _get, _property_out

router = APIRouter(tags=["Objekte"])

TERMINABLE = {PropertyStatus.ONBOARDING, PropertyStatus.ACTIVE}


async def open_termination(session: Any, property_id: uuid.UUID) -> PropertyTermination | None:
    row: PropertyTermination | None = await session.scalar(
        select(PropertyTermination).where(
            PropertyTermination.property_id == property_id,
            PropertyTermination.reactivated_at.is_(None),
        )
    )
    return row


async def termination_out(session: Any, row: PropertyTermination) -> s.PropertyTerminationOut:
    out = s.PropertyTerminationOut.model_validate(row)
    for attr, target in (
        ("successor_manager_contact_id", "successor_manager_name"),
        ("successor_owner_contact_id", "successor_owner_name"),
    ):
        contact_id = getattr(row, attr)
        if contact_id is not None:
            contact = await session.get(Contact, contact_id)
            setattr(out, target, contact.display_name if contact is not None else None)
    if row.notice_document_id is not None:
        document = await session.get(Document, row.notice_document_id)
        out.notice_document_title = document.title if document is not None else None
    return out


async def _check_references(session: Any, body: s.PropertyTerminationIn) -> None:
    """Successors and the notice letter must exist in this tenant (RLS hides foreign rows)."""
    for contact_id in (body.successor_manager_contact_id, body.successor_owner_contact_id):
        if contact_id is not None:
            await _get(session, Contact, contact_id)
    if body.notice_document_id is not None:
        await _get(session, Document, body.notice_document_id)


@router.post("/properties/{property_id}/terminate", summary="Verwaltung beenden")
async def terminate_property(
    property_id: uuid.UUID,
    body: s.PropertyTerminationIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PropertyTerminationOut:
    if body.effective_date < body.notice_date:
        raise ProblemError(ErrorCodes.PROPERTY_TERMINATION_DATES)
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        if prop.status not in TERMINABLE or await open_termination(session, prop.id):
            raise ProblemError(ErrorCodes.PROPERTY_NOT_TERMINABLE)
        await _check_references(session, body)
        row = PropertyTermination(
            tenant_id=principal.tenant_id,
            property_id=prop.id,
            previous_status=prop.status,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        old_status, old_to = prop.status.value, prop.managed_to
        prop.status = PropertyStatus.TERMINATED
        prop.managed_to = body.effective_date
        prop.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.terminated",
            entity_type="property",
            entity_id=prop.id,
            actor_user_id=principal.user_id,
            payload={
                "termination_id": str(row.id),
                "terminated_by": body.terminated_by.value,
                "notice_date": body.notice_date.isoformat(),
                "effective_date": body.effective_date.isoformat(),
            },
            changes={
                "status": {"old": old_status, "new": PropertyStatus.TERMINATED.value},
                "managed_to": {
                    "old": old_to.isoformat() if old_to else None,
                    "new": body.effective_date.isoformat(),
                },
            },
        )
        return await termination_out(session, row)


@router.post("/properties/{property_id}/reactivate", summary="Objekt wieder aktivieren")
async def reactivate_property(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> s.PropertyOut:
    if not principal.is_superadmin:
        raise ProblemError(ErrorCodes.PROPERTY_REACTIVATE_SUPERADMIN_ONLY)
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        row = await open_termination(session, prop.id)
        if prop.status is not PropertyStatus.TERMINATED or row is None:
            raise ProblemError(ErrorCodes.PROPERTY_NOT_TERMINATED)
        row.reactivated_at = datetime.now(UTC)
        row.reactivated_by_user_id = principal.user_id
        row.updated_by = principal.user_id
        old_to = prop.managed_to
        prop.status = row.previous_status
        prop.managed_to = None
        prop.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.reactivated",
            entity_type="property",
            entity_id=prop.id,
            actor_user_id=principal.user_id,
            payload={"termination_id": str(row.id), "superadmin": True},
            changes={
                "status": {
                    "old": PropertyStatus.TERMINATED.value,
                    "new": row.previous_status.value,
                },
                "managed_to": {"old": old_to.isoformat() if old_to else None, "new": None},
            },
        )
        return await _property_out(session, prop)


@router.get("/properties/{property_id}/termination", summary="Beendigung lesen")
async def get_termination(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.PropertyTerminationOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        row = await open_termination(session, prop.id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await termination_out(session, row)
