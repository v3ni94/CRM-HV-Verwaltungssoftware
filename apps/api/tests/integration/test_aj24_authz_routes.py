"""AJ24 (GAI-303 Rest): permission and tenant checks on write routes of communication,
platform, tickets, objektakte, metering, workspace, properties and contacts that are listed
in GAI-3 without a tenant separation or 403 test.

Table driven with unknown ids: the read only user must receive 403 before any lookup or
body validation (the permission dependency runs first), anonymous callers 401, and the
administrator of another tenant must receive 404 for ids he does not own.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.aj24_authz_world import AuthzWorld, build_world, call, headers, settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration

X = str(uuid.UUID(int=0x0AA24))
Y = str(uuid.UUID(int=0x0BB24))

# (method, path, body); body {} is enough, the permission check precedes validation.
CASES: list[tuple[str, str, Any]] = [
    # communication
    ("PATCH", f"/api/v1/communication/calls/{X}", {}),
    ("POST", f"/api/v1/communication/calls/{X}/assign", {}),
    ("POST", f"/api/v1/communication/calls/{X}/proposal/dismiss", {}),
    ("POST", f"/api/v1/dispatches/{X}/evidence", {}),
    ("PATCH", f"/api/v1/mail/inbound/sources/{X}", {}),
    ("DELETE", f"/api/v1/mail/mailboxes/{X}", None),
    ("POST", f"/api/v1/mail/mailboxes/{X}/reconcile-state", {}),
    ("POST", f"/api/v1/mail/messages/{X}/forward-invoice", {}),
    ("POST", f"/api/v1/mail/messages/{X}/reply-ai", {}),
    ("POST", f"/api/v1/mail/messages/{X}/restore-inbox", {}),
    ("POST", f"/api/v1/mail/messages/{X}/attachments/{Y}/invoice-extraction", {}),
    ("PATCH", f"/api/v1/mail/playbooks/{X}", {}),
    ("DELETE", f"/api/v1/mail/playbooks/{X}", None),
    ("POST", f"/api/v1/postal/jobs/{X}/manual", {}),
    # contacts
    ("PUT", "/api/v1/consent-legal-basis/email_delivery", {}),
    ("DELETE", "/api/v1/consent-legal-basis/email_delivery", None),
    ("POST", "/api/v1/contacts/roles/recompute", {}),
    # metering
    ("POST", f"/api/v1/metering/assignments/{X}/change-provider", {}),
    ("POST", f"/api/v1/metering/clearing-items/{X}/resolve", {}),
    ("PUT", f"/api/v1/metering/connections/{X}/secrets", {}),
    ("POST", f"/api/v1/metering/transmissions/{X}/order", {}),
    ("POST", f"/api/v1/metering/transmissions/{X}/poll", {}),
    ("PATCH", f"/api/v1/metering/unit-assignments/{X}", {}),
    # objektakte
    ("POST", f"/api/v1/objektakte/properties/{X}/lists/missing-documents/store", {}),
    ("POST", f"/api/v1/objektakte/review/{X}/ask-ai", {}),
    ("POST", "/api/v1/integrations/objektakte/objects/924/person-proposals", {}),
    ("POST", "/api/v1/integrations/objektakte/objects/924/persons-export", {}),
    # platform (operator routes and tenant administration)
    ("PATCH", f"/api/v1/platform/licenses/{X}", {}),
    ("POST", f"/api/v1/platform/licenses/{X}/end", {}),
    ("PATCH", f"/api/v1/platform/maintenance-windows/{X}", {}),
    ("POST", f"/api/v1/platform/oidc-clients/{X}/deactivate", {}),
    ("DELETE", f"/api/v1/platform/ops/metrics-keys/{X}", None),
    ("PATCH", f"/api/v1/platform/price-list/{X}", {}),
    ("DELETE", f"/api/v1/platform/price-list/{X}", None),
    ("PATCH", f"/api/v1/platform/pricing/items/{X}", {}),
    ("PUT", f"/api/v1/platform/tenants/{X}/demo", {}),
    ("POST", f"/api/v1/platform/tenants/{X}/export-requests/{Y}/run", {}),
    ("POST", f"/api/v1/platform/tenants/{X}/members", {}),
    ("POST", f"/api/v1/platform/tenants/{X}/usage", {}),
    ("DELETE", f"/api/v1/tenant/api-keys/{X}", None),
    ("PUT", f"/api/v1/tenant/members/{X}/competences", {}),
    ("PUT", f"/api/v1/tenant/members/{X}/mobile-phone", {}),
    ("PUT", f"/api/v1/tenant/members/{X}/position", {}),
    ("POST", f"/api/v1/tenant/webhook-deliveries/{X}/redeliver", {}),
    ("POST", f"/api/v1/tenant/webhooks/{X}/test", {}),
    # properties
    ("PATCH", f"/api/v1/properties/{X}/contacts/{Y}", {}),
    ("POST", f"/api/v1/properties/{X}/owner", {}),
    ("POST", f"/api/v1/properties/{X}/portal-documents", {}),
    ("DELETE", f"/api/v1/properties/{X}/portal-documents/{Y}", None),
    ("POST", f"/api/v1/properties/{X}/reactivate", {}),
    ("PATCH", f"/api/v1/properties/{X}/takeover-checklist/legal", {}),
    ("POST", f"/api/v1/units/{X}/vat-options", {}),
    ("POST", "/api/v1/catalogs/contact_group", {}),
    # tickets
    ("POST", f"/api/v1/tickets/{X}/apply-process", {}),
    ("POST", f"/api/v1/tickets/{X}/assignees", {}),
    ("DELETE", f"/api/v1/tickets/{X}/assignees/{Y}", None),
    ("POST", f"/api/v1/tickets/{X}/attach-invoice", {}),
    ("PATCH", f"/api/v1/tickets/{X}/checklist/k", {}),
    ("POST", f"/api/v1/tickets/{X}/proposals/{Y}/accept-and-reply", {}),
    ("POST", f"/api/v1/tickets/{X}/proposals/{Y}/correct", {}),
    ("PATCH", f"/api/v1/work-orders/{X}/approval-workflow", {}),
    # workspace
    ("POST", f"/api/v1/workspace/checklists/{X}/items/k", {}),
]

# Routes that load the id first: unknown ids answer 404 to an administrator.
NOT_FOUND: list[tuple[str, str, Any]] = [
    ("DELETE", f"/api/v1/mail/playbooks/{X}", None),
    ("DELETE", f"/api/v1/mail/mailboxes/{X}", None),
    ("DELETE", f"/api/v1/tenant/api-keys/{X}", None),
    ("DELETE", f"/api/v1/tickets/{X}/assignees/{Y}", None),
    ("DELETE", f"/api/v1/properties/{X}/portal-documents/{Y}", None),
    ("DELETE", f"/api/v1/workspace/filters/{X}", None),
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
    return headers(client, world, "aj24rd")


@pytest.fixture(scope="module")
def other(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return headers(client, world, "aj24oth")


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


def test_draft_letter_is_read_only_and_tenant_bound(
    client: TestClient, reader: dict[str, str], other: dict[str, str]
) -> None:
    # The Nachforderungsschreiben draft only returns text (objektakte:read, nothing is
    # stored): the reader may call it, an unknown or foreign property answers 404.
    path = f"/api/v1/objektakte/properties/{X}/completeness/nachforderungsschreiben"
    assert call(client, "POST", path, reader, {}).status_code == 404
    assert call(client, "POST", path, other, {}).status_code == 404


def test_reactivate_is_reserved_to_superadmin(client: TestClient, other: dict[str, str]) -> None:
    response = call(client, "POST", f"/api/v1/properties/{X}/reactivate", other, {})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "MHVP-PROP-0003"
