"""Period lock endpoints (/api/v1/accounting/period-locks, P06-02, AE20).

Reading needs ``accounting:read``; creating and the four eyes release ``accounting:approve``;
the tenant switches ``tenant_settings:update``. Nothing here books, sends or deletes.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from mhvp.accounting import period_lock as svc
from mhvp.accounting.models import PeriodLock
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/accounting/period-locks", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")
SETTINGS = require_permission("tenant_settings:update")


@router.get("/settings", summary="Schalter der Periodensperre")
async def get_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> svc.PeriodLockSettingOut:
    async with tenant_tx(request, principal) as session:
        return svc.setting_out(await svc.get_setting(session))


@router.put("/settings", summary="Schalter der Periodensperre ändern")
async def put_settings(
    body: svc.PeriodLockSettingIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> svc.PeriodLockSettingOut:
    async with tenant_tx(request, principal) as session:
        return await svc.update_setting(session, principal.tenant_id, principal.user_id, body)


@router.get("", summary="Periodensperren je Objekt", dependencies=[Depends(strict_query)])
async def list_locks(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    active: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal: TenantPrincipal = Depends(READ),
) -> list[svc.PeriodLockOut]:
    async with tenant_tx(request, principal) as session:
        stmt = select(PeriodLock).order_by(PeriodLock.period_from.desc(), PeriodLock.id)
        if ledger_id is not None:
            stmt = stmt.where(PeriodLock.ledger_id == ledger_id)
        if property_id is not None:
            stmt = stmt.where(PeriodLock.property_id == property_id)
        if active is not None:
            stmt = stmt.where(
                PeriodLock.released_at.is_(None) if active else PeriodLock.released_at.is_not(None)
            )
        rows = (await session.scalars(stmt.limit(limit).offset(offset))).all()
        return [svc.to_out(r) for r in rows]


async def _one(session: Any, lock_id: uuid.UUID) -> PeriodLock:
    row = await session.get(PeriodLock, lock_id)
    if row is None:
        raise ProblemError(ErrorCodes.NOT_FOUND, detail="Sperre nicht gefunden.")
    return row  # type: ignore[no-any-return]


@router.get("/{lock_id}", summary="Periodensperre lesen")
async def get_lock(
    lock_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> svc.PeriodLockOut:
    async with tenant_tx(request, principal) as session:
        return svc.to_out(await _one(session, lock_id))


@router.post("", status_code=201, summary="Periodensperre anlegen")
async def create(
    body: svc.PeriodLockIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> svc.PeriodLockOut:
    async with tenant_tx(request, principal) as session:
        row = await svc.create_lock(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            ledger_id=body.ledger_id,
            property_id=body.property_id,
            period_from=body.period_from,
            period_to=body.period_to,
            reason=body.reason,
        )
        return svc.to_out(row)


@router.post("/{lock_id}/release-request", summary="Aufhebung beantragen")
async def release_request(
    lock_id: uuid.UUID,
    body: svc.PeriodLockReasonIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> svc.PeriodLockOut:
    async with tenant_tx(request, principal) as session:
        await _one(session, lock_id)
        return svc.to_out(
            await svc.request_release(session, lock_id, principal.user_id, body.reason)
        )


@router.post("/{lock_id}/release", summary="Aufhebung freigeben (Vier Augen)")
async def release(
    lock_id: uuid.UUID,
    body: svc.PeriodLockReasonIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> svc.PeriodLockOut:
    async with tenant_tx(request, principal) as session:
        await _one(session, lock_id)
        return svc.to_out(await svc.release(session, lock_id, principal.user_id, body.reason))
