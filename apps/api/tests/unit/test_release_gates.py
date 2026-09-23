import uuid

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient

from mhvp.core.config import Settings
from mhvp.core.release_gates import (
    GATE_LABELS,
    ClosedReleaseGateResolver,
    ReleaseGate,
    ReleaseGateClosedError,
    ensure_release_gate_open,
    require_release_gate,
)
from mhvp.main import create_app

TENANT = uuid.UUID("0199a0c0-0000-7000-8000-000000000001")


class OpenResolver:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return True


class BrokenResolver:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        raise RuntimeError("database down")


class TruthyResolver:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return "yes"  # type: ignore[return-value]


def test_exactly_five_gates_with_labels() -> None:
    assert [gate.value for gate in ReleaseGate] == ["G1", "G2", "G3", "G4", "G5"]
    assert ReleaseGate.G1.label == "Produktive Buchführung"
    assert ReleaseGate.G2.label == "Zahlungsveranlassung"
    assert ReleaseGate.G3.label == "Mietabrechnung"
    assert ReleaseGate.G4.label == "WEG-Abrechnung"
    assert ReleaseGate.G5.label == "Fremdmandanten"
    assert set(GATE_LABELS) == set(ReleaseGate)


@pytest.mark.parametrize("gate", list(ReleaseGate))
async def test_default_resolver_keeps_every_gate_closed(gate: ReleaseGate) -> None:
    resolver = ClosedReleaseGateResolver()
    assert await resolver.is_open(uuid.uuid4(), gate) is False
    with pytest.raises(ReleaseGateClosedError) as info:
        await ensure_release_gate_open(gate, uuid.uuid4(), resolver)
    assert info.value.gate is gate


async def test_missing_tenant_context_is_closed_even_for_open_resolver() -> None:
    with pytest.raises(ReleaseGateClosedError):
        await ensure_release_gate_open(ReleaseGate.G1, None, OpenResolver())


async def test_resolver_error_fails_closed() -> None:
    with pytest.raises(ReleaseGateClosedError):
        await ensure_release_gate_open(ReleaseGate.G2, TENANT, BrokenResolver())


async def test_only_true_opens() -> None:
    with pytest.raises(ReleaseGateClosedError):
        await ensure_release_gate_open(ReleaseGate.G2, TENANT, TruthyResolver())
    await ensure_release_gate_open(ReleaseGate.G2, TENANT, OpenResolver())


def test_environment_cannot_open_gates(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    for name in ("MHVP_RELEASE_GATES", "MHVP_G1", "MHVP_GATE_G1", "MHVP_RELEASE_GATE_G1"):
        monkeypatch.setenv(name, "open")
    app = create_app(settings)
    assert isinstance(app.state.release_gate_resolver, ClosedReleaseGateResolver)


def _gated_client(settings: Settings, tenant: uuid.UUID | None, resolver: object) -> TestClient:
    app = create_app(settings, release_gate_resolver=resolver)  # type: ignore[arg-type]

    async def set_tenant(request: Request) -> None:
        request.state.tenant_id = tenant

    @app.post(
        "/bookings",
        dependencies=[Depends(set_tenant), Depends(require_release_gate(ReleaseGate.G1))],
    )
    async def post_booking() -> dict[str, str]:
        return {"booked": "yes"}

    return TestClient(app)


def test_endpoint_guard_returns_problem(settings: Settings) -> None:
    with _gated_client(settings, TENANT, ClosedReleaseGateResolver()) as client:
        response = client.post("/bookings")
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "MHVP-GATE-0001"
    assert body["gate"] == "G1"
    assert "Produktive Buchführung" in body["detail"]


def test_endpoint_guard_passes_when_resolver_opens(settings: Settings) -> None:
    with _gated_client(settings, TENANT, OpenResolver()) as client:
        response = client.post("/bookings")
    assert response.status_code == 200


def test_endpoint_guard_without_tenant_is_closed(settings: Settings) -> None:
    with _gated_client(settings, None, OpenResolver()) as client:
        response = client.post("/bookings")
    assert response.status_code == 403
