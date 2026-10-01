"""Release gates G1 to G5 (section 18.0, ADR 0003).

Development is released, money is not. Every gate is a per tenant flag that is closed by
default. No environment variable or setting can open a gate. The guard applies to API
endpoints and equally to jobs, imports, bulk actions and integrations (rule 0.1.4).

M1 ships only the fail closed resolver. Persistence per tenant (scope, opened by, evidence
document, revocation) arrives with the tenant table in M2.
"""

import asyncio
import functools
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, ParamSpec, Protocol, TypeVar
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


P = ParamSpec("P")
R = TypeVar("R")

# Resolver for jobs (Celery, imports, bulk). The worker installs the persistent resolver at
# start (``install_job_release_gate_resolver``, GA14-01); without it every gate stays closed.
job_release_gate_resolver: ReleaseGateResolver = ClosedReleaseGateResolver()


class JobDbReleaseGateResolver:
    """Persistent resolver for jobs. Celery tasks run their own event loop per call
    (``asyncio.run``), so every check opens a short lived engine without pool on the runtime
    role; RLS and the approval state of ``release_gate_request`` decide (ADR 0003)."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from mhvp.core.db.engine import create_session_factory
        from mhvp.platform.gates import DbReleaseGateResolver

        engine = create_async_engine(self.database_url, poolclass=NullPool, hide_parameters=True)
        try:
            return await DbReleaseGateResolver(create_session_factory(engine)).is_open(
                tenant_id, gate
            )
        finally:
            await engine.dispose()


def install_job_release_gate_resolver(resolver: ReleaseGateResolver) -> None:
    """Set the resolver used by :func:`release_gated` and job gate checks (worker start)."""
    global job_release_gate_resolver
    job_release_gate_resolver = resolver


def release_gated(gate: ReleaseGate) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Guard for synchronous jobs. The job must receive ``tenant_id`` as keyword argument.

    The check runs before the job body; a closed gate raises :class:`ReleaseGateClosedError`.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tenant: Any = kwargs.get("tenant_id")
            if isinstance(tenant, str):
                try:
                    tenant = UUID(tenant)
                except ValueError:
                    tenant = None
            asyncio.run(
                ensure_release_gate_open(
                    gate, tenant if isinstance(tenant, UUID) else None, job_release_gate_resolver
                )
            )
            return func(*args, **kwargs)

        return wrapper

    return decorator
