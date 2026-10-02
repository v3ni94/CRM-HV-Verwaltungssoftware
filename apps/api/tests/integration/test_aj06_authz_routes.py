"""AJ06 (GAI-303): permission and tenant checks on write routes of billing, portal
administration, contracts and documents that are listed in GAI-3 without a 403 test.

Table driven with unknown ids: the read only user must receive 403 before any lookup or
body validation (the permission dependency runs first), the administrator of another
tenant must never receive a success status for an id he does not own (404, or 409/422 if
the route validates before the lookup, never 2xx).
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.aj06_authz_world import AuthzWorld, build_world, call, headers, settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration

X = str(uuid.UUID(int=0x0AA06))
Y = str(uuid.UUID(int=0x0BB06))

# (method, path, body); body {} is enough, the permission check precedes validation.
CASES: list[tuple[str, str, Any]] = [
    ("PUT", f"/api/v1/billing/heating-cost-imports/{X}", {}),
    ("PUT", f"/api/v1/billing/heating-cost-imports/{X}/rows", {}),
    ("PATCH", f"/api/v1/billing/owner-statements/{X}/options", {"attach_receipts": True}),
    ("POST", f"/api/v1/billing/owner-statements/{X}/outputs", {}),
    ("PUT", f"/api/v1/billing/operating-cost-types/accounts/{X}", {}),
    ("PATCH", f"/api/v1/statements/{X}", {}),
    ("PUT", f"/api/v1/statements/{X}/heating", {}),
    ("POST", f"/api/v1/statements/{X}/heating/import-consumptions", {}),
    ("POST", f"/api/v1/statements/{X}/inspections", {}),
    ("PATCH", f"/api/v1/statements/{X}/inspections/{Y}", {}),
    ("POST", f"/api/v1/statements/{X}/result-entries", {}),
    ("PUT", f"/api/v1/statements/{X}/results/{Y}/delivery", {}),
    ("POST", f"/api/v1/statements/{X}/advance-proposals", {}),
    ("POST", f"/api/v1/statements/{X}/info-sheet", {}),
    ("PUT", f"/api/v1/properties/{X}/consumption-info/{Y}/delivery", {}),
    ("PATCH", f"/api/v1/contracts/{X}/allocation-agreements/{Y}", {}),
    ("DELETE", f"/api/v1/contracts/{X}/allocation-agreements/{Y}", None),
    ("PATCH", f"/api/v1/contracts/{X}/payments/{Y}", {}),
    ("PATCH", f"/api/v1/contracts/{X}/schedules/{Y}", {}),
    ("PUT", "/api/v1/deposit-interest-rates/2023", {"rate": "1"}),
    ("PUT", "/api/v1/document-text-blocks/policy", {}),
    ("POST", f"/api/v1/documents/{X}/mirror", {}),
    ("POST", f"/api/v1/documents/trash/{X}/purge", {"reason": "Test"}),
    ("POST", f"/api/v1/documents/trash/{X}/restore", {"reason": "Test"}),
    ("POST", f"/api/v1/tickets/{X}/retention-hold", {}),
    ("DELETE", f"/api/v1/tickets/{X}/retention-hold", None),
    ("POST", f"/api/v1/portal-admin/accounts/{X}/document-class-grants", {}),
    ("PATCH", f"/api/v1/portal-admin/accounts/{X}/security", {"magic_link_2fa": True}),
    ("POST", f"/api/v1/portal-admin/accounts/{X}/invitation-letter", {}),
    ("POST", "/api/v1/portal-admin/provider-availability", {}),
    ("DELETE", f"/api/v1/portal-admin/provider-availability/{X}", None),
    ("DELETE", f"/api/v1/portal-admin/forms/{X}", None),
]

# Routes that need the id to exist: unknown ids answer 404 to the foreign administrator.
NOT_FOUND = [
    ("PATCH", f"/api/v1/billing/owner-statements/{X}/options", {"attach_receipts": True}),
    ("PATCH", f"/api/v1/portal-admin/accounts/{X}/security", {"magic_link_2fa": True}),
    ("DELETE", f"/api/v1/portal-admin/provider-availability/{X}", None),
    ("DELETE", f"/api/v1/portal-admin/forms/{X}", None),
    ("DELETE", f"/api/v1/contracts/{X}/allocation-agreements/{Y}", None),
    ("POST", f"/api/v1/documents/trash/{X}/restore", {"reason": "Test"}),
]


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> AuthzWorld:
    return build_world(database, redis_url)


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(settings(database, redis_url))) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def reader(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return headers(client, world, "aj06rd")


@pytest.fixture(scope="module")
def other(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return headers(client, world, "aj06oth")


@pytest.mark.parametrize(("method", "path", "body"), CASES)
def test_read_only_user_gets_403(
    client: TestClient, reader: dict[str, str], method: str, path: str, body: Any
) -> None:
    response = call(client, method, path, reader, body)
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(("method", "path", "body"), NOT_FOUND)
def test_unknown_id_of_admin_gets_404(
    client: TestClient, other: dict[str, str], method: str, path: str, body: Any
) -> None:
    response = call(client, method, path, other, body)
    assert response.status_code == 404, response.text


def test_anonymous_gets_401(client: TestClient) -> None:
    for method, path, body in CASES:
        response = call(client, method, path, {}, body)
        assert response.status_code == 401, (method, path, response.status_code)
