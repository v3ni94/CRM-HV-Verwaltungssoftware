"""Demo tenant guard (AE36, AA15-01, rule AE36-DEMO).

A demo tenant (``tenant.is_demo``, migration 0392) holds invented data only (``make seed-demo``,
``mhvp.platform.demo_seed``). It must never end up in a real figure or file:

* platform billing: no licence, no usage counter, no billing preview, not counted as a
  productive tenant;
* exports: tenant export (job and request), audit export, journal and DATEV export;
* statistics: operating metrics and the scale monitoring count productive tenants only.

``ensure_not_demo`` answers 409 ``MHVP-DEMO-0001`` for the excluded actions. The flag is set
when the demo tenant is created and, for a tenant created earlier, by a platform administrator
(``PUT /platform/tenants/{id}/demo``). It is refused for a tenant with an open release gate:
such a tenant works with real data.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Tenant, TenantStatus


async def is_demo_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """True when the tenant carries the demo flag (readable in tenant and platform sessions:
    the ``tenant`` table has no row level security)."""
    return bool(await session.scalar(select(Tenant.is_demo).where(Tenant.id == tenant_id)))


async def ensure_not_demo(session: AsyncSession, tenant_id: uuid.UUID, what: str) -> None:
    """Refuses ``what`` for a demo tenant (409 ``MHVP-DEMO-0001``)."""
    if await is_demo_tenant(session, tenant_id):
        raise ProblemError(
            ErrorCodes.DEMO_TENANT_EXCLUDED,
            detail=(
                f"{what} ist für einen Demo-Mandanten ausgeschlossen: Der Mandant enthält nur "
                "erfundene Daten und geht in keine Abrechnung, keinen Export und keine "
                "Statistik ein (AE36)."
            ),
        )


def active_productive_tenants() -> Any:
    """Select of the ids of active tenants without demo tenants (statistics, billing jobs)."""
    return select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE, Tenant.is_demo.is_(False))
