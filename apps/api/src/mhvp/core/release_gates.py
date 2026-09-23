"""Release gates G1 to G5 (section 18.0, ADR 0003).

Development is released, money is not. Every gate is a per tenant flag that is closed by
default. No environment variable or setting can open a gate. The guard applies to API
endpoints and equally to jobs, imports, bulk actions and integrations (rule 0.1.4).

M1 ships only the fail closed resolver. Persistence per tenant (scope, opened by, evidence
document, revocation) arrives with the tenant table in M2.
"""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from fastapi import Request

from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, ProblemError

_log = get_logger("mhvp.release_gates")


class ReleaseGate(StrEnum):
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"

    @property
    def label(self) -> str:
        return GATE_LABELS[self]


GATE_LABELS: dict[ReleaseGate, str] = {
    ReleaseGate.G1: "Produktive Buchführung",
    ReleaseGate.G2: "Zahlungsveranlassung",
    ReleaseGate.G3: "Mietabrechnung",
    ReleaseGate.G4: "WEG-Abrechnung",
    ReleaseGate.G5: "Fremdmandanten",
}


class ReleaseGateResolver(Protocol):
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool: ...


class ClosedReleaseGateResolver:
    """Default resolver: every gate stays closed for every tenant."""

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return False


class ReleaseGateClosedError(ProblemError):
    def __init__(self, gate: ReleaseGate) -> None:
        super().__init__(
            ErrorCodes.RELEASE_GATE_CLOSED,
            detail=(
                f"Die Funktion erfordert die Freigabestufe {gate.value} ({gate.label}). "
                "Sie ist für diesen Mandanten nicht freigegeben."
            ),
            developer_message=f"Release gate {gate.value} is closed for this tenant.",
            extensions={"gate": gate.value},
        )
        self.gate = gate


async def ensure_release_gate_open(
    gate: ReleaseGate, tenant_id: UUID | None, resolver: ReleaseGateResolver
) -> None:
    """Raise :class:`ReleaseGateClosedError` unless the gate is open for the tenant.

    Fails closed: no tenant context, a resolver error or anything but ``True`` means closed.
    """
    if tenant_id is None:
        raise ReleaseGateClosedError(gate)
    try:
        is_open = await resolver.is_open(tenant_id, gate)
    except Exception:
        _log.exception("release_gate_resolver_failed", gate=gate.value)
        raise ReleaseGateClosedError(gate) from None
    if is_open is not True:
        raise ReleaseGateClosedError(gate)


def require_release_gate(gate: ReleaseGate) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency: ``dependencies=[Depends(require_release_gate(ReleaseGate.G1))]``.

    The tenant id is read from ``request.state.tenant_id``, which authentication sets from M2.
    """

    async def dependency(request: Request) -> None:
        resolver: ReleaseGateResolver = getattr(
            request.app.state, "release_gate_resolver", ClosedReleaseGateResolver()
        )
        tenant_id = getattr(request.state, "tenant_id", None)
        await ensure_release_gate_open(
            gate, tenant_id if isinstance(tenant_id, UUID) else None, resolver
        )

    return dependency
