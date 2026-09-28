"""Data quality report and entry standards (rules ES-01 to ES-11): hard postcode check on the
property endpoints (create, PUT, PATCH), advisory check endpoint, report sections with
expected entries, authorization, tenant separation and no automatic change of data."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
P = "/api/v1/properties"
R = "/api/v1/data-quality/report"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dq-a-{RUN}", name=f"DQ A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"dq-b-{RUN}", name=f"DQ B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("dqadmin", a, "tenant_admin"),
            ("dqcare", a, "caretaker"),
            ("dqother", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(c: TestClient, h: dict[str, str], number: str, **extra: Any) -> Any:
    body = {"number": number, "name": f"Objekt {number}", "management_type": "rental", **extra}
    return c.post(P, json=body, headers=h)


def _section(report: dict[str, Any], key: str) -> dict[str, Any]:
    return next(s for s in report["sections"] if s["key"] == key)


def test_postcode_is_validated_on_the_api(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "dqadmin", world.tenant_a))
    bad = _property(client, h, "801", postal_code="4078")
    assert bad.status_code == 422, bad.text
    assert bad.json()["errors"][0]["field"] == "postal_code"
    # Other countries are not checked against the German five digit format.
    _ok(_property(client, h, "802", postal_code="1010", country="AT"), 201)
    prop = _ok(_property(client, h, "803", postal_code="40789", city="Monheim am Rhein"), 201)
    patch_h = {**h, "If-Match": f'"{prop["version"]}"'}
    rejected = client.patch(f"{P}/{prop['id']}", json={"postal_code": "123"}, headers=patch_h)
    assert rejected.status_code == 422, rejected.text
    # Changing another field of the record is not blocked by the postcode rule.
    _ok(client.patch(f"{P}/{prop['id']}", json={"notes": "x"}, headers=patch_h))


def test_report_lists_violations_without_changing_data(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "dqadmin", world.tenant_a))
    prop = _ok(_property(client, h, "811", street="Rheinpromenade 13"), 201)
    clean = _ok(
        _property(
            client,
            h,
            "812",
            name="Rheinpromenade 13, 40789 Monheim am Rhein",
            street="Rheinpromenade",
            house_number="13",
            postal_code="40789",
            city="Monheim am Rhein",
        ),
        201,
    )
    swapped = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "last_name": f"Anna Schmidt{RUN}", "roles": ["mieter"]},
            headers=h,
        ),
        201,
    )
    fine = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Bernd",
                "last_name": f"Muster{RUN}",
                "roles": ["eigentuemer"],
                "emails": [{"email": f"bernd-{RUN}@example.org", "label": "privat"}],
            },
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Frist ohne Zuständigen", "due_on": "2030-01-31"},
            headers=h,
        ),
        201,
    )

    report = _ok(client.get(R, headers=h))
    assert report["sections_omitted"] == []
    props = {i["entity_id"]: i for i in _section(report, "properties")["items"]}
    assert clean["id"] not in props
    assert {f["rule"] for f in props[prop["id"]]["findings"]} == {"ES-02", "ES-03", "ES-04"}
    contacts = {i["entity_id"]: i for i in _section(report, "contacts")["items"]}
    assert [f["rule"] for f in contacts[swapped["id"]]["findings"]] == ["ES-06"]
    assert fine["id"] not in contacts
    mails = {i["entity_id"] for i in _section(report, "contact_emails")["items"]}
    assert swapped["id"] in mails
    assert fine["id"] not in mails
    deadlines = {i["entity_id"]: i for i in _section(report, "deadlines")["items"]}
    assert ticket["assignee_user_id"] is None
    assert [f["rule"] for f in deadlines[ticket["id"]]["findings"]] == ["ES-10"]

    # Read only: the swapped contact keeps its stored values.
    stored = _ok(client.get(f"/api/v1/contacts/{swapped['id']}", headers=h))
    assert stored["last_name"] == f"Anna Schmidt{RUN}"
    assert stored["first_name"] in (None, "")

    # Tenant separation: tenant B sees none of tenant A's records.
    hb = bearer(login(client, world, "dqother", world.tenant_b))
    other = _ok(client.get(R, headers=hb))
    ids = {i["entity_id"] for s in other["sections"] for i in s["items"]}
    assert not ids & {prop["id"], swapped["id"], ticket["id"]}


def test_report_and_check_authorization(client: TestClient, world: World) -> None:
    assert client.get(R).status_code == 401
    care = bearer(login(client, world, "dqcare", world.tenant_a))
    assert client.get(R, headers=care).status_code == 403
    assert (
        client.post(
            "/api/v1/data-quality/check", json={"entity": "property", "data": {}}, headers=care
        ).status_code
        == 403
    )


def test_check_endpoint(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "dqadmin", world.tenant_a))
    url = "/api/v1/data-quality/check"
    out = _ok(
        client.post(
            url,
            json={"entity": "contact", "data": {"kind": "person", "last_name": "Schmidt, Anna"}},
            headers=h,
        )
    )
    assert [f["rule"] for f in out["findings"]] == ["ES-05"]
    out = _ok(
        client.post(url, json={"entity": "deadline", "data": {"due_on": "2000-01-01"}}, headers=h)
    )
    assert [f["rule"] for f in out["findings"]] == ["ES-09", "ES-10"]
    bad = client.post(url, json={"entity": "deadline", "data": {"due_on": "01.01.2000"}}, headers=h)
    assert bad.status_code == 422
