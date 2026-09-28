"""Stammdaten in der Oberfläche (package C2, 28.09.2026): contact persons with display name
and partial update, meter partial update (unit link, period, no number), maintenance partial
update and completion with a deterministic next due date, custom field values of a property
via ``PATCH /properties/{id}`` with ``If-Match``. Authorization (403), tenant separation
(404) and validation (422, 409) for the new routes. Rows and expected values are invented and
recomputable by hand."""

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.properties.services import add_months
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration

P = "/api/v1/properties"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"c2a-{RUN}", name=f"C2 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"c2b-{RUN}", name=f"C2 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("c2admin", a, "tenant_admin"),
            ("c2caretaker", a, "caretaker"),
            ("c2other", b, "tenant_admin"),
        ]:
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
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _prop(c: TestClient, h: dict[str, str], number: str, management_type: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"C2 Objekt {number}",
        "management_type": management_type,
        "street": "Musterweg",
        "house_number": number.lstrip("0"),
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    return dict(_ok(c.post(P, json=body, headers=h), 201))


def _unit(c: TestClient, h: dict[str, str], prop: str, number: str) -> Any:
    building = _ok(c.post(f"{P}/{prop}/buildings", json={"name": "Haus A"}, headers=h), 201)
    body = {"building_id": building["id"], "number": number, "unit_type": "apartment"}
    return _ok(c.post(f"{P}/{prop}/units", json=body, headers=h), 201)


def _contact(c: TestClient, h: dict[str, str], name: str) -> Any:
    body = {"kind": "company", "company_name": f"{name} {RUN} GmbH"}
    return _ok(c.post("/api/v1/contacts", json=body, headers=h), 201)


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 3, 31), 12) == date(2027, 3, 31)


def test_contact_persons_with_name_and_patch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "c2admin"))
    prop = _prop(client, h, "931", "rental")
    contact = _contact(client, h, "Hausmeister")
    url = f"{P}/{prop['id']}/contacts"
    body = {
        "contact_id": contact["id"],
        "category_code": "caretaker",
        "valid_from": "2026-01-01",
        "visible_in_portal_for": ["tenant"],
    }
    row = _ok(client.post(url, json=body, headers=h), 201)
    assert row["contact_name"] == contact["display_name"]
    listed = _ok(client.get(url, headers=h))
    assert [r["contact_name"] for r in listed] == [contact["display_name"]]

    patched = _ok(
        client.patch(
            f"{url}/{row['id']}",
            json={"valid_to": "2026-06-30", "visible_in_portal_for": ["owner", "tenant"]},
            headers=h,
        )
    )
    assert patched["valid_to"] == "2026-06-30"
    assert patched["visible_in_portal_for"] == ["owner", "tenant"]
    assert patched["category_code"] == "caretaker"
    # period order and unknown category are refused, the contact itself is immutable
    assert (
        client.patch(f"{url}/{row['id']}", json={"valid_to": "2025-12-31"}, headers=h).status_code
        == 422
    )
    assert (
        client.patch(f"{url}/{row['id']}", json={"category_code": "nope"}, headers=h).status_code
        == 422
    )
    assert (
        client.patch(
            f"{url}/{row['id']}", json={"contact_id": contact["id"]}, headers=h
        ).status_code
        == 422
    )
    # the assignment must belong to the property in the path
    other_prop = _prop(client, h, "932", "rental")
    assert (
        client.patch(
            f"{P}/{other_prop['id']}/contacts/{row['id']}", json={"valid_to": None}, headers=h
        ).status_code
        == 404
    )
    events = _ok(
        client.get(
            f"/api/v1/tenant/audit-log?entity_type=property&entity_id={prop['id']}", headers=h
        )
    )
    assert any("valid_to" in e["changes"] for e in events), events


def test_meter_patch_unit_link_period_and_number_via_change(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "c2admin"))
    prop = _prop(client, h, "933", "hoa")
    unit = _unit(client, h, prop["id"], "01")
    foreign = _unit(client, h, _prop(client, h, "934", "hoa")["id"], "01")
    meter = _ok(
        client.post(
            f"{P}/{prop['id']}/meters",
            json={"meter_type_code": "cold_water", "number": "KW-1", "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    assert meter["property_id"] == prop["id"]
    m = f"/api/v1/meters/{meter['id']}"
    patched = _ok(
        client.patch(
            m,
            json={"unit_id": unit["id"], "location": "Keller links", "valid_to": "2026-12-31"},
            headers=h,
        )
    )
    assert patched["unit_id"] == unit["id"]
    assert patched["location"] == "Keller links"
    assert patched["valid_to"] == "2026-12-31"
    assert patched["number"] == "KW-1"
    assert client.patch(m, json={"unit_id": foreign["id"]}, headers=h).status_code == 422
    assert client.patch(m, json={"valid_to": "2025-01-01"}, headers=h).status_code == 422
    assert client.patch(m, json={"meter_type_code": "unknown"}, headers=h).status_code == 422
    # the number only changes through a recorded replacement
    assert client.patch(m, json={"number": "KW-2"}, headers=h).status_code == 422
    change = _ok(
        client.post(
            f"{m}/changes",
            json={
                "changed_on": "2026-07-01",
                "old_final_value": "1234.5",
                "new_initial_value": "0",
                "new_number": "KW-2",
            },
            headers=h,
        ),
        201,
    )
    assert change["old_number"] == "KW-1"
    listed = _ok(client.get(f"{P}/{prop['id']}/meters", headers=h))
    assert [x["number"] for x in listed] == ["KW-2"]


def test_maintenance_patch_and_done_cycle(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "c2admin"))
    prop = _prop(client, h, "935", "rental")
    provider = _contact(client, h, "Heizungsbau")
    relation = _ok(
        client.post(
            f"{P}/{prop['id']}/service-providers",
            json={
                "contact_id": provider["id"],
                "contract_type_code": "heating_maintenance",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    foreign_relation = _ok(
        client.post(
            f"{P}/{_prop(client, h, '936', 'rental')['id']}/service-providers",
            json={
                "contact_id": provider["id"],
                "contract_type_code": "heating_maintenance",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    item = _ok(
        client.post(
            f"{P}/{prop['id']}/maintenance",
            json={"kind": "maintenance", "title": "Heizungswartung", "due_date": "2026-01-31"},
            headers=h,
        ),
        201,
    )
    assert item["status"] == "open"
    assert item["last_done_on"] is None
    mi = f"/api/v1/maintenance/{item['id']}"
    patched = _ok(
        client.patch(
            mi,
            json={"interval_months": 12, "provider_relation_id": relation["id"]},
            headers=h,
        )
    )
    assert patched["interval_months"] == 12
    assert patched["provider_relation_id"] == relation["id"]
    assert (
        client.patch(
            mi, json={"provider_relation_id": foreign_relation["id"]}, headers=h
        ).status_code
        == 422
    )
    assert client.patch(mi, json={"status": "done"}, headers=h).status_code == 422
    assert client.patch(mi, json={"interval_months": 0}, headers=h).status_code == 422

    # interval: the item stays open, due date 31.01.2026 + 12 months = 31.01.2027
    done = _ok(client.post(f"{mi}/done", json={"done_on": "2026-01-31"}, headers=h))
    assert done["next_due_date"] == "2027-01-31"
    assert done["item"]["status"] == "open"
    assert done["item"]["due_date"] == "2027-01-31"
    assert done["item"]["last_done_on"] == "2026-01-31"
    # month end clamp: 31.01. + 1 month = 28.02.
    _ok(client.patch(mi, json={"interval_months": 1}, headers=h))
    done = _ok(client.post(f"{mi}/done", json={"done_on": "2026-01-31"}, headers=h))
    assert done["next_due_date"] == "2026-02-28"

    # without interval: closed once, a second completion is a conflict (MHVP-PROP-0005)
    once = _ok(
        client.post(
            f"{P}/{prop['id']}/maintenance",
            json={"kind": "inspection", "title": "Blitzschutzprüfung"},
            headers=h,
        ),
        201,
    )
    closed = _ok(
        client.post(
            f"/api/v1/maintenance/{once['id']}/done", json={"done_on": "2026-03-02"}, headers=h
        )
    )
    assert closed["item"]["status"] == "done"
    assert closed["next_due_date"] is None
    assert closed["item"]["last_done_on"] == "2026-03-02"
    again = client.post(
        f"/api/v1/maintenance/{once['id']}/done", json={"done_on": "2026-03-03"}, headers=h
    )
    assert again.status_code == 409
    assert again.json()["code"] == "MHVP-PROP-0005"
    listed = _ok(client.get(f"{P}/{prop['id']}/maintenance", headers=h))
    by_id = {x["id"]: x for x in listed}
    assert by_id[once["id"]]["last_done_on"] == "2026-03-02"
    assert by_id[item["id"]]["status"] == "open"


def test_property_custom_field_values(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "c2admin"))
    prop = _prop(client, h, "937", "rental")
    key = f"c2_{RUN}"
    _ok(
        client.post(
            "/api/v1/custom-fields",
            json={
                "entity_type": "property",
                "key": key,
                "label": "Objektakte Nr.",
                "field_type": "string",
            },
            headers=h,
        ),
        201,
    )
    number_key = f"c2n_{RUN}"
    _ok(
        client.post(
            "/api/v1/custom-fields",
            json={
                "entity_type": "property",
                "key": number_key,
                "label": "Stellplätze",
                "field_type": "integer",
            },
            headers=h,
        ),
        201,
    )
    fields = _ok(client.get("/api/v1/custom-fields?entity_type=property", headers=h))
    assert {f["key"] for f in fields} >= {key, number_key}
    url = f"{P}/{prop['id']}"
    version = _ok(client.get(url, headers=h))["version"]
    updated = _ok(
        client.patch(
            url,
            json={"custom_fields": {key: "OA-2026-01", number_key: 4}},
            headers=h | {"If-Match": f'"{version}"'},
        )
    )
    assert updated["custom_fields"] == {key: "OA-2026-01", number_key: 4}
    assert updated["version"] == version + 1
    # type check and stale version
    assert (
        client.patch(
            url,
            json={"custom_fields": {key: "x", number_key: "vier"}},
            headers=h | {"If-Match": f'"{version + 1}"'},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            url,
            json={"custom_fields": {key: "y", number_key: 4}},
            headers=h | {"If-Match": f'"{version}"'},
        ).status_code
        == 412
    )
    assert (
        client.patch(
            url,
            json={"custom_fields": {"undefined_key": 1}},
            headers=h | {"If-Match": f'"{version + 1}"'},
        ).status_code
        == 422
    )


def test_authorization_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "c2admin"))
    caretaker = bearer(login(client, world, "c2caretaker"))
    other = bearer(login(client, world, "c2other"))
    prop = _prop(client, h, "938", "rental")
    contact = _contact(client, h, "Notdienst")
    assignment = _ok(
        client.post(
            f"{P}/{prop['id']}/contacts",
            json={
                "contact_id": contact["id"],
                "category_code": "emergency",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    meter = _ok(
        client.post(
            f"{P}/{prop['id']}/meters",
            json={"meter_type_code": "gas", "number": "G-1", "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    item = _ok(
        client.post(
            f"{P}/{prop['id']}/maintenance",
            json={"kind": "inspection", "title": "Aufzugprüfung", "interval_months": 12},
            headers=h,
        ),
        201,
    )
    calls = [
        ("PATCH", f"{P}/{prop['id']}/contacts/{assignment['id']}", {"valid_to": "2026-12-31"}),
        ("PATCH", f"/api/v1/meters/{meter['id']}", {"location": "Flur"}),
        ("PATCH", f"/api/v1/maintenance/{item['id']}", {"title": "Aufzug TÜV"}),
        ("POST", f"/api/v1/maintenance/{item['id']}/done", {"done_on": "2026-02-01"}),
    ]
    for method, url, body in calls:
        assert client.request(method, url, json=body, headers=caretaker).status_code == 403, url
        assert client.request(method, url, json=body, headers=other).status_code == 404, url
    # the reader of the same tenant sees the rows, the foreign tenant sees nothing
    assert len(_ok(client.get(f"{P}/{prop['id']}/contacts", headers=caretaker))) == 1
    assert _ok(client.get(f"{P}/{prop['id']}/contacts", headers=other)) == []
    assert _ok(client.get(f"{P}/{prop['id']}/maintenance", headers=other)) == []
    # nothing changed through the refused calls
    assert (
        _ok(client.get(f"{P}/{prop['id']}/maintenance", headers=h))[0]["title"] == "Aufzugprüfung"
    )
