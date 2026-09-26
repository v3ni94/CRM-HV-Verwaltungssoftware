"""Handover protocols for staff in the portal (M2-08 rest, 26.09.2026):
/api/v1/portal/handover-protocols.

A tenant member with a portal account and the staff portal permission ``handover:read``
(``mhvp.portal.staff_access.DEFAULT_STAFF_PORTAL_PERMISSIONS``, overridable per tenant) reads
every protocol of the own tenant: list with object, unit, date, status and PDF link, detail
without internal fields (same filter as for participants), and the PDF. Read only; writing stays
in the CRM. External portal users (participants, tenants, owners, providers) hold no tenant
wide staff grant and get 403 here; other tenants are invisible through RLS (section 5.3)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.handover import portal as participant_portal
from mhvp.handover import routers as crm
from mhvp.handover import services as svc
from mhvp.handover.models import HandoverProtocol
from mhvp.portal import access
from mhvp.portal.models import AccessGrant, PortalAccount
from mhvp.portal.routers import Portal, portal_user
from mhvp.properties.models import Property, Unit

router = APIRouter(prefix="/portal/handover-protocols", tags=["Portal"])
Ctx = Annotated[Portal, Depends(portal_user)]
PERMISSION = "handover:read"


async def _require_staff(session: Any, account: PortalAccount) -> None:
    if PERMISSION not in await access.staff_permissions(session, account):
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            detail="Für Übergabeprotokolle fehlt das Portalrecht handover:read.",
        )


def _pdf_url(p: HandoverProtocol) -> str:
    """Absolute API path (the portal BFF forwards `/api/v1/...` verbatim)."""
    return f"/api/v1{router.prefix}/{p.id}/pdf"


@router.get("", summary="Übergabeprotokolle des Mandanten (Mitarbeiter)")
async def list_protocols(
    request: Request, ctx: Ctx, include_archived: bool = False
) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _require_staff(session, account)
        query = (
            select(HandoverProtocol, Property.number, Property.name, Unit.number, Unit.label)
            .outerjoin(Property, Property.id == HandoverProtocol.property_id)
            .outerjoin(Unit, Unit.id == HandoverProtocol.unit_id)
            .order_by(HandoverProtocol.number.desc(), HandoverProtocol.version.desc())
        )
        if not include_archived:
            query = query.where(HandoverProtocol.status != "archived")
        rows = (await session.execute(query)).all()
        return [
            {
                "id": p.id,
                "number": p.number,
                "version": p.version,
                "kind": p.kind,
                "status": p.status,
                "handover_date": p.handover_date,
                "address": svc.address_line(p),
                "property": (
                    {"id": p.property_id, "number": prop_number, "name": prop_name}
                    if p.property_id
                    else None
                ),
                "unit": (
                    {"id": p.unit_id, "number": unit_number, "label": unit_label}
                    if p.unit_id
                    else None
                ),
                "unit_number": p.unit_number,
                "unit_label": p.unit_label,
                "floor": p.floor,
                "external_object_number": p.external_object_number,
                "finalized": svc.is_finalized(p),
                "pdf_url": _pdf_url(p),
            }
            for p, prop_number, prop_name, unit_number, unit_label in rows
        ]


@router.get("/{protocol_id}", summary="Übergabeprotokoll lesen (Mitarbeiter)")
async def get_protocol(protocol_id: uuid.UUID, request: Request, ctx: Ctx) -> dict[str, Any]:
    """Same field filter as for participants: internal remarks, the internal contact and the
    management number never leave the CRM, not even for staff reading through the portal."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _require_staff(session, account)
        p = await session.get(HandoverProtocol, protocol_id)
        if p is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        out = participant_portal._public(
            await crm._full_out(session, p), AccessGrant(right="read", valid_to=None)
        )
        out["pdf_url"] = _pdf_url(p)
        return out


@router.get(
    "/{protocol_id}/pdf",
    summary="PDF eines Übergabeprotokolls (Mitarbeiter)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_pdf(
    protocol_id: uuid.UUID, request: Request, ctx: Ctx, download: bool = False
) -> Response:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _require_staff(session, account)
        if await session.get(HandoverProtocol, protocol_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return await crm.get_pdf(protocol_id, request, download, principal)
