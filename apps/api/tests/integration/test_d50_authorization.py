"""Annex D case D50 (A04, rule 0.1.4): a user with read only rights tries financial changes
through every mass and side path.

Covered paths:

* every writing mass endpoint from ``apps/api/openapi.json`` whose path contains ``bulk``,
  ``apply``, ``approve``, ``run``, ``release``, ``post`` or ``confirm``, called with the system
  role ``read_only`` and with an API key that only carries ``*:read`` scopes; the server has to
  answer 403 (never 2xx, never 500);
* release gates G1 to G5 on mass endpoints (payment batch, WEG statement posting) and on jobs
  (``release_gated`` and the persistent resolver): closed by default for every tenant;
* Celery jobs run system side without a principal; the authorization of a job is the guarded
  endpoint that enqueues it (``.../runs`` endpoints are part of the list above).

The result table is documented in ``docs/reviews/2026-09-26-d50-berechtigungen.md``.
"""

import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.auth.permissions import READ_ALL
from mhvp.core.release_gates import (
    ReleaseGate,
    ReleaseGateClosedError,
    job_release_gate_resolver,
    release_gated,
)
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login

pytestmark = pytest.mark.integration

OPENAPI = Path(__file__).resolve().parents[2] / "openapi.json"
MASS_PATTERN = re.compile(r"bulk|apply|approve|run|release|post|confirm", re.IGNORECASE)
READ_METHODS = {"get", "head", "options"}
FORBIDDEN_CODES = {"MHVP-AUTH-0003"}


def mass_endpoints() -> list[tuple[str, str]]:
    """All writing endpoints of the exported OpenAPI whose path matches the mass pattern."""
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    rows: list[tuple[str, str]] = []
    for path, operations in sorted(spec["paths"].items()):
        if not MASS_PATTERN.search(path):
            continue
        for method in sorted(operations):
            if method.lower() in READ_METHODS:
                continue
            rows.append((method.upper(), path))
    return rows


ENDPOINTS = mass_endpoints()

# Endpoints whose permission check runs inside the handler (per action) need a body that
# passes request validation, otherwise 422 is answered before the guard is reached.
VALID_BODIES: dict[str, dict[str, Any]] = {
    "/api/v1/workspace/bulk": {
        "action": "contacts.add_tag",
        "ids": [str(uuid.uuid4())],
        "tag": "d50",
    },
}
WORKSPACE_ACTIONS = ("contacts.add_tag", "contacts.remove_tag", "maintenance.done")

# Documented exception: a POST that persists nothing (it only renders a letter draft from
# the completeness check) and is therefore guarded by ``objektakte:read`` on purpose. A
# reader passes the guard and receives 404 for an unknown property; never 2xx or 500.
READ_EFFECT_ONLY: dict[str, set[int]] = {
    "/api/v1/objektakte/properties/{property_id}/completeness/nachforderungsschreiben": {403, 404}
}


def _fill(path: str, tenant_id: uuid.UUID) -> str:
    """Path parameters get syntactically valid values so that only the guard decides."""

    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "tenant_id":
            return str(tenant_id)
        if name == "provider":
            return "openai"
        return str(uuid.uuid4())

    return re.sub(r"\{([^}]+)\}", value, path)


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def reader_headers(client: TestClient, world: World) -> dict[str, str]:
    return bearer(login(client, world, "reader"))


@pytest.fixture(scope="module")
def admin_headers(client: TestClient, world: World) -> dict[str, str]:
    return bearer(login(client, world, "admin"))


@pytest.fixture(scope="module")
def read_key_headers(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    """API key with every ``*:read`` scope and no write scope at all."""
    created = client.post(
        "/api/v1/tenant/api-keys",
        json={"name": f"d50-read-{uuid.uuid4().hex[:6]}", "scopes": sorted(READ_ALL)},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    return {"X-API-Key": created.json()["key"]}


def _assert_forbidden(response: Any, label: str, path: str = "") -> None:
    allowed = READ_EFFECT_ONLY.get(path, {403})
    assert response.status_code in allowed, f"{label}: {response.status_code} {response.text}"
    body = response.json()
    if response.status_code == 403:
        assert body.get("code") in FORBIDDEN_CODES, f"{label}: {body}"


def test_endpoint_list_is_derived_from_openapi_and_complete() -> None:
    assert OPENAPI.exists()
    paths = {path for _, path in ENDPOINTS}
    # The four /bulk endpoints named in A04 and the money paths of annex D must be present.
    for expected in (
        "/api/v1/banking/bulk-confirm",
        "/api/v1/tickets/bulk-status",
        "/api/v1/workspace/bulk",
        "/api/v1/objektakte/review/bulk-decide",
        "/api/v1/banking/auto-post",
        "/api/v1/accounting/receivable-runs/{run_id}/post",
        "/api/v1/hoa/statements/{statement_id}/post",
        "/api/v1/ai/proposals/{proposal_id}/apply",
    ):
        assert expected in paths, expected
    assert all(method != "GET" for method, _ in ENDPOINTS)


@pytest.mark.parametrize(("method", "path"), ENDPOINTS, ids=[f"{m} {p}" for m, p in ENDPOINTS])
def test_read_only_role_is_rejected(
    client: TestClient, world: World, reader_headers: dict[str, str], method: str, path: str
) -> None:
    body = VALID_BODIES.get(path, {})
    response = client.request(
        method, _fill(path, world.tenant_a), json=body, headers=reader_headers
    )
    _assert_forbidden(response, f"read_only {method} {path}", path)


@pytest.mark.parametrize(("method", "path"), ENDPOINTS, ids=[f"{m} {p}" for m, p in ENDPOINTS])
def test_read_only_api_key_is_rejected(
    client: TestClient, world: World, read_key_headers: dict[str, str], method: str, path: str
) -> None:
    body = VALID_BODIES.get(path, {})
    response = client.request(
        method, _fill(path, world.tenant_a), json=body, headers=read_key_headers
    )
    _assert_forbidden(response, f"api-key {method} {path}", path)


@pytest.mark.parametrize(("method", "path"), ENDPOINTS, ids=[f"{m} {p}" for m, p in ENDPOINTS])
def test_unauthenticated_is_rejected(
    client: TestClient, world: World, method: str, path: str
) -> None:
    response = client.request(method, _fill(path, world.tenant_a), json={})
    assert response.status_code == 401, f"{method} {path}: {response.status_code}"


@pytest.mark.parametrize("action", WORKSPACE_ACTIONS)
def test_workspace_bulk_checks_permission_per_action(
    client: TestClient,
    reader_headers: dict[str, str],
    read_key_headers: dict[str, str],
    action: str,
) -> None:
    """``/workspace/bulk`` guards inside the handler per action (contacts:update or
    properties:update); every action is refused for the reader and for the read key."""
    body = {"action": action, "ids": [str(uuid.uuid4())], "tag": "d50"}
    for label, headers in (("reader", reader_headers), ("api-key", read_key_headers)):
        response = client.post("/api/v1/workspace/bulk", json=body, headers=headers)
        _assert_forbidden(response, f"{label} workspace.bulk {action}")


def test_guard_is_the_only_difference_positive_control(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The same calls pass the permission guard for a tenant administrator: the 403 above is
    caused by the missing right, not by the synthetic payload (which fails later with 4xx)."""
    for method, path in (
        ("POST", "/api/v1/banking/bulk-confirm"),
        ("POST", "/api/v1/tickets/bulk-status"),
        ("POST", "/api/v1/workspace/bulk"),
        ("POST", "/api/v1/objektakte/review/bulk-decide"),
    ):
        response = client.request(method, path, json={}, headers=admin_headers)
        assert response.status_code == 422, f"{method} {path}: {response.status_code}"


# Release gates on mass endpoints and jobs ---------------------------------------------------


def test_gates_close_mass_endpoints_even_for_administrators(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    batch = client.post(
        "/api/v1/banking/payment-batches",
        json={"order_ids": [str(uuid.uuid4())]},
        headers=admin_headers,
    )
    assert batch.status_code == 403, batch.text
    assert batch.json()["code"] == "MHVP-GATE-0001"
    assert batch.json()["gate"] == "G2"

    posting = client.post(f"/api/v1/hoa/statements/{uuid.uuid4()}/post", headers=admin_headers)
    assert posting.status_code == 403, posting.text
    assert posting.json()["code"] == "MHVP-GATE-0001"
    assert posting.json()["gate"] == "G4"


def test_gates_close_mass_endpoints_for_read_only_before_anything_else(
    client: TestClient, reader_headers: dict[str, str]
) -> None:
    """A reader is refused by the permission guard; the gate is not even consulted."""
    batch = client.post(
        "/api/v1/banking/payment-batches",
        json={"order_ids": [str(uuid.uuid4())]},
        headers=reader_headers,
    )
    _assert_forbidden(batch, "reader payment-batches")


def test_persistent_gate_resolver_is_closed_for_every_gate(
    client: TestClient, world: World
) -> None:
    import asyncio

    from mhvp.platform.gates import DbReleaseGateResolver

    resolver = DbReleaseGateResolver(client.app.state.resources.session_factory)  # type: ignore[attr-defined]

    async def all_closed() -> list[bool]:
        return [await resolver.is_open(world.tenant_a, gate) for gate in ReleaseGate]

    assert asyncio.run(all_closed()) == [False] * len(ReleaseGate)


def test_job_guard_fails_closed_by_default(world: World) -> None:
    """Jobs (Celery, imports, bulk) are guarded by ``release_gated``; the default resolver
    keeps every gate closed and a missing tenant is closed too."""
    assert type(job_release_gate_resolver).__name__ == "ClosedReleaseGateResolver"
    calls: list[uuid.UUID | None] = []

    @release_gated(ReleaseGate.G1)
    def job(*, tenant_id: uuid.UUID | str | None) -> str:
        calls.append(uuid.UUID(str(tenant_id)) if tenant_id else None)
        return "posted"

    with pytest.raises(ReleaseGateClosedError):
        job(tenant_id=world.tenant_a)
    with pytest.raises(ReleaseGateClosedError):
        job(tenant_id=str(world.tenant_a))
    with pytest.raises(ReleaseGateClosedError):
        job(tenant_id=None)
    assert calls == []


def test_celery_jobs_carry_no_principal() -> None:
    """Every registered job runs system side: none accepts permissions or roles. The
    authorization of a job is therefore the guarded endpoint that enqueues it (the
    ``.../runs`` endpoints above), and the money locks are the gates, not the caller."""
    import inspect

    from celery import Celery, current_app

    from mhvp.worker import create_celery
    from tests.conftest import make_settings

    # A new Celery instance registers itself as the current app; restore the previous one so
    # later tests keep enqueueing against the app of their own TestClient.
    previous: Celery = current_app._get_current_object()  # type: ignore[attr-defined]
    app = create_celery(make_settings())
    try:
        app.loader.import_default_modules()
        names = sorted(n for n in app.tasks if n.startswith("mhvp."))
        assert len(names) >= 20, names
        for name in names:
            params = set(inspect.signature(app.tasks[name].run).parameters)
            assert not params & {"principal", "permissions", "roles"}, name
    finally:
        previous.set_current()
