"""AJ06 (GAI-303): tenant separation and permission checks on write routes with a path
parameter in contracts, documents and portal administration.

Table driven: every object is created in tenant A. The administrator of tenant B must
receive 404 (never 403 or 2xx, the object does not exist for him), the read only user of
tenant A must receive 403. Afterwards the objects are unchanged for tenant A.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.aj06_authz_world import (
    RUN,
    AuthzWorld,
    build_world,
    call,
    headers,
    ok,
    settings,
)
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> AuthzWorld:
    return build_world(database, redis_url)


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(settings(database, redis_url))) as test_client:
        yield test_client


def _objects(c: TestClient, h: dict[str, str]) -> dict[str, str]:
    prop = ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": "906",
                "name": f"Objekt {RUN}",
                "management_type": "rental",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    building = ok(
        c.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h)
    )
    unit = ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building["id"],
                "number": "01",
                "label": "WE 01",
                "unit_type": "apartment",
            },
            headers=h,
        )
    )
    contact = ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Mia", "last_name": f"Test{RUN}"},
            headers=h,
        )
    )
    party = ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h)
    )
    owner_contact = ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Vermieter {RUN} GmbH"},
            headers=h,
        )
    )
    owner = ok(
        c.post(
            "/api/v1/parties", json={"members": [{"contact_id": owner_contact["id"]}]}, headers=h
        )
    )
    ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner["id"], "valid_from": "2020-01-01"},
            headers=h,
        )
    )
    contract = ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit["id"],
                "party_id": party["id"],
                "start_date": "2025-01-01",
            },
            headers=h,
        )
    )
    deposit = ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/deposits",
            json={"kind": "cash", "amount_due": "900.00", "valid_from": "2025-01-01"},
            headers=h,
        )
    )
    ok(
        c.put(
            f"/api/v1/deposits/{deposit['id']}/interest-rates/2025-01-01",
            json={"rate": "0.5"},
            headers=h,
        ),
        200,
    )
    ok(c.put("/api/v1/deposit-interest-rates/2024", json={"rate": "0.25"}, headers=h), 200)
    category = ok(
        c.post(
            "/api/v1/document-categories",
            json={"code": "aj06_kat", "name": f"Kategorie {RUN}"},
            headers=h,
        )
    )
    template = ok(
        c.post(
            "/api/v1/document-templates",
            json={"code": "aj06_vorlage", "name": "Vorlage", "subject": "Betreff", "body": "Text"},
            headers=h,
        )
    )
    block = ok(
        c.post(
            "/api/v1/document-text-blocks",
            json={"code": "info_sheet_inspection", "title": "Entwurf", "body": "Platzhalter"},
            headers=h,
        )
    )
    profile = ok(
        c.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": "aj06_klasse",
                "legal_basis": "R17 Testprofil",
                "retention_years": 6,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )
    availability = ok(
        c.post(
            "/api/v1/portal-admin/provider-availability",
            json={
                "provider_contact_id": contact["id"],
                "starts_at": "2026-11-02T08:00:00+00:00",
                "ends_at": "2026-11-02T12:00:00+00:00",
            },
            headers=h,
        )
    )
    return {
        "contract": contract["id"],
        "deposit": deposit["id"],
        "category": category["id"],
        "template": template["id"],
        "block": block["id"],
        "profile": profile["id"],
        "availability": availability["id"],
    }


# (method, path template, body); every route requires a write permission.
CASES: list[tuple[str, str, Any]] = [
    ("PATCH", "/api/v1/contracts/{contract}/notes", {"notes": "fremd"}),
    ("PATCH", "/api/v1/contracts/{contract}/custom-fields", {"custom_fields": {"k": "v"}}),
    ("PATCH", "/api/v1/deposits/{deposit}", {"valid_to": "2030-12-31"}),
    ("PUT", "/api/v1/deposits/{deposit}/interest-rates/2025-01-01", {"rate": "9"}),
    ("DELETE", "/api/v1/deposits/{deposit}/interest-rates/2025-01-01", None),
    ("DELETE", "/api/v1/deposit-interest-rates/2024", None),
    ("PATCH", "/api/v1/document-categories/{category}", {"name": "fremd"}),
    ("PATCH", "/api/v1/document-templates/{template}", {"context_types": []}),
    ("PATCH", "/api/v1/document-text-blocks/{block}", {"title": "fremd"}),
    ("POST", "/api/v1/document-text-blocks/{block}/retire", None),
    ("PATCH", "/api/v1/retention-profiles/{profile}", {"review_note": "fremd"}),
    ("DELETE", "/api/v1/portal-admin/provider-availability/{availability}", None),
]


@pytest.fixture(scope="module")
def objects(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return _objects(client, headers(client, world, "aj06adm"))


@pytest.mark.parametrize(("method", "template", "body"), CASES)
def test_foreign_tenant_gets_404(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "aj06oth")
    response = call(client, method, template.format(**objects), h, body)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "RESOURCE_NOT_FOUND" or "code" in response.json()


@pytest.mark.parametrize(("method", "template", "body"), CASES)
def test_read_only_user_gets_403(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "aj06rd")
    response = call(client, method, template.format(**objects), h, body)
    assert response.status_code == 403, response.text


def test_objects_unchanged_for_owner_tenant(
    client: TestClient, world: AuthzWorld, objects: dict[str, str]
) -> None:
    # Runs after the parametrised denials (file order): nothing was changed or deleted.
    h = headers(client, world, "aj06adm")
    rates = ok(client.get(f"/api/v1/deposits/{objects['deposit']}/interest-rates", headers=h), 200)
    assert [(r["valid_from"], r["rate"]) for r in rates] == [("2025-01-01", "0.50000")]
    ref = ok(client.get("/api/v1/deposit-interest-rates", headers=h), 200)
    assert [(r["year"], r["rate"]) for r in ref] == [(2024, "0.25000")]
    block = ok(client.get(f"/api/v1/document-text-blocks/{objects['block']}", headers=h), 200)
    assert block["title"] == "Entwurf"
    contract = ok(client.get(f"/api/v1/contracts/{objects['contract']}", headers=h), 200)
    assert contract.get("notes") in (None, "")
    # The owner may delete; the emit of GAI-308 is written in the same transaction.
    assert client.delete("/api/v1/deposit-interest-rates/2024", headers=h).status_code == 204
    assert (
        client.delete(
            f"/api/v1/deposits/{objects['deposit']}/interest-rates/2025-01-01", headers=h
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/portal-admin/provider-availability/{objects['availability']}", headers=h
        ).status_code
        == 204
    )
