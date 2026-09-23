"""Tenant scoped transactions (ADR 0002, section 5.3).

The tenant id is bound with ``set_config('app.tenant_id', <id>, true)``: transaction local
like ``SET LOCAL``, but parameterised. It disappears at commit or rollback, so a pooled
connection never carries a tenant into the next request. Every query on tenant tables must
run inside :func:`tenant_transaction`; without it RLS returns no rows (fail closed).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core import crypto

TENANT_SETTING = "app.tenant_id"
_BIND_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")


@asynccontextmanager
async def tenant_transaction(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> AsyncIterator[AsyncSession]:
    if not isinstance(tenant_id, UUID):
        raise TypeError("tenant_id must be a UUID")
    token = crypto.set_scope(str(tenant_id))
    try:
        async with session_factory() as session, session.begin():
            await session.execute(_BIND_TENANT, {"tenant_id": str(tenant_id)})
            yield session
    finally:
        crypto.reset_scope(token)


@asynccontextmanager
async def platform_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transaction without tenant context: only platform tables are visible (RLS)."""
    token = crypto.set_scope(crypto.PLATFORM_SCOPE)
    try:
        async with session_factory() as session, session.begin():
            yield session
    finally:
        crypto.reset_scope(token)
