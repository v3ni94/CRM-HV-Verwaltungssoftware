"""GA14-02 (structured gate scope), GA14-03 (checklists G2 to G4), GA14-04 (evidence document
and revocation kept apart from the approval). Reuses the shared M2 world."""

import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform.gate_checklists import GATE_CHECKLISTS
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login

pytestmark = pytest.mark.integration

REQ = "/api/v1/tenant/release-gates/requests"


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    # GA14-03: evidence documents need the object store (moto, no network).
    settings = _settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket="mhvp-aa02-gates",
    )
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="mhvp-aa02-gates")
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _doc(client: TestClient, headers: dict[str, str]) -> str:
    r = client.post(
        "/api/v1/documents",
        files={"file": ("nachweis.txt", uuid.uuid4().hex.encode(), "text/plain")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _approve(client: TestClient, world: World, rid: str, headers: dict[str, str]) -> Any:
    return client.post(
        f"/api/v1/platform/tenants/{world.tenant_a}/release-gates/requests/{rid}/approve",
        json={"comment": "geprüft"},
        headers=headers,
    )


def _state(client: TestClient, headers: dict[str, str], gate: str) -> dict[str, Any]:
    rows = client.get("/api/v1/tenant/release-gates", headers=headers).json()
    return dict(next(g for g in rows if g["gate"] == gate))


def test_checklists_listed_and_read_permission(client: TestClient, world: World) -> None:
    reader = bearer(login(client, world, "reader"))
    r = client.get("/api/v1/tenant/release-gates/checklists", headers=reader)
    assert r.status_code == 200
    by_gate = {g["gate"]: g for g in r.json()}
    assert [i["code"] for i in by_gate["G2"]["items"]] == list(GATE_CHECKLISTS[ReleaseGate.G2])
    assert by_gate["G4"]["evidence_document_required"] is True
    assert by_gate["G1"]["items"] == []
    # read only may not request a gate
    body = {"gate": "G2", "scope": "Pilotumfang Objekt", "evidence": "Bericht"}
    assert client.post(REQ, json=body, headers=reader).status_code == 403


def test_request_validation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "padmin2"))
    base = {"gate": "G2", "scope": "Pilotumfang Objekt", "evidence": "Bericht"}
    bad_code = client.post(REQ, json={**base, "checklist": {"nope": "x"}}, headers=h)
    assert bad_code.status_code == 422
    assert bad_code.json()["code"] == "MHVP-GATE-0007"
    bad_fn = client.post(REQ, json={**base, "scope_functions": ["weg_statement"]}, headers=h)
    assert bad_fn.json()["code"] == "MHVP-GATE-0007"
    foreign_doc = client.post(
        REQ, json={**base, "evidence_document_id": str(uuid.uuid4())}, headers=h
    )
    assert foreign_doc.status_code == 422
    assert client.post(REQ, json={**base, "gate": "G9"}, headers=h).status_code == 422


def test_g2_needs_checklist_and_document_then_revoke_keeps_opening(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "padmin2"))
    approver = bearer(login(client, world, "padmin"))
    codes = list(GATE_CHECKLISTS[ReleaseGate.G2])
    partial = dict.fromkeys(codes[:-1], "geprüft")
    rid = client.post(
        REQ,
        json={
            "gate": "G2",
            "scope": "Pilot ohne Nachweis",
            "evidence": "Bericht",
            "checklist": partial,
        },
        headers=h,
    ).json()["id"]
    refused = _approve(client, world, rid, approver)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-GATE-0006"
    assert set(refused.json()["missing"]) == {codes[-1], "evidence_document"}
    assert _state(client, h, "G2")["open"] is False
    client.post(f"{REQ}/{rid}/revoke", json={}, headers=h)

    doc = _doc(client, h)
    rid = client.post(
        REQ,
        json={
            "gate": "G2",
            "scope": "Pilot mit Nachweis",
            "evidence": "Bericht",
            "checklist": dict.fromkeys(codes, "geprüft"),
            "evidence_document_id": doc,
        },
        headers=h,
    ).json()["id"]
    # another tenant id in the platform path finds nothing (RLS)
    other = client.post(
        f"/api/v1/platform/tenants/{world.tenant_b}/release-gates/requests/{rid}/approve",
        json={},
        headers=approver,
    )
    assert other.status_code == 404
    ok = _approve(client, world, rid, approver)
    assert ok.status_code == 200, ok.text
    assert ok.json()["opened_by"] == str(world.users["padmin"])
    assert ok.json()["evidence_document_id"] == doc
    assert _state(client, h, "G2")["open"] is True
    revoked = client.post(f"{REQ}/{rid}/revoke", json={"comment": "Ende Pilot"}, headers=h)
    assert revoked.status_code == 200
    out = revoked.json()
    assert out["status"] == "revoked"
    assert out["opened_by"] == str(world.users["padmin"])
    assert out["decided_by"] == str(world.users["padmin"])
    assert out["revoked_by"] == str(world.users["padmin2"])
    assert out["revoked_at"] is not None
    assert out["revoke_comment"] == "Ende Pilot"
    assert _state(client, h, "G2")["open"] is False


def test_restricted_scope_opens_only_for_the_named_property(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "padmin2"))
    approver = bearer(login(client, world, "padmin"))
    pilot, other_property = uuid.uuid4(), uuid.uuid4()
    doc = _doc(client, h)
    rid = client.post(
        REQ,
        json={
            "gate": "G3",
            "scope": "Pilotobjekt Mietabrechnung",
            "evidence": "Bericht",
            "scope_property_ids": [str(pilot)],
            "scope_functions": ["rent_statement"],
            "checklist": dict.fromkeys(GATE_CHECKLISTS[ReleaseGate.G3], "geprüft"),
            "evidence_document_id": doc,
        },
        headers=h,
    ).json()["id"]
    assert _approve(client, world, rid, approver).status_code == 200
    state = _state(client, h, "G3")
    assert state["open"] is False
    assert state["partially_open"] is True
    resolver = client.app.state.release_gate_resolver  # type: ignore[attr-defined]
    portal = client.portal
    assert portal is not None

    def is_open(**ctx: Any) -> bool:
        async def run() -> bool:
            return bool(await resolver.is_open_for(world.tenant_a, ReleaseGate.G3, **ctx))

        return bool(portal.call(run))

    assert is_open(property_id=pilot, function="rent_statement") is True
    assert is_open(property_id=other_property, function="rent_statement") is False
    assert is_open(property_id=pilot) is False
    assert is_open() is False
    assert bool(portal.call(resolver.is_open, world.tenant_a, ReleaseGate.G3)) is False
    assert bool(portal.call(resolver.is_open, world.tenant_b, ReleaseGate.G3)) is False
    assert client.post(f"{REQ}/{rid}/revoke", json={}, headers=h).status_code == 200
    assert is_open(property_id=pilot, function="rent_statement") is False
