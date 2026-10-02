"""AJ24 (GAI-303 Rest): tenant separation and permission checks on write routes with a path
parameter in properties, contacts, tickets, objektakte, workspace and tenant administration.

Table driven: every object is created in tenant A. The administrator of tenant B must
receive 404 (never 403 or 2xx, the object does not exist for him), the read only user of
tenant A must receive 403. Afterwards the objects are unchanged for tenant A.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.aj24_authz_world import (
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


def _objects(c: TestClient, h: dict[str, str], world: AuthzWorld) -> dict[str, str]:
    prop = ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": "924",
                "name": f"Objekt {RUN}",
                "management_type": "hoa",
                "street": "Rheinpromenade",
                "house_number": "24",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    sub = ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/sub-communities",
            json={"code": "H1", "name": "Haus 1"},
            headers=h,
        )
    )
    ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Mia",
                "last_name": f"Test{RUN}",
                "tags": ["aj24tag"],
            },
            headers=h,
        )
    )
    tags = ok(c.get("/api/v1/contact-tags", headers=h), 200)
    tag = next(t for t in tags if t["name"] == "aj24tag")
    entry = ok(
        c.post(
            "/api/v1/catalogs/contact_group",
            json={"code": "aj24_gruppe", "label": "AJ24"},
            headers=h,
        )
    )
    field = ok(
        c.post(
            "/api/v1/custom-fields",
            json={
                "entity_type": "contact",
                "key": "aj24_feld",
                "label": "AJ24 Feld",
                "field_type": "text",
            },
            headers=h,
        )
    )
    ticket = ok(c.post("/api/v1/tickets", json={"title": f"Ticket {RUN}"}, headers=h))
    comment = ok(
        c.post(f"/api/v1/tickets/{ticket['id']}/comments", json={"body": "intern"}, headers=h)
    )
    rule = ok(
        c.post(
            "/api/v1/objektakte/classification-rules",
            json={"name": "AJ24", "pattern_type": "text_keyword", "pattern_value": "aj24"},
            headers=h,
        )
    )
    flt = ok(
        c.put(
            "/api/v1/workspace/filters",
            json={"resource": "contacts", "name": "AJ24", "params": {}},
            headers=h,
        ),
        200,
    )
    members = ok(c.get("/api/v1/tenant/members", headers=h), 200)
    items = members["items"] if isinstance(members, dict) else members
    reader = next(m for m in items if m.get("email") == world.email("aj24rd"))
    membership = reader.get("membership_id") or reader["id"]
    roles = ok(c.get("/api/v1/tenant/roles", headers=h), 200)
    role_items = roles["items"] if isinstance(roles, dict) else roles
    role = next(r for r in role_items if r["code"] == "read_only")
    return {
        "property": prop["id"],
        "sub": sub["id"],
        "tag": tag["id"],
        "entry": entry["id"],
        "field": field["id"],
        "ticket": ticket["id"],
        "comment": comment["id"],
        "rule": rule["id"],
        "filter": flt["id"],
        "membership": str(membership),
        "role": role["id"],
    }


# (method, path template, body); every route requires a write permission.
CASES: list[tuple[str, str, Any]] = [
    ("PUT", "/api/v1/properties/{property}/sub-communities/{sub}", {"code": "H1", "name": "x"}),
    ("DELETE", "/api/v1/properties/{property}/sub-communities/{sub}", None),
    ("PATCH", "/api/v1/contact-tags/{tag}", {"name": "fremd"}),
    ("DELETE", "/api/v1/contact-tags/{tag}", None),
    (
        "POST",
        "/api/v1/contact-tags/{tag}/merge",
        {"target_id": "00000000-0000-0000-0000-00000000aa24"},
    ),
    ("PATCH", "/api/v1/catalogs/contact_group/{entry}", {"label": "fremd"}),
    ("DELETE", "/api/v1/catalogs/contact_group/{entry}", None),
    ("PATCH", "/api/v1/custom-fields/{field}", {"label": "fremd"}),
    ("DELETE", "/api/v1/custom-fields/{field}", None),
    ("DELETE", "/api/v1/tickets/{ticket}/comments/{comment}", None),
    ("PATCH", "/api/v1/objektakte/classification-rules/{rule}", {"name": "fremd"}),
    ("DELETE", "/api/v1/objektakte/classification-rules/{rule}", None),
    ("PATCH", "/api/v1/tenant/members/{membership}", {"status": "disabled"}),
    ("PUT", "/api/v1/tenant/members/{membership}/roles", {"role_codes": ["tenant_admin"]}),
    (
        "POST",
        "/api/v1/tenant/members/{membership}/reset-password",
        {"password": "Fremd-Passwort-2026!x"},
    ),
    ("PUT", "/api/v1/tenant/roles/{role}/permissions", {"permissions": []}),
]

# Personal resources: the read only user is a member, the owner check yields 404.
FOREIGN_ONLY: list[tuple[str, str, Any]] = [
    ("DELETE", "/api/v1/workspace/filters/{filter}", None),
]


def _fill(body: Any, objects: dict[str, str]) -> Any:
    if isinstance(body, dict):
        return {k: (v.format(**objects) if isinstance(v, str) else v) for k, v in body.items()}
    return body


@pytest.fixture(scope="module")
def objects(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    return _objects(client, headers(client, world, "aj24adm"), world)


@pytest.mark.parametrize(("method", "template", "body"), CASES + FOREIGN_ONLY)
def test_foreign_tenant_gets_404(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "aj24oth")
    response = call(client, method, template.format(**objects), h, _fill(body, objects))
    assert response.status_code == 404, response.text
    assert "code" in response.json()


@pytest.mark.parametrize(("method", "template", "body"), CASES)
def test_read_only_user_gets_403(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "aj24rd")
    response = call(client, method, template.format(**objects), h, _fill(body, objects))
    assert response.status_code == 403, response.text


def test_objects_unchanged_for_owner_tenant(
    client: TestClient, world: AuthzWorld, objects: dict[str, str]
) -> None:
    # Runs after the parametrised denials (file order): nothing was changed or deleted.
    h = headers(client, world, "aj24adm")
    subs = ok(
        client.get(f"/api/v1/properties/{objects['property']}/sub-communities", headers=h), 200
    )
    assert [(x["id"], x["name"]) for x in subs] == [(objects["sub"], "Haus 1")]
    tags = ok(client.get("/api/v1/contact-tags", headers=h), 200)
    assert [t["name"] for t in tags if t["id"] == objects["tag"]] == ["aj24tag"]
    comments = ok(client.get(f"/api/v1/tickets/{objects['ticket']}/comments", headers=h), 200)
    assert [x["id"] for x in comments] == [objects["comment"]]
    rules = ok(client.get("/api/v1/objektakte/classification-rules", headers=h), 200)
    rule_items = rules["items"] if isinstance(rules, dict) else rules
    assert [r["name"] for r in rule_items if r["id"] == objects["rule"]] == ["AJ24"]
    filters = ok(client.get("/api/v1/workspace/filters?resource=contacts", headers=h), 200)
    assert [f["id"] for f in filters] == [objects["filter"]]
    # The reader is still read only: the denied role change did not apply.
    rd = headers(client, world, "aj24rd")
    assert client.post("/api/v1/tickets", json={"title": "x"}, headers=rd).status_code == 403
