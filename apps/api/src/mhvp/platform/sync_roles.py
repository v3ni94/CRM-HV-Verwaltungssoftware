"""``python -m mhvp.platform.sync_roles``: add new template permissions to system roles.

Runs in the migrate job after Alembic, so permissions of new milestones (e.g. contacts in M3)
reach existing tenants. Only adds; tenant specific roles are never touched.
"""

import asyncio
import sys

from sqlalchemy import select

from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.logging import configure_logging, get_logger
from mhvp.platform.models import Tenant
from mhvp.platform.services import ensure_system_roles
from mhvp.properties.defaults import ensure_tenant_defaults


async def run() -> int:
    settings = get_settings()
    configure_logging(settings)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            tenant_ids = list(await session.scalars(select(Tenant.id)))
        for tenant_id in tenant_ids:
            async with tenant_transaction(factory, tenant_id) as session:
                await ensure_system_roles(session, tenant_id)
                await ensure_tenant_defaults(session, tenant_id)
        get_logger("mhvp.sync_roles").info("system_roles_synced", tenants=len(tenant_ids))
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
