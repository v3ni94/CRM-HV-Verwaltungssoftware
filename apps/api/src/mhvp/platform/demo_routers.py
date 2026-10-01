"""Demo flag of a tenant (AE36, AA15-01, rule AE36-DEMO): ``PUT /platform/tenants/{id}/demo``.

Only platform administrators. The flag marks a tenant with invented data (``make seed-demo``)
that is excluded from billing, exports, DATEV and statistics. Setting it is refused for a tenant
with an open release gate (``MHVP-DEMO-0002``): such a tenant works with real data. Every change
is written to the platform audit and the application log.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate
from mhvp.platform.models import PlatformAuditEvent, Tenant

router = APIRouter(tags=["Plattform"])
_log = get_logger("mhvp.platform.demo")


class PlatformDemoFlagIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_demo: bool


class PlatformDemoFlagOut(BaseModel):
    id: uuid.UUID
    slug: str
    is_demo: bool


@router.put(
    "/platform/tenants/{tenant_id}/demo",
    summary="Demo-Kennzeichen eines Mandanten setzen oder entfernen",
)
async def put_demo_flag(
    tenant_id: uuid.UUID,
    body: PlatformDemoFlagIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> PlatformDemoFlagOut:
    resolver = request.app.state.release_gate_resolver
    async with platform_transaction(sessions(request)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.is_demo and not tenant.is_demo:
            open_gates = [g.value for g in ReleaseGate if await resolver.is_open(tenant_id, g)]
            if open_gates:
                raise ProblemError(
                    ErrorCodes.DEMO_TENANT_FLAG_REFUSED,
                    detail=(
                        "Der Mandant hat geöffnete Freigabestufen ("
                        + ", ".join(open_gates)
                        + ") und arbeitet mit echten Daten."
                    ),
                )
        if tenant.is_demo != body.is_demo:
            before = tenant.is_demo
            tenant.is_demo = body.is_demo
            session.add(
                PlatformAuditEvent(
                    actor_user_id=principal.user_id,
                    action="tenant_demo_flag_changed",
                    target_type="tenant",
                    target_id=str(tenant_id),
                    payload={"from": before, "to": body.is_demo},
                )
            )
            _log.warning(
                "tenant_demo_flag_changed",
                actor_user_id=str(principal.user_id),
                tenant_id=str(tenant_id),
                is_demo=body.is_demo,
            )
        return PlatformDemoFlagOut(id=tenant.id, slug=tenant.slug, is_demo=tenant.is_demo)
