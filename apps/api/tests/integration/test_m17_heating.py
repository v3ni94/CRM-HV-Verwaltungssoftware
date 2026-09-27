"""M17-02 draft heating statement over the API (D25 to D27, expected values from
tests/unit/test_m17_heating_calc.py case A: A 1.500,00 / B 740,96 / C 759,04 by time share,
B 832,50 / C 667,50 with the draft degree day table). Issuing stays behind G3 (not tested
here, see test_m17_operating_costs)."""

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
DEGREE_DAYS = {
    "1": "170", "2": "150", "3": "130", "4": "80", "5": "40", "6": "10",
    "7": "0", "8": "0", "9": "30", "10": "90", "11": "130", "12": "170",
}  # fmt: skip


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"hk17-{RUN}", name=f"HK {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"hk17b-{RUN}", name=f"HKB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("hkadmin", a, "tenant_admin"),
            ("hkclerk", a, "clerk_no_accounting"),
            ("hkother", b, "tenant_admin"),
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


def _setup(client: TestClient, h: dict[str, str]) -> tuple[str, dict[str, str]]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "772", "name": "Heizhaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(client, h, "Vermieter", "company")
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
    contracts: dict[str, str] = {}
    units: dict[str, str] = {}
    for number, name, start, end in [
        ("01", "a", "2024-01-01", None),
        ("02", "b", "2024-01-01", "2025-03-31"),
        ("02", "c", "2025-04-01", None),
    ]:
        if name != "c":
            unit = _ok(
                client.post(
                    f"/api/v1/properties/{prop['id']}/units",
                    json={"building_id": building, "number": number, "unit_type": "apartment"},
                    headers=h,
                ),
                201,
            )["id"]
            _ok(
                client.post(
                    f"/api/v1/units/{unit}/allocation-values",
                    json={
                        "allocation_key_id": keys["WFL"],
                        "value": "50",
                        "valid_from": "2020-01-01",
                    },
                    headers=h,
                ),
                201,
            )
            units[number] = unit
        tenant, _ = _party(client, h, f"Mieter{name}")
        body = {
            "kind": "tenancy",
            "unit_id": units[number],
            "party_id": tenant,
            "start_date": start,
        }
        c = _ok(client.post("/api/v1/contracts", json=body, headers=h), 201)
        if end:
            _ok(
                client.post(
                    f"/api/v1/contracts/{c['id']}/termination",
                    json={
                        "end_date": end,
                        "termination_date": "2025-01-31",
                        "termination_reason": "Kündigung Mieter",
                    },
                    headers=h,
                )
            )
        contracts[name] = c["id"]
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
    )
    return st["id"], contracts


def test_heating_draft_d25_d27(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "hkadmin"))
    st, contracts = _setup(client, h)
    hp = f"{S}/{st}/heating"
    initial = _ok(client.get(hp, headers=h))
    assert initial["settings"]["consumption_share_percent"] == 70
    assert initial["tables"]["degree_days"]["review_status"] == "fehlt"
    assert initial["tables"]["co2_steps"]["review_status"] == "zu_pruefen"
    keys = {o["unit_number"] + o["from"]: o["key"] for o in initial["occupants"]}
    ka, kb, kc = keys["012025-01-01"], keys["022025-01-01"], keys["022025-04-01"]

    # D27: unknown CO2 facts -> review status, apply refused, no zero costs.
    _ok(
        client.put(
            hp,
            json={
                "total_costs": "3000.00",
                "settings": {"hot_water_flat_percent": "0"},
                "co2": {"building_kind": "unknown", "costs": "100.00"},
            },
            headers=h,
        )
    )
    _ok(
        client.put(
            f"{hp}/consumptions",
            json={
                "consumptions": {
                    ka: {"heating": "1000"},
                    kb: {"heating": "600"},
                    kc: {"heating": "400"},
                }
            },
            headers=h,
        )
    )
    r = _ok(client.post(f"{hp}/calculate", headers=h))["result"]
    assert r["co2"]["status"] == "pruefen"
    assert r["allocable_costs"] == "3000.00"
    assert client.post(f"{hp}/apply", headers=h).status_code == 422

    # D25 by time share (no degree day table): B 740,96 / C 759,04.
    _ok(
        client.put(
            hp,
            json={
                "total_costs": "3000.00",
                "settings": {"hot_water_flat_percent": "0"},
                "co2": {"mode": "not_applicable", "reason": "Testfall ohne CO2-Kosten"},
            },
            headers=h,
        )
    )
    consumptions = _ok(client.get(hp, headers=h))["consumptions"]
    assert consumptions[kb]["heating"] == "600"  # inputs survive the settings update
    r = _ok(client.post(f"{hp}/calculate", headers=h))["result"]
    assert {r["per_occupant"][k]["total"] for k in (ka, kb, kc)} == {"1500.00", "740.96", "759.04"}
    assert r["per_occupant"][kb]["total"] == "740.96"
    assert any("Gradtagstabelle" in n for n in r["notes"])

    # Degree day table (draft, source required) -> winter tenant B 832,50.
    assert (
        client.put(
            "/api/v1/billing/heating-rule-tables",
            json={
                "kind": "degree_days",
                "valid_from": "2025-01-01",
                "rows": {"1": "1000"},
                "source": "Test",
            },
            headers=h,
        ).status_code
        == 422
    )
    _ok(
        client.put(
            "/api/v1/billing/heating-rule-tables",
            json={
                "kind": "degree_days",
                "valid_from": "2025-01-01",
                "rows": DEGREE_DAYS,
                "source": "Beispieltabelle Test, zu prüfen",
            },
            headers=h,
        )
    )
    assert (
        _ok(client.get("/api/v1/billing/heating-rule-tables", headers=h))[0]["kind"]
        == "degree_days"
    )
    r = _ok(client.post(f"{hp}/calculate", headers=h))["result"]
    assert (r["per_occupant"][kb]["total"], r["per_occupant"][kc]["total"]) == ("832.50", "667.50")
    assert r["vacancy_owner_share"] == "0.00"

    # Feed into the statement and calculate it: the external amounts per contract match.
    applied = _ok(client.post(f"{hp}/apply", headers=h))
    assert applied["item"]["amount"] == "3000.00"
    info = _ok(client.get(f"{hp}/consumption-info", headers=h))
    assert len(info["units"]) == 3
    assert info["units"][0]["status"] == "entwurf"
    calc = _ok(client.post(f"{S}/{st}/calculate", headers=h))
    by_contract = {x["contract_id"]: x["costs"] for x in calc["snapshot"]["results"]}
    assert by_contract[contracts["b"]] == "832.50"
    assert by_contract[contracts["a"]] == "1500.00"
    # After calculation the draft inputs are frozen (new version needed).
    assert client.post(f"{hp}/calculate", headers=h).status_code == 409
    assert client.put(hp, json={"total_costs": "1.00"}, headers=h).status_code == 409

    # Authorization and tenant separation.
    clerk = bearer(login(client, world, "hkclerk"))
    assert client.get(hp, headers=clerk).status_code == 403
    other = bearer(login(client, world, "hkother", tenant_id=world.tenant_b))
    assert client.get(hp, headers=other).status_code == 404
