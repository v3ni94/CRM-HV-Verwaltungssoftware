"""AB02: GA14-02 context check against the persistent resolver and GA14-04 platform overview
(GET /platform/tenants/{id}/release-gates). Uses the AA02 gate world (M2 users)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import (
    ReleaseGate,
    ReleaseGateClosedError,
    ensure_release_gate_open_for,
)
from mhvp.platform.gate_checklists import GATE_CHECKLISTS
from tests.integration.test_aa02_gate_scope_evidence import REQ, _approve, _doc, client
from tests.integration.test_m2_platform import World, bearer, login

pytestmark = pytest.mark.integration
__all__ = ["client"]


def _overview(c: TestClient, tenant: uuid.UUID, headers: dict[str, str]) -> dict:  # type: ignore[type-arg]
    r = c.get(f"/api/v1/platform/tenants/{tenant}/release-gates", headers=headers)
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_restricted_g2_opens_only_pilot_property_and_overview(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "padmin2"))
    approver = bearer(login(client, world, "padmin"))
    pilot, other = uuid.uuid4(), uuid.uuid4()
    rid = client.post(
        REQ,
        json={
            "gate": "G2",
            "scope": "Pilotobjekt Zahlungen AB02",
            "evidence": "Bericht",
            "scope_property_ids": [str(pilot)],
            "checklist": dict.fromkeys(GATE_CHECKLISTS[ReleaseGate.G2], "geprüft"),
            "evidence_document_id": _doc(client, h),
        },
        headers=h,
    ).json()["id"]
    assert _approve(client, world, rid, approver).status_code == 200

    resolver = client.app.state.release_gate_resolver  # type: ignore[attr-defined]
    portal = client.portal
    assert portal is not None

    def check(property_id: uuid.UUID | None) -> None:
        async def run() -> None:
            await ensure_release_gate_open_for(
                ReleaseGate.G2, world.tenant_a, resolver, property_id=property_id
            )

        portal.call(run)

    check(pilot)
    for ctx in (other, None):
        with pytest.raises(ReleaseGateClosedError):
            check(ctx)

    # Platform overview: state and request with opening data; other tenant shows nothing.
    data = _overview(client, world.tenant_a, approver)
    g2 = next(g for g in data["gates"] if g["gate"] == "G2")
    assert g2["open"] is False
    assert g2["partially_open"] is True
    row = next(r for r in data["requests"] if r["id"] == rid)
    assert row["opened_by"] == str(world.users["padmin"])
    assert row["opened_at"]
    assert all(r["id"] != rid for r in _overview(client, world.tenant_b, approver)["requests"])
    # tenant users without platform admin may not read the platform view
    reader = bearer(login(client, world, "reader"))
    denied = client.get(f"/api/v1/platform/tenants/{world.tenant_a}/release-gates", headers=reader)
    assert denied.status_code == 403
    assert (
        client.post(f"{REQ}/{rid}/revoke", json={"comment": "Ende"}, headers=h).status_code == 200
    )
    with pytest.raises(ReleaseGateClosedError):
        check(pilot)
