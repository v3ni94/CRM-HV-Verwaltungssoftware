"""AJ23 (GAI-303): permission and tenant checks on hoa and letting write routes that the
GAI-3 lists name without a tenant separation test or without a 403 test.

Table driven with unknown ids: the read only user must receive 403 before any lookup or
body validation, the administrator of another tenant must never receive a success status
for an id he does not own (404 where the route looks the id up first, otherwise 4xx).
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.aj23_authz_world import AuthzWorld, build_world, call, headers, settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration

X = str(uuid.UUID(int=0x0AA23))
Y = str(uuid.UUID(int=0x0BB23))

# (method, path, body); body {} is enough, the permission check precedes validation.
CASES: list[tuple[str, str, Any]] = [
    ("PUT", "/api/v1/hoa/acquisition-rules/purchase", {}),
    ("PATCH", f"/api/v1/hoa/agenda/{X}", {}),
    ("POST", f"/api/v1/hoa/audit-engagements/{X}/notes/{Y}/answer", {}),
    ("PATCH", f"/api/v1/hoa/audit-items/{X}", {}),
    ("POST", f"/api/v1/hoa/audit-reports/{X}/board-statement", {}),
    ("POST", f"/api/v1/hoa/audits/{X}/reports/1/confirm", {}),
    ("PUT", f"/api/v1/hoa/majority-rules/subject-rules/{X}", {}),
    ("DELETE", f"/api/v1/hoa/majority-rules/subject-rules/{X}", None),
    ("PATCH", f"/api/v1/hoa/measures/{X}", {}),
    ("PUT", f"/api/v1/hoa/meetings/{X}/dial-in", {}),
    ("POST", f"/api/v1/hoa/meetings/{X}/disruptions", {}),
    ("POST", f"/api/v1/hoa/special-levies/{X}/amend", {}),
    ("POST", f"/api/v1/hoa/special-levies/{X}/resolve", {}),
    ("POST", f"/api/v1/hoa/statements/{X}/costs/from-ledger", {}),
    ("PUT", f"/api/v1/hoa/statements/{X}/reconciliation-notes", {}),
    ("POST", "/api/v1/hoa/inspection-requests/ownership-transfers/scan", {}),
    ("PUT", "/api/v1/hoa/portal-circular-settings", {}),
    ("PUT", "/api/v1/hoa/allocation-proposal-settings", {}),
    ("POST", "/api/v1/hoa/insurance-claims", {}),
    ("PATCH", f"/api/v1/hoa/insurance-claims/{X}", {}),
    ("POST", "/api/v1/hoa/reserve-statements", {}),
    ("POST", "/api/v1/hoa/special-levies", {}),
    ("PUT", "/api/v1/letting/broker/is24/config", {}),
    ("POST", "/api/v1/letting/listings", {}),
    ("PATCH", f"/api/v1/letting/listings/{X}", {}),
    ("DELETE", f"/api/v1/letting/listings/{X}", None),
    ("POST", f"/api/v1/letting/listings/{X}/broker/is24/sync", {}),
    ("POST", f"/api/v1/letting/listings/{X}/images", {}),
    ("POST", f"/api/v1/letting/listings/{X}/images/link", {}),
    ("DELETE", f"/api/v1/letting/listings/{X}/images/{Y}", None),
    ("PATCH", f"/api/v1/letting/prospects/viewings/{X}", {}),
    ("PATCH", f"/api/v1/letting/prospects/{X}", {}),
    ("DELETE", f"/api/v1/letting/prospects/{X}", None),
    ("POST", f"/api/v1/letting/prospects/{X}/self-disclosure-link", {}),
    ("POST", f"/api/v1/letting/prospects/{X}/viewings", {}),
    ("POST", f"/api/v1/letting/rent-increases/{X}/actions", {}),
    ("POST", f"/api/v1/letting/rent-increases/{X}/adopt-rent-index", {}),
    ("PUT", f"/api/v1/letting/rent-increases/{X}/ai-check", {}),
    ("POST", f"/api/v1/letting/rent-increases/{X}/letter/pdf", {}),
    ("POST", f"/api/v1/letting/units/{X}/expose/pdf", {}),
    ("PUT", f"/api/v1/letting/vacancies/{X}", {}),
    ("POST", f"/api/v1/letting/vacancies/{X}/listing", {}),
]

# Path parameter routes: the foreign administrator must never see a success status.
FOREIGN = [c for c in CASES if X in c[1]]


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> AuthzWorld:
    return build_world(database, redis_url)


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(settings(database, redis_url))) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def reader(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return headers(client, world, "aj23rd")


@pytest.fixture(scope="module")
def other(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return headers(client, world, "aj23oth")


@pytest.mark.parametrize(("method", "path", "body"), CASES)
def test_read_only_user_gets_403(
    client: TestClient, reader: dict[str, str], method: str, path: str, body: Any
) -> None:
    response = call(client, method, path, reader, body)
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(("method", "path", "body"), FOREIGN)
def test_unknown_id_of_foreign_admin_never_succeeds(
    client: TestClient, other: dict[str, str], method: str, path: str, body: Any
) -> None:
    response = call(client, method, path, other, body)
    assert response.status_code in (404, 409, 422), response.text


def test_anonymous_gets_401(client: TestClient) -> None:
    for method, path, body in CASES:
        response = call(client, method, path, {}, body)
        assert response.status_code == 401, (method, path, response.status_code)
