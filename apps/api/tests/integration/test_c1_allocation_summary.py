"""Package C1 (Stammdaten in der Oberfläche): allocation key update with ``expected_total`` and
the per property allocation summary that the CRM uses for the sum warning.

Fixed expected values (rule 0.1.8): three units with MEA 400, 350 and 250 against an expected
total of 1000; at a date before the third value the sum is 750 and the difference -250.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _ok, _property

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"c1a-{RUN}", name=f"C1 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"c1b-{RUN}", name=f"C1 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("c1admin", a, "tenant_admin"),
            ("c1caretaker", a, "caretaker"),
            ("c1other", b, "tenant_admin"),
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


def _value(
    c: TestClient, h: dict[str, str], unit_id: str, key_id: str, value: str, valid_from: str
) -> Any:
    return c.post(
        f"/api/v1/units/{unit_id}/allocation-values",
        json={"allocation_key_id": key_id, "value": value, "valid_from": valid_from},
        headers=h,
    )


def test_summary_sums_values_per_key_and_reports_the_expected_total(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "c1admin"))
    prop = _property(client, h, "710", "hoa")
    pid = prop["id"]
    building = _ok(
        client.post(f"/api/v1/properties/{pid}/buildings", json={"name": "Haus A"}, headers=h)
    )
    key = _ok(
        client.post(
            f"/api/v1/properties/{pid}/allocation-keys",
            json={
                "code": "C1MEA",
                "name": "Miteigentumsanteile (C1)",
                "unit_of_measure": "MEA",
                "kind": "static",
                "expected_total": "1000",
            },
            headers=h,
        )
    )
    assert key["expected_total"] == "1000.00000000"
    units: dict[str, str] = {}
    for number in ["1", "2", "3"]:
        units[number] = _ok(
            client.post(
                f"/api/v1/properties/{pid}/units",
                json={"building_id": building["id"], "number": number, "unit_type": "apartment"},
                headers=h,
            )
        )["id"]
    _ok(_value(client, h, units["1"], key["id"], "400", "2020-01-01"))
    _ok(_value(client, h, units["2"], key["id"], "350", "2020-01-01"))
    _ok(_value(client, h, units["3"], key["id"], "250", "2026-07-01"))

    before = _ok(
        client.get(
            f"/api/v1/properties/{pid}/allocation-summary",
            params={"as_of": "2026-06-30"},
            headers=h,
        ),
        200,
    )
    assert before["as_of"] == "2026-06-30"
    assert [u["number"] for u in before["units"]] == ["1", "2", "3"]
    row = next(k for k in before["keys"] if k["code"] == "C1MEA")
    assert row["total"] == "750.00000000"
    assert row["expected_total"] == "1000.00000000"
    assert row["difference"] == "-250.00000000"
    assert (row["units_with_value"], row["units_without_value"]) == (2, 1)
    assert len([v for v in before["values"] if v["allocation_key_id"] == key["id"]]) == 2

    after = _ok(
        client.get(
            f"/api/v1/properties/{pid}/allocation-summary",
            params={"as_of": "2026-09-01"},
            headers=h,
        ),
        200,
    )
    row = next(k for k in after["keys"] if k["code"] == "C1MEA")
    assert row["total"] == "1000.00000000"
    assert row["difference"] == "0.00000000"
    assert (row["units_with_value"], row["units_without_value"]) == (3, 0)
    # Template keys without an expected total carry no difference (nothing is assumed).
    template = next(k for k in after["keys"] if k["code"] != "C1MEA")
    assert template["expected_total"] is None
    assert template["difference"] is None

    # Update: name and expected total change, the code stays immutable.
    patched = _ok(
        client.patch(
            f"/api/v1/properties/{pid}/allocation-keys/{key['id']}",
            json={"name": "Miteigentumsanteile laut Teilungserklärung", "expected_total": "10000"},
            headers=h,
        ),
        200,
    )
    assert patched["expected_total"] == "10000.00000000"
    assert patched["code"] == "C1MEA"
    assert (
        client.patch(
            f"/api/v1/properties/{pid}/allocation-keys/{key['id']}",
            json={"code": "NEU"},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/properties/{pid}/allocation-keys/{key['id']}",
            json={"expected_total": "-1"},
            headers=h,
        ).status_code
        == 422
    )
    # The deviation is information only: the summary still answers 200 with the difference.
    deviating = _ok(
        client.get(
            f"/api/v1/properties/{pid}/allocation-summary",
            params={"as_of": "2026-09-01"},
            headers=h,
        ),
        200,
    )
    row = next(k for k in deviating["keys"] if k["code"] == "C1MEA")
    assert row["difference"] == "-9000.00000000"


def test_validation_unit_number_unique_and_period_order(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "c1admin"))
    prop = _property(client, h, "711", "rental")
    pid = prop["id"]
    building = _ok(
        client.post(f"/api/v1/properties/{pid}/buildings", json={"name": "Haus"}, headers=h)
    )
    body = {"building_id": building["id"], "number": "WE1", "unit_type": "apartment"}
    unit = _ok(client.post(f"/api/v1/properties/{pid}/units", json=body, headers=h))
    duplicate = client.post(f"/api/v1/properties/{pid}/units", json=body, headers=h)
    assert duplicate.status_code == 409, duplicate.text
    key = _ok(
        client.post(
            f"/api/v1/properties/{pid}/allocation-keys",
            json={
                "code": "C1WFL",
                "name": "Wohnfläche (C1)",
                "unit_of_measure": "m2",
                "kind": "static",
            },
            headers=h,
        )
    )
    wrong_period = client.post(
        f"/api/v1/units/{unit['id']}/allocation-values",
        json={
            "allocation_key_id": key["id"],
            "value": "65.5",
            "valid_from": "2026-02-01",
            "valid_to": "2026-01-01",
        },
        headers=h,
    )
    assert wrong_period.status_code == 422
    assert (
        client.post(f"/api/v1/properties/{pid}/buildings", json={"name": ""}, headers=h).status_code
        == 422
    )
    # A key of another property is not accepted on the update route of this property.
    other = _property(client, h, "712", "rental")
    assert (
        client.patch(
            f"/api/v1/properties/{other['id']}/allocation-keys/{key['id']}",
            json={"expected_total": "1"},
            headers=h,
        ).status_code
        == 404
    )


def test_authorization_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "c1admin"))
    prop = _property(client, h, "713", "hoa")
    pid = prop["id"]
    keys = _ok(client.get(f"/api/v1/properties/{pid}/allocation-keys", headers=h), 200)
    key_id = keys[0]["id"]

    caretaker = bearer(login(client, world, "c1caretaker"))
    assert (
        client.get(f"/api/v1/properties/{pid}/allocation-summary", headers=caretaker).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/properties/{pid}/allocation-keys/{key_id}",
            json={"expected_total": "1000"},
            headers=caretaker,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/properties/{pid}/buildings", json={"name": "Haus"}, headers=caretaker
        ).status_code
        == 403
    )

    other = bearer(login(client, world, "c1other", tenant_id=world.tenant_b))
    assert (
        client.get(f"/api/v1/properties/{pid}/allocation-summary", headers=other).status_code == 404
    )
    assert (
        client.patch(
            f"/api/v1/properties/{pid}/allocation-keys/{key_id}",
            json={"expected_total": "1000"},
            headers=other,
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/properties/{pid}/allocation-summary").status_code == 401
