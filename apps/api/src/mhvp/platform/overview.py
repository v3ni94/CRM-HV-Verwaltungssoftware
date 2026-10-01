"""Cross tenant working view for platform administrators (M2-05, Produktschutz).

The view never weakens the tenant separation (section 5.3, ADR 0002): every tenant is read in
its own ``tenant_transaction`` with the tenant bound for RLS, only tenants in which the caller
holds an active membership are read (a platform administrator without membership sees nothing,
the superadmin marker of ADR 0011 grants no extra tenant), and the merged lists carry the
tenant id and name on every row. The view is read only: writing stays behind the recorded
tenant switch (``POST /auth/switch-tenant``). Every read is recorded per tenant as the event
``platform.overview_viewed`` so that the tenant's own audit trail shows the cross tenant access.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import (
    GateRequestStatus,
    Membership,
    MembershipStatus,
    ReleaseGateRequest,
    Tenant,
)

router = APIRouter(prefix="/platform/overview", tags=["Plattform"])

EVENT_TYPE = "platform.overview_viewed"
# Deadlines counted as "due": open compliance deadlines due within this window or overdue.
DEADLINE_WINDOW_DAYS = 30
# Priority rank for the urgency sort of tickets (highest first).
_PRIORITY_RANK: dict[str, int] = {
    "immediate": 0,
    "urgent": 1,
    "high": 2,
    "normal": 3,
    "low": 4,
}
_OPEN_TICKET_STATUSES = ("new", "in_progress", "waiting")

View = Literal["overview", "tickets", "properties"]


class TenantRef(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str


class TenantFigures(TenantRef):
    properties: int
    units: int
    open_tickets: int
    deadlines_due: int
    open_approvals: int
    # Kinds behind ``open_approvals`` so the CRM can explain the number.
    approvals: dict[str, int]


class OverviewOut(BaseModel):
    tenants: list[TenantFigures]
    totals: dict[str, int]


class TicketRow(TenantRef):
    id: uuid.UUID
    number: int
    title: str
    status: str
    priority: str
    sla_due_at: datetime | None
    due_on: date | None
    property_id: uuid.UUID | None
    created_at: datetime


class PropertyRow(TenantRef):
    id: uuid.UUID
    number: str
    name: str
    city: str | None
    management_type: str
    status: str
    units: int
    open_tickets: int


async def member_tenants(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> list[tuple[uuid.UUID, str]]:
    """Tenants with an active membership of the user, ordered by name. The platform admin flag
    and the superadmin marker never add a tenant here (M2-05). Demo tenants (AE36) are left out:
    the merged lists are an operating view and must not mix in invented data."""
    async with platform_transaction(factory) as session:
        rows = await session.execute(
            select(Tenant.id, Tenant.name)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE,
                Tenant.is_demo.is_(False),
            )
            .order_by(Tenant.name)
        )
        return [(row.id, row.name) for row in rows]


async def _record(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, view: View
) -> None:
    await emit(
        session,
        tenant_id=tenant_id,
        type=EVENT_TYPE,
        entity_type="tenant",
        entity_id=tenant_id,
        actor_user_id=user_id,
        payload={"view": view, "read_only": True},
    )


def _count(model: Any, *where: Any) -> Any:
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


async def _figures(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, today: date
) -> TenantFigures:
    from mhvp.accounting.direct_debit_models import DirectDebitRun, DirectDebitRunStatus
    from mhvp.accounting.models import DunningRun
    from mhvp.communication.models import Message
    from mhvp.contacts.models import BankAccountApproval, ContactBankAccount
    from mhvp.properties.models import Property, PropertyStatus, Unit
    from mhvp.tickets.models import Ticket
    from mhvp.workspace.models import ComplianceDeadline

    columns = {
        "properties": _count(Property, Property.status != PropertyStatus.TERMINATED),
        "units": _count(Unit),
        "open_tickets": _count(Ticket, Ticket.status.in_(_OPEN_TICKET_STATUSES)),
        "deadlines_due": _count(
            ComplianceDeadline,
            ComplianceDeadline.status == "open",
            ComplianceDeadline.due_on <= today + timedelta(days=DEADLINE_WINDOW_DAYS),
        ),
        "release_gates": _count(
            ReleaseGateRequest, ReleaseGateRequest.status == GateRequestStatus.REQUESTED
        ),
        "bank_accounts": _count(
            ContactBankAccount, ContactBankAccount.approval_status == BankAccountApproval.PENDING
        ),
        "mail": _count(
            Message,
            Message.direction == "out",
            Message.submitted_at.is_not(None),
            Message.approved_at.is_(None),
            Message.sent_at.is_(None),
            Message.rejection_note.is_(None),
        ),
        "dunning_runs": _count(DunningRun, DunningRun.status == "preview"),
        "direct_debits": _count(
            DirectDebitRun, DirectDebitRun.status == DirectDebitRunStatus.DRAFT
        ),
    }
    row = (await session.execute(select(*(q.label(k) for k, q in columns.items())))).one()
    values = {key: int(getattr(row, key)) for key in columns}
    approvals = {
        key: values[key]
        for key in ("release_gates", "bank_accounts", "mail", "dunning_runs", "direct_debits")
    }
    return TenantFigures(
        tenant_id=tenant_id,
        tenant_name=name,
        properties=values["properties"],
        units=values["units"],
        open_tickets=values["open_tickets"],
        deadlines_due=values["deadlines_due"],
        open_approvals=sum(approvals.values()),
        approvals=approvals,
    )


async def _tickets(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, limit: int
) -> list[TicketRow]:
    from mhvp.tickets.models import Ticket

    rows = (
        await session.scalars(
            select(Ticket)
            .where(Ticket.status.in_(_OPEN_TICKET_STATUSES), Ticket.merged_into_ticket_id.is_(None))
            .order_by(Ticket.sla_due_at.asc().nulls_last(), Ticket.number.asc())
            .limit(limit)
        )
    ).all()
    return [
        TicketRow(
            tenant_id=tenant_id,
            tenant_name=name,
            id=t.id,
            number=t.number,
            title=t.title,
            status=t.status.value,
            priority=t.priority.value,
            sla_due_at=t.sla_due_at,
            due_on=t.due_on,
            property_id=t.property_id,
            created_at=t.created_at,
        )
        for t in rows
    ]


async def _properties(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, limit: int
) -> list[PropertyRow]:
    from mhvp.properties.models import Property, PropertyStatus, Unit
    from mhvp.tickets.models import Ticket

    units = (
        select(func.count())
        .select_from(Unit)
        .where(Unit.property_id == Property.id)
        .correlate(Property)
        .scalar_subquery()
    )
    open_tickets = (
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.property_id == Property.id, Ticket.status.in_(_OPEN_TICKET_STATUSES))
        .correlate(Property)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Property, units.label("units"), open_tickets.label("open_tickets"))
        .where(Property.status != PropertyStatus.TERMINATED)
        .order_by(Property.number)
        .limit(limit)
    )
    return [
        PropertyRow(
            tenant_id=tenant_id,
            tenant_name=name,
            id=p.id,
            number=p.number,
            name=p.name,
            city=p.city,
            management_type=p.management_type.value,
            status=p.status.value,
            units=int(u),
            open_tickets=int(o),
        )
        for p, u, o in rows
    ]


def ticket_urgency(row: TicketRow) -> tuple[int, datetime, datetime]:
    """Sort key: highest priority first, then the earliest SLA due time (missing last), then
    the oldest ticket."""
    far = datetime.max.replace(tzinfo=UTC)
    return (
        _PRIORITY_RANK.get(row.priority, len(_PRIORITY_RANK)),
        row.sla_due_at if row.sla_due_at is not None else far,
        row.created_at,
    )


def property_urgency(row: PropertyRow) -> tuple[int, str, str]:
    """Sort key: most open tickets first, then tenant name and property number."""
    return (-row.open_tickets, row.tenant_name, row.number)


def _user_id(principal: Principal) -> uuid.UUID:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="User session required.")
    return principal.user_id


async def _scope(request: Request, principal: Principal) -> list[tuple[uuid.UUID, str]]:
    return await member_tenants(sessions(request), _user_id(principal))


Limit = Annotated[int, Query(ge=1, le=200)]


@router.get("", summary="Kennzahlen je Mandant (Plattformadministrator mit Mitgliedschaft)")
async def overview(
    request: Request, principal: Principal = Depends(require_platform_admin)
) -> OverviewOut:
    """Figures per tenant of the caller's memberships, each read in its own tenant transaction
    (RLS stays in force). Read only; nothing here opens a gate or changes data."""
    user_id = _user_id(principal)
    today = datetime.now(UTC).date()
    figures: list[TenantFigures] = []
    for tenant_id, name in await _scope(request, principal):
        async with tenant_transaction(sessions(request), tenant_id) as session:
            figures.append(await _figures(session, tenant_id, name, today))
            await _record(session, tenant_id, user_id, "overview")
    totals = {
        key: sum(getattr(f, key) for f in figures)
        for key in ("properties", "units", "open_tickets", "deadlines_due", "open_approvals")
    }
    return OverviewOut(tenants=figures, totals=totals)


@router.get(
    "/tickets",
    summary="Offene Tickets über die Mandanten des Aufrufers",
    dependencies=[Depends(strict_query)],
)
async def overview_tickets(
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    limit: Limit = 50,
) -> list[TicketRow]:
    """Open tickets of every membership tenant, at most ``limit`` per tenant, merged and sorted
    by urgency (priority, SLA due time, age). Editing needs the tenant switch."""
    user_id = _user_id(principal)
    merged: list[TicketRow] = []
    for tenant_id, name in await _scope(request, principal):
        async with tenant_transaction(sessions(request), tenant_id) as session:
            merged.extend(await _tickets(session, tenant_id, name, limit))
            await _record(session, tenant_id, user_id, "tickets")
    merged.sort(key=ticket_urgency)
    return merged


@router.get(
    "/properties",
    summary="Objekte über die Mandanten des Aufrufers",
    dependencies=[Depends(strict_query)],
)
async def overview_properties(
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    limit: Limit = 100,
) -> list[PropertyRow]:
    """Active properties of every membership tenant, at most ``limit`` per tenant, merged and
    sorted by open tickets. Editing needs the tenant switch."""
    user_id = _user_id(principal)
    merged: list[PropertyRow] = []
    for tenant_id, name in await _scope(request, principal):
        async with tenant_transaction(sessions(request), tenant_id) as session:
            merged.extend(await _properties(session, tenant_id, name, limit))
            await _record(session, tenant_id, user_id, "properties")
    merged.sort(key=property_urgency)
    return merged
