"""Owner portal: inspection requests (GAJ-202, section 7.9.3 PÜ10, PÜ12, PÜ13 and 14).

An owner files a request to inspect the administration documents of the own community and
follows its status. The request lands in the existing CRM process (``hoa_inspection_request``,
status ``requested``); release, provision and rejection stay with the management. The portal
route is an additional channel, not a duty (PÜ12): it is offered only with the existing switch
``portal_owner_receipts_enabled`` (AG09, default off). The portal shows the status trail only,
never internal notes of the management."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.inspection import SCOPE_KINDS, InspectionEvent, InspectionRequest, _trail
from mhvp.portal import features as portal_features
from mhvp.portal.owner import _owner_scope
from mhvp.portal.routers import Portal, portal_user

router = APIRouter(prefix="/portal/owner", tags=["Portal"])
NOTE_OFF = "Einsichtsanfragen über das Portal sind für Ihre Verwaltung nicht freigeschaltet."
NOTE = (
    "Ihre Anfrage wird von der Verwaltung geprüft. Den Weg der Einsicht (Portal, Datenträger, "
    "vor Ort) stimmt die Verwaltung mit Ihnen ab."
)


class PortalInspectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_entity_id: uuid.UUID
    scope_kinds: list[str] = Field(default_factory=list, max_length=4)
    scope_text: str | None = Field(default=None, max_length=4000)


class PortalInspectionStepOut(BaseModel):
    to_status: str | None
    occurred_at: datetime


class PortalInspectionOut(BaseModel):
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    requested_on: date
    scope_kinds: list[str]
    scope_text: str | None
    status: str
    delivery_kind: str | None
    steps: list[PortalInspectionStepOut] = Field(default_factory=list)


class PortalInspectionCommunityOut(BaseModel):
    id: uuid.UUID
    name: str


class PortalInspectionListOut(BaseModel):
    enabled: bool
    note: str
    items: list[PortalInspectionOut]
    communities: list[PortalInspectionCommunityOut] = Field(default_factory=list)


async def _enabled(session: AsyncSession) -> bool:
    return bool((await portal_features.get_or_default(session)).portal_owner_receipts_enabled)


async def _out(session: AsyncSession, row: InspectionRequest) -> PortalInspectionOut:
    events = (
        await session.scalars(
            select(InspectionEvent)
            .where(InspectionEvent.request_id == row.id, InspectionEvent.kind == "status")
            .order_by(InspectionEvent.occurred_at, InspectionEvent.id)
        )
    ).all()
    out = PortalInspectionOut.model_validate(row, from_attributes=True)
    out.steps = [
        PortalInspectionStepOut(to_status=e.to_status, occurred_at=e.occurred_at) for e in events
    ]
    return out


@router.get(
    "/inspection-requests",
    summary="Eigene Einsichtsanfragen (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def list_owner_inspections(
    request: Request, ctx: Portal = Depends(portal_user)
) -> PortalInspectionListOut:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, _ = await _owner_scope(session, account, local_today())
        if not await _enabled(session):
            return PortalInspectionListOut(enabled=False, note=NOTE_OFF, items=[])
        rows = (
            await session.scalars(
                select(InspectionRequest)
                .where(
                    InspectionRequest.applicant_contact_id == account.contact_id,
                    InspectionRequest.legal_entity_id.in_(hoa_ids),
                )
                .order_by(InspectionRequest.requested_on.desc(), InspectionRequest.id.desc())
            )
        ).all()
        from mhvp.properties.models import LegalEntity

        entities = (
            await session.scalars(
                select(LegalEntity).where(LegalEntity.id.in_(hoa_ids)).order_by(LegalEntity.name)
            )
        ).all()
        return PortalInspectionListOut(
            enabled=True,
            note=NOTE,
            items=[await _out(session, r) for r in rows],
            communities=[PortalInspectionCommunityOut(id=e.id, name=e.name) for e in entities],
        )


@router.get(
    "/inspection-requests/{request_id}",
    summary="Einsichtsanfrage mit Statusverlauf (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def get_owner_inspection(
    request_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> PortalInspectionOut:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, _ = await _owner_scope(session, account, local_today())
        row = await session.get(InspectionRequest, request_id)
        if (
            row is None
            or not await _enabled(session)
            or row.applicant_contact_id != account.contact_id
            or row.legal_entity_id not in hoa_ids
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _out(session, row)


@router.post(
    "/inspection-requests",
    status_code=201,
    summary="Einsichtsanfrage stellen (Eigentümer)",
)
async def create_owner_inspection(
    body: PortalInspectionIn, request: Request, ctx: Portal = Depends(portal_user)
) -> PortalInspectionOut:
    unknown = [k for k in body.scope_kinds if k not in SCOPE_KINDS]
    if unknown:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Umfang unbekannt: {', '.join(unknown)}.")
    if not body.scope_kinds and not (body.scope_text or "").strip():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Bitte den Umfang der Einsicht angeben.")
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, _ = await _owner_scope(session, account, local_today())
        if not await _enabled(session):
            raise ProblemError(ErrorCodes.FORBIDDEN, detail=NOTE_OFF)
        if body.legal_entity_id not in hoa_ids:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        from mhvp.properties.models import LegalEntity

        entity = await session.get(LegalEntity, body.legal_entity_id)
        if entity is None or entity.property_id is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = InspectionRequest(
            tenant_id=principal.tenant_id,
            legal_entity_id=entity.id,
            property_id=entity.property_id,
            applicant_contact_id=account.contact_id,
            requested_on=local_today(),
            scope_text=(body.scope_text or "").strip() or None,
            scope_kinds=sorted(set(body.scope_kinds)),
            status="requested",
            created_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await _trail(session, principal, row, kind="status", to_status="requested", via="portal")
        return await _out(session, row)
