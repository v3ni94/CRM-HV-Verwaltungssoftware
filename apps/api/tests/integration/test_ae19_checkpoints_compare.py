"""AE19: manageable check points (AB10-01) and heating comparison (M17-02) over the API."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
S = "/api/v1/statements"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae19a-{RUN}", name=f"AE19 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae19b-{RUN}", name=f"AE19B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae19admin", a, "tenant_admin"),
            ("ae19clerk", a, "clerk_no_accounting"),
            ("ae19other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_checkpoint_lifecycle(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae19admin"))
    clerk = bearer(login(client, world, "ae19clerk"))
    other = bearer(login(client, world, "ae19other"))
    cp = f"{A}/rule-versions/checkpoints"
    body = {"title": "Nachrüstfrist Objekt 1", "effective_from": "2026-10-15", "source": "Q1"}
    assert client.post(cp, json=body, headers=clerk).status_code == 403
    assert client.post(cp, json={"title": "", "effective_from": "x"}, headers=h).status_code == 422
    assert client.post(cp, json={**body, "extra": 1}, headers=h).status_code == 422
    row = _ok(client.post(cp, json=body, headers=h), 201)
    assert row["status"] == "draft"
    assert row["source_status"] == "Q1"
    far = _ok(client.post(cp, json={**body, "effective_from": "2030-01-01"}, headers=h), 201)
    past = _ok(client.post(cp, json={**body, "effective_from": "2020-01-01"}, headers=h), 201)
    states = {
        r["id"]: r["state"] for r in _ok(client.get(cp, params={"on": "2026-10-01"}, headers=h))
    }
    assert states[row["id"]] == "upcoming"  # 14 days inside the 30 day lead time
    assert states[far["id"]] == "open"
    assert states[past["id"]] == "due"
    only = _ok(client.get(cp, params={"state": "due", "on": "2026-10-01"}, headers=h))
    assert [r["id"] for r in only] == [past["id"]]
    assert client.get(cp, params={"lead_days": 5, "on": "2026-10-01"}, headers=h).status_code == 200
    assert client.get(cp, params={"bogus": 1}, headers=h).status_code == 422
    assert client.get(cp, headers=clerk).status_code == 403
    assert _ok(client.get(cp, headers=other)) == []
    patched = _ok(client.patch(f"{cp}/{row['id']}", json={"title": "Neu"}, headers=h))
    assert patched["title"] == "Neu"
    assert client.patch(f"{cp}/{row['id']}", json={"title": "x"}, headers=other).status_code == 404
    _ok(client.post(f"{A}/rule-versions/{row['id']}/withdraw", headers=h))
    assert client.patch(f"{cp}/{row['id']}", json={"title": "y"}, headers=h).status_code == 409
    done = _ok(client.get(cp, params={"state": "withdrawn"}, headers=h))
    assert [r["id"] for r in done] == [row["id"]]


def _statement(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "919", "name": "AE19 Haus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(client, h, "Vermieter AE19", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/units/{unit}/allocation-values",
            json={"allocation_key_id": keys["WFL"], "value": "50", "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenant, _ = _party(client, h, "Mieter AE19")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    ledger = _ok(client.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)[
        "id"
    ]
    st = _ok(
        client.post(
            S,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )["id"]
    return st, unit


def test_heating_comparison(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae19admin"))
    clerk = bearer(login(client, world, "ae19clerk"))
    other = bearer(login(client, world, "ae19other"))
    st, _unit = _statement(client, h)
    hp = f"{S}/{st}/heating"
    cmp_ = f"{hp}/comparison"
    first = _ok(client.get(cmp_, headers=h))
    assert first["status"] == "nicht_berechenbar"
    key = _ok(client.get(hp, headers=h))["occupants"][0]["key"]
    _ok(
        client.put(
            hp,
            json={
                "total_costs": "1000.00",
                "settings": {"hot_water_flat_percent": "0"},
                "co2": {"mode": "not_applicable", "reason": "Test"},
            },
            headers=h,
        )
    )
    _ok(
        client.put(f"{hp}/consumptions", json={"consumptions": {key: {"heating": "10"}}}, headers=h)
    )
    _ok(client.post(f"{hp}/calculate", headers=h))
    missing = _ok(client.get(cmp_, headers=h))
    assert missing["rows"][0]["status"] == "extern_fehlt"
    assert missing["rows"][0]["own"] == "1000.00"
    _ok(
        client.post(
            f"{S}/{st}/cost-items",
            json={
                "label": "Heizung Messdienst",
                "amount": "900.00",
                "heating": True,
                "external_amounts": {key: "900.00"},
                "basis": "Messdienst Abrechnung",
            },
            headers=h,
        ),
        201,
    )
    res = _ok(client.get(cmp_, headers=h))
    row = res["rows"][0]
    assert (row["status"], row["difference"], row["percent"]) == ("abweichung", "100.00", "11.11")
    assert res["summary"]["deviations"] == 1
    tol = _ok(client.get(cmp_, params={"tolerance_abs": "150.00"}, headers=h))
    assert tol["rows"][0]["status"] == "ok"
    csv = client.get(f"{cmp_}/report", headers=h)
    assert csv.status_code == 200
    assert "abweichung" in csv.text
    assert "100,00" in csv.text
    assert client.get(cmp_, params={"tolerance_abs": "-1"}, headers=h).status_code == 422
    assert client.get(cmp_, params={"x": "1"}, headers=h).status_code == 422
    assert client.get(cmp_, headers=clerk).status_code == 403
    assert client.get(cmp_, headers=other).status_code == 404
