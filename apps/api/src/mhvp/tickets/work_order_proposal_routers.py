"""Appointment proposals of a work order for the CRM (A58, A74): read only list of the
proposals a service provider made in the portal with their status and the confirmed
appointment of the order. The provider proposes and the resident accepts through
``mhvp.portal.routers``; the office only sees the result here. Kept out of
``mhvp.tickets.routers`` (module of another work stream)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import ProposalStatus, WorkOrder, WorkOrderAppointmentProposal

router = APIRouter(prefix="/work-orders", tags=["tickets"])
READ = require_permission("tickets:read")


def proposal_out(p: WorkOrderAppointmentProposal) -> dict[str, Any]:
    return {
        "id": p.id,
        "work_order_id": p.work_order_id,
        "starts_at": p.starts_at,
        "note": p.note,
        "status": p.status,
        "proposed_by_contact_id": p.proposed_by_contact_id,
        "decided_by_contact_id": p.decided_by_contact_id,
        "decided_at": p.decided_at,
        "created_at": p.created_at,
    }


@router.get(
    "/{order_id}/appointment-proposals",
    summary="Terminvorschläge des Dienstleisters zum Auftrag mit bestätigtem Termin",
)
async def appointment_proposals(
    order_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id)
        if order is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = (
            await session.scalars(
                select(WorkOrderAppointmentProposal)
                .where(WorkOrderAppointmentProposal.work_order_id == order.id)
                .order_by(
                    WorkOrderAppointmentProposal.created_at.desc(),
                    WorkOrderAppointmentProposal.starts_at,
                )
            )
        ).all()
        accepted = next((p for p in rows if p.status == ProposalStatus.ACCEPTED.value), None)
        return {
            "work_order_id": order.id,
            "ticket_id": order.ticket_id,
            "property_id": order.property_id,
            "provider_contact_id": order.provider_contact_id,
            "description": order.description,
            "status": order.status.value,
            "scheduled_at": order.scheduled_at,
            "confirmed_proposal_id": accepted.id if accepted else None,
            "open_count": sum(1 for p in rows if p.status == ProposalStatus.PROPOSED.value),
            "proposals": [proposal_out(p) for p in rows],
        }
