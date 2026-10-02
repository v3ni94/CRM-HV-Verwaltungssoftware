"""AJ23 (GAI-303): tenant separation and permission checks on hoa and letting write routes
with a path parameter, against real objects of tenant A.

The administrator of tenant B must receive 404 (the object does not exist for him), the
read only user of tenant A must receive 403. Afterwards the objects are unchanged.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.aj23_authz_world import (
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

RULE = {
    "subject_kind": "other",
    "majority_type": "simple",
    "counting_basis": "heads",
    "source": "Testannahme AJ23",
}


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
                "number": "923",
                "name": f"Objekt {RUN}",
                "management_type": "rental",
                "street": "Rheinpromenade",
                "house_number": "23",
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
            json={"kind": "person", "first_name": "Lea", "last_name": f"Test{RUN}"},
            headers=h,
        )
    )
    listing = ok(
        c.post(
            "/api/v1/letting/listings",
            json={"unit_id": unit["id"], "kind": "rental", "title": "Entwurf"},
            headers=h,
        )
    )
    prospect = ok(
        c.post(
            "/api/v1/letting/prospects",
            json={
                "unit_id": unit["id"],
                "contact_id": contact["id"],
                "delete_after": (datetime.now(UTC).date() + timedelta(days=180)).isoformat(),
                "notes": "Entwurf",
            },
            headers=h,
        )
    )
    viewing = ok(
        c.post(
            f"/api/v1/letting/prospects/{prospect['id']}/viewings",
            json={"scheduled_at": "2026-11-03T10:00:00+00:00", "note": "Entwurf"},
            headers=h,
        )
    )
    rule = ok(c.post("/api/v1/hoa/majority-rules/subject-rules", json=RULE, headers=h))
    return {
        "unit": unit["id"],
        "listing": listing["id"],
        "prospect": prospect["id"],
        "viewing": viewing["id"],
        "rule": rule["id"],
    }


# (method, path template, body); valid bodies, so only the lookup can refuse.
CASES: list[tuple[str, str, Any]] = [
    ("PATCH", "/api/v1/letting/listings/{listing}", {"title": "fremd"}),
    ("DELETE", "/api/v1/letting/listings/{listing}", None),
    ("PATCH", "/api/v1/letting/prospects/{prospect}", {"notes": "fremd"}),
    ("DELETE", "/api/v1/letting/prospects/{prospect}", None),
    (
        "POST",
        "/api/v1/letting/prospects/{prospect}/viewings",
        {"scheduled_at": "2026-11-04T10:00:00+00:00"},
    ),
    ("PATCH", "/api/v1/letting/prospects/viewings/{viewing}", {"note": "fremd"}),
    ("PUT", "/api/v1/hoa/majority-rules/subject-rules/{rule}", {**RULE, "source": "fremd"}),
    ("DELETE", "/api/v1/hoa/majority-rules/subject-rules/{rule}", None),
]

# Read routes of the same objects: foreign tenant 404.
READS = [
    "/api/v1/letting/listings/{listing}/images",
    "/api/v1/letting/listings/{listing}/prospect-matches",
    "/api/v1/letting/prospects/{prospect}/viewings",
    "/api/v1/letting/prospects/{prospect}/self-disclosure-links",
]


@pytest.fixture(scope="module")
def objects(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return _objects(client, headers(client, world, "aj23adm"))


@pytest.mark.parametrize(("method", "template", "body"), CASES)
def test_foreign_tenant_gets_404(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "aj23oth")
    response = call(client, method, template.format(**objects), h, body)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("template", READS)
def test_foreign_tenant_read_gets_404(
    client: TestClient, world: AuthzWorld, objects: dict[str, str], template: str
) -> None:
    h = headers(client, world, "aj23oth")
    response = client.get(template.format(**objects), headers=h)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize(("method", "template", "body"), CASES)
def test_read_only_user_gets_403(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "aj23rd")
    response = call(client, method, template.format(**objects), h, body)
    assert response.status_code == 403, response.text


def test_objects_unchanged_for_owner_tenant(
    client: TestClient, world: AuthzWorld, objects: dict[str, str]
) -> None:
    # Runs after the parametrised denials (file order): nothing was changed or deleted.
    h = headers(client, world, "aj23adm")
    listing = ok(client.get(f"/api/v1/letting/listings/{objects['listing']}", headers=h), 200)
    assert listing["title"] == "Entwurf"
    prospects = ok(
        client.get(f"/api/v1/letting/prospects?unit_id={objects['unit']}", headers=h), 200
    )
    assert [p["notes"] for p in prospects if p["id"] == objects["prospect"]] == ["Entwurf"]
    viewings = ok(
        client.get(f"/api/v1/letting/prospects/{objects['prospect']}/viewings", headers=h), 200
    )
    assert [v["note"] for v in viewings] == ["Entwurf"]
    rules = ok(client.get("/api/v1/hoa/majority-rules/subject-rules", headers=h), 200)
    assert [r["source"] for r in rules if r["id"] == objects["rule"]] == ["Testannahme AJ23"]
