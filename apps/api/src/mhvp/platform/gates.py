"""Persistent release gates (ADR 0003): four eyes opening, revocation, resolver."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.release_gates import ReleaseGate
from mhvp.platform.gate_checklists import GateScope, scope_covers
from mhvp.platform.models import GateRequestStatus, ReleaseGateRequest


class DbReleaseGateResolver:
    """A gate is open for a tenant while an approved, not revoked request exists.

    ``is_open`` (no context) only counts approvals without a structured restriction, so an
    approval for one pilot property never opens the gate for the whole tenant (GA14-02).
    ``is_open_for`` evaluates restricted approvals against a property, legal entity or
    function context.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return await self.is_open_for(tenant_id, gate)

    async def is_open_for(
        self,
        tenant_id: uuid.UUID,
        gate: ReleaseGate,
        *,
        property_id: uuid.UUID | None = None,
        legal_entity_id: uuid.UUID | None = None,
        function: str | None = None,
    ) -> bool:
        async with tenant_transaction(self.factory, tenant_id) as session:
            for scope in await approved_gate_scopes(session, tenant_id, gate):
                if scope_covers(
                    scope,
                    property_id=property_id,
                    legal_entity_id=legal_entity_id,
                    function=function,
                ):
                    return True
            return False


async def _approved(
    session: AsyncSession, tenant_id: uuid.UUID, gate: ReleaseGate
) -> list[ReleaseGateRequest]:
    rows = await session.scalars(
        select(ReleaseGateRequest).where(
            ReleaseGateRequest.tenant_id == tenant_id,
            ReleaseGateRequest.gate == gate.value,
            ReleaseGateRequest.status == GateRequestStatus.APPROVED,
        )
    )
    return list(rows)


def scope_of(item: ReleaseGateRequest) -> GateScope:
    return GateScope(
        property_ids=tuple(item.scope_property_ids)
        if item.scope_property_ids is not None
        else None,
        legal_entity_ids=(
            tuple(item.scope_legal_entity_ids) if item.scope_legal_entity_ids is not None else None
        ),
        functions=tuple(item.scope_functions) if item.scope_functions is not None else None,
    )


async def approved_gate_scopes(
    session: AsyncSession, tenant_id: uuid.UUID, gate: ReleaseGate
) -> list[GateScope]:
    return [scope_of(item) for item in await _approved(session, tenant_id, gate)]


async def approved_scopes(
    session: AsyncSession, tenant_id: uuid.UUID, gate: ReleaseGate
) -> list[str]:
    """Free text scopes of all approvals (display)."""
    return [item.scope for item in await _approved(session, tenant_id, gate)]


async def open_without_context(
    session: AsyncSession, tenant_id: uuid.UUID, gate: ReleaseGate
) -> bool:
    return any(s.unrestricted for s in await approved_gate_scopes(session, tenant_id, gate))


def now() -> datetime:
    return datetime.now(UTC)
