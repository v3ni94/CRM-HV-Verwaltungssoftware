"""Tenant scoped transactions (ADR 0002, section 5.3).

The tenant id is bound with ``set_config('app.tenant_id', <id>, true)``: transaction local
like ``SET LOCAL``, but parameterised. It disappears at commit or rollback, so a pooled
connection never carries a tenant into the next request. Every query on tenant tables must
run inside :func:`tenant_transaction`; without it RLS returns no rows (fail closed).
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core import crypto

log = logging.getLogger(__name__)

TENANT_SETTING = "app.tenant_id"
_BIND_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")
AFTER_COMMIT_KEY = "mhvp.after_commit"

AfterCommitHook = Callable[[], Awaitable[None]]


def after_commit(session: AsyncSession, hook: AfterCommitHook) -> None:
    """Registers a coroutine factory that :func:`tenant_transaction` runs once the transaction
    has committed (event consumers with side effects outside the database, such as mail
    archiving or queueing a job). Hooks never run after a rollback; a failing hook is logged
    and never affects the committed change. Outside ``tenant_transaction`` the hook is kept
    in ``session.info`` and the caller is responsible for running :func:`run_after_commit`."""
    session.info.setdefault(AFTER_COMMIT_KEY, []).append(hook)


async def run_after_commit(session: AsyncSession) -> int:
    """Runs and clears the hooks registered with :func:`after_commit`. Returns their count."""
    hooks: list[AfterCommitHook] = list(session.info.pop(AFTER_COMMIT_KEY, []))
    for hook in hooks:
        try:
            await hook()
        except Exception:
            log.exception("after-commit hook failed")
    return len(hooks)


@asynccontextmanager
async def tenant_transaction(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> AsyncIterator[AsyncSession]:
    if not isinstance(tenant_id, UUID):
        raise TypeError("tenant_id must be a UUID")
    token = crypto.set_scope(str(tenant_id))
    try:
        async with session_factory() as session:
            async with session.begin():
                await session.execute(_BIND_TENANT, {"tenant_id": str(tenant_id)})
                yield session
            # Reached only after a successful commit: a rollback raises out of the block
            # and the registered hooks are dropped with the session.
            await run_after_commit(session)
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
