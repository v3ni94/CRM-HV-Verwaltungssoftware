"""Service provider information in the portal (GA11-04, 14 Dienstleister Phase 4): framework
contracts (service contracts of the provider, read only) and the availability calendar
(windows entered by the management, read only for the provider).

AE30 (AA14-02): ratings of service providers (stars of a completed work order) are internal.
Behind the tenant switch ``provider_rating_display`` (default off) the management sees them
aggregated per provider in the portal administration. Neither the provider nor any other
portal user gets them, and the free text of the rating is never part of the view."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.contacts.models import Contact
from mhvp.contracts.service_contracts import ServiceContract
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import session_allowed_property_ids
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal.models import ProviderAvailability
from mhvp.portal.property_scope import portal_admin_guard
from mhvp.portal.routers import Portal, portal_user
from mhvp.tickets.work_order_rating import WorkOrderRatingIn

router = APIRouter(prefix="/portal", tags=["Portal"])
admin = APIRouter(
    prefix="/portal-admin", tags=["Portal Verwaltung"], dependencies=[Depends(portal_admin_guard)]
)
MANAGE = require_permission("contacts:update")
SETTINGS_READ = require_permission("tenant_settings:read")
RATINGS_READ = require_permission("tickets:read")
RATING_NOTE = (
    "Bewertungen sind interne Einschätzungen der Verwaltung. Die Anzeige gilt nur für die "
    "Verwaltung, nicht für Dienstleister oder Dritte, und enthält keine Freitexte."
)


class PortalLegalEntityChoice(BaseModel):
    """Minimal option for the legal entity selection (id and name only)."""

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    name: str


@admin.get(
    "/legal-entities",
    summary="Rechtsträger zur Auswahl (nur Id und Name, AC04)",
    dependencies=[Depends(strict_query)],
)
async def list_legal_entity_choices(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> list[PortalLegalEntityChoice]:
    """Small read path for the provider portal settings page: the selection needs no
    members:read, only tenant_settings:read. RLS limits it to the own tenant."""
    from mhvp.properties.models import LegalEntity

    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(LegalEntity.id, LegalEntity.name).order_by(LegalEntity.name)
            )
        ).all()
    return [PortalLegalEntityChoice(id=r.id, name=r.name) for r in rows]


def average_rating(counts: dict[int, int]) -> str | None:
    """Mean of the stars (1 to 5) with one decimal, half up; None without ratings."""
    total = sum(counts.values())
    if total == 0:
        return None
    mean = Decimal(sum(star * n for star, n in counts.items())) / Decimal(total)
    return format(mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")


@admin.get(
    "/provider-ratings",
    summary="Bewertungen der Dienstleister (nur Verwaltung, hinter Schalter)",
    dependencies=[Depends(strict_query)],
)
async def provider_ratings(
    request: Request, principal: TenantPrincipal = Depends(RATINGS_READ)
) -> dict[str, Any]:
    """AA14-02: stars of completed work orders aggregated per provider. Default off: the answer
    then carries no data. The view holds counts and the mean only, no free text of the rating
    and no work order text (data minimisation); a member with a property assignment sees only
    the work orders of the assigned properties."""
    from mhvp.portal import features as portal_features
    from mhvp.tickets.models import WorkOrder, WorkOrderRating

    async with tenant_tx(request, principal) as session:
        mode = (await portal_features.get_or_default(session)).provider_rating_display or "off"
        if mode != "staff":
            return {"mode": mode, "enabled": False, "note": RATING_NOTE, "providers": []}
        query = (
            select(WorkOrder.provider_contact_id, WorkOrder.rating, func.count())
            .where(WorkOrder.rating.is_not(None))
            .group_by(WorkOrder.provider_contact_id, WorkOrder.rating)
        )
        new_query = (
            select(WorkOrder.provider_contact_id, WorkOrderRating.stars, func.count())
            .join(WorkOrder, WorkOrder.id == WorkOrderRating.work_order_id)
            .group_by(WorkOrder.provider_contact_id, WorkOrderRating.stars)
        )
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            query = query.where(WorkOrder.property_id.in_(allowed))
            new_query = new_query.where(WorkOrder.property_id.in_(allowed))
        per_provider: dict[uuid.UUID, dict[int, int]] = {}
        for result in (await session.execute(query), await session.execute(new_query)):
            for contact_id, rating, n in result.all():
                counts = per_provider.setdefault(contact_id, {})
                counts[int(rating)] = counts.get(int(rating), 0) + int(n)
        names = {
            row.id: row.display_name
            for row in (
                await session.execute(
                    select(Contact.id, Contact.display_name).where(
                        Contact.id.in_(list(per_provider))
                    )
                )
            ).all()
        }
        providers = [
            {
                "provider_contact_id": contact_id,
                "provider_name": names.get(contact_id),
                "rated_count": sum(counts.values()),
                "average": average_rating(counts),
                "distribution": {str(star): counts.get(star, 0) for star in range(1, 6)},
            }
            for contact_id, counts in per_provider.items()
        ]
        providers.sort(
            key=lambda p: (str(p["provider_name"] or "").lower(), str(p["provider_contact_id"]))
        )
        return {"mode": mode, "enabled": True, "note": RATING_NOTE, "providers": providers}


@router.get(
    "/provider/framework-contracts",
    summary="Eigene Rahmenverträge (Dienstleister)",
    dependencies=[Depends(strict_query)],
)
async def framework_contracts(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    """Only the own contracts; internal notes and the notice calculation stay with the
    management."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ServiceContract)
            .where(ServiceContract.provider_contact_id == account.contact_id)
            .order_by(ServiceContract.starts_at.desc(), ServiceContract.id)
        )
        today = local_today()
        return [
            {
                "id": c.id,
                "title": c.title,
                "starts_at": c.starts_at,
                "ends_at": c.ends_at,
                "cancelled_at": c.cancelled_at,
                "active": _active(c, today),
            }
            for c in rows.all()
        ]


def _active(c: ServiceContract, today: date) -> bool:
    if c.cancelled_at is not None and c.cancelled_at <= today:
        return False
    return c.starts_at <= today and (c.ends_at is None or c.ends_at >= today)


def _out(a: ProviderAvailability) -> dict[str, Any]:
    return {
        "id": a.id,
        "starts_at": a.starts_at,
        "ends_at": a.ends_at,
        "kind": a.kind,
        "note": a.note,
    }


@router.get(
    "/provider/availability",
    summary="Eigener Verfügbarkeitskalender (Dienstleister)",
    dependencies=[Depends(strict_query)],
)
async def own_availability(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ProviderAvailability)
            .where(
                ProviderAvailability.provider_contact_id == account.contact_id,
                ProviderAvailability.ends_at >= datetime.now(UTC),
            )
            .order_by(ProviderAvailability.starts_at, ProviderAvailability.id)
        )
        return [_out(a) for a in rows.all()]


class ProviderAvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_contact_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    kind: str = Field(default="available", pattern="^(available|unavailable)$")
    note: str | None = Field(default=None, max_length=300)


@admin.get(
    "/provider-availability",
    summary="Verfügbarkeit der Dienstleister",
    dependencies=[Depends(strict_query)],
)
async def list_availability(
    request: Request,
    provider_contact_id: uuid.UUID | None = Query(default=None),
    principal: TenantPrincipal = Depends(MANAGE),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(ProviderAvailability).order_by(
            ProviderAvailability.starts_at, ProviderAvailability.id
        )
        if provider_contact_id is not None:
            query = query.where(ProviderAvailability.provider_contact_id == provider_contact_id)
        return [
            {**_out(a), "provider_contact_id": a.provider_contact_id}
            for a in (await session.scalars(query)).all()
        ]


@admin.post("/provider-availability", status_code=201, summary="Verfügbarkeit erfassen")
async def add_availability(
    body: ProviderAvailabilityIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    if body.starts_at.tzinfo is None or body.ends_at.tzinfo is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitzone fehlt.")
    if body.ends_at <= body.starts_at:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ende liegt nicht nach dem Beginn.")
    async with tenant_tx(request, principal) as session:
        if await session.get(Contact, body.provider_contact_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = ProviderAvailability(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            provider_contact_id=body.provider_contact_id,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            kind=body.kind,
            note=(body.note or "").strip() or None,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="provider_availability.created",
            entity_type="provider_availability",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"provider_contact_id": str(row.provider_contact_id), "kind": row.kind},
        )
        return {**_out(row), "provider_contact_id": row.provider_contact_id}


@admin.delete("/provider-availability/{availability_id}", status_code=204)
async def delete_availability(
    availability_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ProviderAvailability, availability_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        provider_contact_id = row.provider_contact_id
        await session.delete(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="provider_availability.deleted",
            entity_type="provider_availability",
            entity_id=availability_id,
            actor_user_id=principal.user_id,
            payload={"provider_contact_id": str(provider_contact_id)},
        )


# Rating of a completed work order by the affected resident (GAF-35, AE30-02) ---------------


def _resident_rating_view(rows: list[Any], mode: str, order_status: Any) -> dict[str, Any]:
    from mhvp.tickets.work_order_rating import RATABLE

    own = next((r for r in rows if r.party == "resident"), None)
    return {
        "mode": mode,
        "can_rate": order_status in RATABLE and own is None,
        "own": {"stars": own.stars, "created_at": own.created_at} if own else None,
    }


@router.get(
    "/work-orders/{order_id}/rating",
    summary="Bewertung des Auftrags (betroffener Bewohner)",
    dependencies=[Depends(strict_query)],
)
async def resident_rating_state(
    order_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """The resident sees whether the order can be rated and the own stars. The provider
    average appears only with the tenant switch ``provider_rating_display`` = all, never the
    free text of any rating, and never for the provider."""
    from mhvp.portal import features as portal_features
    from mhvp.portal.routers import _resident_scope
    from mhvp.tickets.models import WorkOrder, WorkOrderRating
    from mhvp.tickets.work_order_rating import provider_counts

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id)
        if order is None or not await _resident_scope(session, account, order):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        mode = (await portal_features.get_or_default(session)).provider_rating_display or "off"
        rows = list(
            (
                await session.scalars(
                    select(WorkOrderRating).where(
                        WorkOrderRating.work_order_id == order.id,
                        WorkOrderRating.party == "resident",
                    )
                )
            ).all()
        )
        out = _resident_rating_view(rows, mode, order.status)
        out["provider_summary"] = None
        if mode == "all":
            counts = await provider_counts(session, order.provider_contact_id)
            out["provider_summary"] = {
                "rated_count": sum(counts.values()),
                "average": average_rating(counts),
            }
        return out


@router.post(
    "/work-orders/{order_id}/rating",
    status_code=201,
    summary="Auftrag bewerten (betroffener Bewohner, nach Abschluss, einmalig)",
)
async def resident_rate_order(
    order_id: uuid.UUID,
    body: WorkOrderRatingIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.portal.routers import _resident_scope
    from mhvp.tickets.models import WorkOrder
    from mhvp.tickets.work_order_rating import add_rating

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id, with_for_update=True)
        # Provider and everyone outside the resident scope get not found.
        if order is None or not await _resident_scope(session, account, order):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await add_rating(
            session,
            order,
            "resident",
            body,
            tenant_id=principal.tenant_id,
            user_id=None,
            contact_id=account.contact_id,
        )
        return {"id": row.id, "stars": row.stars, "created_at": row.created_at}
