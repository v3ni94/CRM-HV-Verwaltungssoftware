"""ADR 0011: release gate approval by the superadmin without four eyes, only behind the
platform flag ``gate_superadmin_bypass`` (default off). Reuses the shared M2 world:
``padmin`` (platform admin, no membership), ``padmin2`` (platform admin and tenant admin of
tenant A), ``admin`` (tenant admin of A only)."""

import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import Engine, text

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform.gate_checklists import GATE_CHECKLISTS
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login

pytestmark = pytest.mark.integration


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    # GA14-03: evidence documents need the object store (moto, no network).
    settings = _settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket="mhvp-gate-superadmin",
    )
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="mhvp-gate-superadmin")
        with TestClient(create_app(settings)) as test_client:
            yield test_client


SETTINGS = "/api/v1/platform/settings"


def _request_gate(client: TestClient, headers: dict[str, str], gate: str = "G2") -> str:
    # GA14-03: G2 to G4 need the full checklist and an evidence document to be approvable.
    doc = client.post(
        "/api/v1/documents",
        files={"file": ("nachweis.txt", uuid.uuid4().hex.encode(), "text/plain")},
        headers=headers,
    )
    assert doc.status_code == 201, doc.text
    checklist = dict.fromkeys(GATE_CHECKLISTS.get(ReleaseGate(gate), {}), "geprüft")
    created = client.post(
        "/api/v1/tenant/release-gates/requests",
        json={
            "gate": gate,
            "scope": f"Pilot {uuid.uuid4().hex[:6]}",
            "evidence": "Prüfbericht",
            "checklist": checklist,
            "evidence_document_id": doc.json()["id"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["four_eyes"] is True
    return str(created.json()["id"])


def _approve_url(tenant_id: uuid.UUID, request_id: str) -> str:
    return f"/api/v1/platform/tenants/{tenant_id}/release-gates/requests/{request_id}/approve"


def _gate_open(client: TestClient, headers: dict[str, str], gate: str) -> bool:
    state = client.get("/api/v1/tenant/release-gates", headers=headers).json()
    return bool(next(g for g in state if g["gate"] == gate)["open"])


@pytest.fixture
def restored(client: TestClient, world: World) -> Iterator[dict[str, Any]]:
    """Flag off and no superadmin after every test: the world is shared per session."""
    padmin2 = bearer(login(client, world, "padmin2"))
    padmin = bearer(login(client, world, "padmin"))
    yield {"padmin2": padmin2, "padmin": padmin}
    client.patch(SETTINGS, json={"gate_superadmin_bypass": False}, headers=padmin)
    for name in ("padmin", "padmin2"):
        client.delete(f"/api/v1/platform/users/{world.users[name]}/superadmin", headers=padmin)
    assert client.get(SETTINGS, headers=padmin).json()["gate_superadmin_bypass"] is False


def test_platform_settings_default_off_and_platform_admin_only(
    client: TestClient, world: World, restored: dict[str, Any]
) -> None:
    padmin = restored["padmin"]
    current = client.get(SETTINGS, headers=padmin)
    assert current.status_code == 200, current.text
    assert current.json()["gate_superadmin_bypass"] is False
    tenant_admin = bearer(login(client, world, "admin"))
    assert client.get(SETTINGS, headers=tenant_admin).status_code == 403
    assert (
        client.patch(
            SETTINGS, json={"gate_superadmin_bypass": True}, headers=tenant_admin
        ).status_code
        == 403
    )
    assert client.get("/api/v1/platform/superadmin", headers=tenant_admin).status_code == 403
    assert (
        client.put(
            f"/api/v1/platform/users/{world.users['admin']}/superadmin", headers=tenant_admin
        ).status_code
        == 403
    )
    # A tenant administrator without platform rights can never become superadmin.
    refused = client.put(
        f"/api/v1/platform/users/{world.users['admin']}/superadmin", headers=padmin
    )
    assert refused.status_code == 422, refused.text


def test_bypass_off_keeps_four_eyes_even_for_superadmin(
    client: TestClient, world: World, restored: dict[str, Any]
) -> None:
    padmin2 = restored["padmin2"]
    granted = client.put(
        f"/api/v1/platform/users/{world.users['padmin2']}/superadmin", headers=padmin2
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["user_id"] == str(world.users["padmin2"])
    # Superadmin marker alone changes nothing: the flag is off.
    request_id = _request_gate(client, padmin2)
    url = _approve_url(world.tenant_a, request_id)
    same = client.post(url, json={}, headers=padmin2)
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    assert not _gate_open(client, padmin2, "G2")
    # A second decision on an already decided request stays 409 (unchanged behaviour).
    other = bearer(login(client, world, "padmin"))
    assert client.post(url, json={}, headers=other).status_code == 200
    assert client.post(url, json={}, headers=padmin2).status_code == 409
    revoked = client.post(
        f"/api/v1/tenant/release-gates/requests/{request_id}/revoke", json={}, headers=padmin2
    )
    assert revoked.status_code == 200
    assert not _gate_open(client, padmin2, "G2")


def test_bypass_on_superadmin_approves_alone_with_audit(
    client: TestClient, world: World, restored: dict[str, Any], app_engine: Engine
) -> None:
    padmin2, padmin = restored["padmin2"], restored["padmin"]
    assert (
        client.put(
            f"/api/v1/platform/users/{world.users['padmin2']}/superadmin", headers=padmin
        ).status_code
        == 200
    )
    switched = client.patch(SETTINGS, json={"gate_superadmin_bypass": True}, headers=padmin)
    assert switched.status_code == 200, switched.text
    assert switched.json()["gate_superadmin_bypass"] is True
    assert switched.json()["updated_by"] == str(world.users["padmin"])
    assert switched.json()["version"] >= 2

    request_id = _request_gate(client, padmin2)
    url = _approve_url(world.tenant_a, request_id)
    # Self rejection is never covered by the bypass.
    reject = url.replace("/approve", "/reject")
    assert client.post(reject, json={}, headers=padmin2).json()["code"] == "MHVP-GATE-0002"
    approved = client.post(url, json={"comment": "allein"}, headers=padmin2)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["four_eyes"] is False
    assert body["decided_by"] == body["requested_by"] == str(world.users["padmin2"])
    assert _gate_open(client, padmin2, "G2")

    audit = client.get(
        "/api/v1/tenant/audit-log", params={"entity_id": request_id}, headers=padmin2
    ).json()
    changes = [a["changes"] for a in audit if "four_eyes" in a["changes"]]
    assert changes
    assert changes[0]["four_eyes"] == {"old": True, "new": False}
    events = client.get(
        "/api/v1/tenant/events", params={"type": "release_gate.opened"}, headers=padmin2
    ).json()
    event = next(e for e in events if e["entity_id"] == request_id)
    assert event["payload"]["superadmin_bypass"] is True
    assert event["payload"]["four_eyes"] is False
    assert event["actor_user_id"] == str(world.users["padmin2"])

    # A regular approval by a second person keeps four_eyes = true while the flag is on.
    second = _request_gate(client, padmin2, gate="G3")
    regular = client.post(_approve_url(world.tenant_a, second), json={}, headers=padmin)
    assert regular.status_code == 200, regular.text
    assert regular.json()["four_eyes"] is True

    # Tenant separation: the approval lives in tenant A only; tenant B stays closed and the
    # request is invisible under tenant B's id.
    assert (
        client.post(_approve_url(world.tenant_b, request_id), json={}, headers=padmin2).status_code
        == 404
    )
    with app_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_b)}
        )
        rows = conn.execute(
            text("SELECT count(*) FROM release_gate_request WHERE status = 'approved'")
        ).scalar()
    assert rows == 0

    for rid in (request_id, second):
        assert (
            client.post(
                f"/api/v1/tenant/release-gates/requests/{rid}/revoke", json={}, headers=padmin2
            ).status_code
            == 200
        )


def test_bypass_on_does_not_help_a_non_superadmin(
    client: TestClient, world: World, restored: dict[str, Any]
) -> None:
    padmin2, padmin = restored["padmin2"], restored["padmin"]
    # padmin holds the marker, padmin2 (the requester) does not.
    assert (
        client.put(
            f"/api/v1/platform/users/{world.users['padmin']}/superadmin", headers=padmin
        ).status_code
        == 200
    )
    assert client.patch(SETTINGS, json={"gate_superadmin_bypass": True}, headers=padmin).json()[
        "gate_superadmin_bypass"
    ]
    request_id = _request_gate(client, padmin2)
    same = client.post(_approve_url(world.tenant_a, request_id), json={}, headers=padmin2)
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    assert not _gate_open(client, padmin2, "G2")
    # Only one superadmin at a time: the marker cannot be granted a second time.
    conflict = client.put(
        f"/api/v1/platform/users/{world.users['padmin2']}/superadmin", headers=padmin
    )
    assert conflict.status_code == 409, conflict.text
    who = client.get("/api/v1/platform/superadmin", headers=padmin2).json()
    assert who["user_id"] == str(world.users["padmin"])
    assert (
        client.delete(
            f"/api/v1/platform/users/{world.users['padmin']}/superadmin", headers=padmin
        ).status_code
        == 204
    )
    assert client.get("/api/v1/platform/superadmin", headers=padmin2).json()["user_id"] is None
    assert (
        client.post(
            f"/api/v1/platform/tenants/{world.tenant_a}/release-gates/requests/{request_id}/reject",
            json={"comment": "aufgeräumt"},
            headers=padmin,
        ).status_code
        == 200
    )
