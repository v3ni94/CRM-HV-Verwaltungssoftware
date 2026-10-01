"""GA14-02 (AB02): routes hand the object context to ``is_open_for``. A restricted approval
opens only the pilot property; another property and a missing context stay closed (403)."""

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.accounting.routers import _ensure_gate_for_ledger
from mhvp.banking.routers import _ensure_g2_for_batch
from mhvp.core.release_gates import (
    ReleaseGate,
    ReleaseGateClosedError,
    ensure_release_gate_open_for,
)
from mhvp.platform.gate_checklists import GateScope, scope_covers

TENANT = uuid.uuid4()
PILOT = uuid.uuid4()
OTHER = uuid.uuid4()


class ScopedResolver:
    """Mirrors DbReleaseGateResolver.is_open_for with in-memory approvals."""

    def __init__(self, *scopes: GateScope) -> None:
        self.scopes = scopes
        self.calls: list[dict[str, Any]] = []

    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return await self.is_open_for(tenant_id, gate)

    async def is_open_for(self, tenant_id: uuid.UUID, gate: ReleaseGate, **context: Any) -> bool:
        self.calls.append(context)
        return tenant_id == TENANT and any(scope_covers(s, **context) for s in self.scopes)


PILOT_ONLY = GateScope(property_ids=(PILOT,), legal_entity_ids=None, functions=None)
UNRESTRICTED = GateScope(property_ids=None, legal_entity_ids=None, functions=None)


def _check(resolver: Any, **context: Any) -> None:
    asyncio.run(ensure_release_gate_open_for(ReleaseGate.G2, TENANT, resolver, **context))


def test_restricted_approval_opens_only_pilot_property() -> None:
    resolver = ScopedResolver(PILOT_ONLY)
    _check(resolver, property_id=PILOT)
    with pytest.raises(ReleaseGateClosedError) as exc:
        _check(resolver, property_id=OTHER)
    assert exc.value.status == 403
    with pytest.raises(ReleaseGateClosedError):
        _check(resolver)


def test_unrestricted_approval_opens_every_context() -> None:
    resolver = ScopedResolver(UNRESTRICTED)
    _check(resolver, property_id=OTHER)
    _check(resolver)


def test_fail_closed_without_tenant_on_error_and_fallback() -> None:
    with pytest.raises(ReleaseGateClosedError):
        asyncio.run(
            ensure_release_gate_open_for(ReleaseGate.G1, None, ScopedResolver(UNRESTRICTED))
        )

    class Broken:
        async def is_open_for(self, *a: Any, **k: Any) -> bool:
            raise RuntimeError("db down")

        async def is_open(self, *a: Any) -> bool:
            return True

    with pytest.raises(ReleaseGateClosedError):
        _check(Broken(), property_id=PILOT)

    class ContextFree:
        async def is_open(self, *a: Any) -> bool:
            return True

    _check(ContextFree(), property_id=OTHER)


class _Result:
    def __init__(self, row: Any) -> None:
        self.row = row

    def first(self) -> Any:
        return self.row

    def scalar_one_or_none(self) -> Any:
        return self.row


class _Session:
    def __init__(self, row: Any) -> None:
        self.row = row

    async def execute(self, _stmt: Any) -> _Result:
        return _Result(self.row)


def _request(resolver: Any) -> Any:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(release_gate_resolver=resolver))
    )


PRINCIPAL: Any = SimpleNamespace(tenant_id=TENANT)


def test_ledger_route_passes_property_and_legal_entity() -> None:
    entity = uuid.uuid4()
    resolver = ScopedResolver(PILOT_ONLY)
    asyncio.run(
        _ensure_gate_for_ledger(
            _request(resolver), PRINCIPAL, _Session((PILOT, entity)), uuid.uuid4()
        )
    )
    assert resolver.calls[-1] == {"property_id": PILOT, "legal_entity_id": entity, "function": None}
    with pytest.raises(ReleaseGateClosedError):
        asyncio.run(
            _ensure_gate_for_ledger(
                _request(resolver), PRINCIPAL, _Session((OTHER, entity)), uuid.uuid4()
            )
        )
    # unknown ledger: checked without context, so a restricted approval stays closed
    with pytest.raises(ReleaseGateClosedError):
        asyncio.run(
            _ensure_gate_for_ledger(_request(resolver), PRINCIPAL, _Session(None), uuid.uuid4())
        )


def test_payment_batch_route_passes_bank_account_property() -> None:
    resolver = ScopedResolver(PILOT_ONLY)
    asyncio.run(_ensure_g2_for_batch(_request(resolver), PRINCIPAL, _Session(PILOT), uuid.uuid4()))
    with pytest.raises(ReleaseGateClosedError):
        asyncio.run(
            _ensure_g2_for_batch(_request(resolver), PRINCIPAL, _Session(OTHER), uuid.uuid4())
        )
