"""Persistent release gates (ADR 0003): four eyes opening, revocation, resolver."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.release_gates import ReleaseGate
from mhvp.platform.models import GateRequestStatus, ReleaseGateRequest


class DbReleaseGateResolver:
    """A gate is open for a tenant while an approved, not revoked request exists."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        async with tenant_transaction(self.factory, tenant_id) as session:
            return await approved_scopes(session, tenant_id, gate) != []


async def approved_scopes(
    session: AsyncSession, tenant_id: uuid.UUID, gate: ReleaseGate
) -> list[str]:
    rows = await session.scalars(
        select(ReleaseGateRequest.scope).where(
            ReleaseGateRequest.tenant_id == tenant_id,
            ReleaseGateRequest.gate == gate.value,
            ReleaseGateRequest.status == GateRequestStatus.APPROVED,
        )
    )
    return list(rows)


def now() -> datetime:
    return datetime.now(UTC)
