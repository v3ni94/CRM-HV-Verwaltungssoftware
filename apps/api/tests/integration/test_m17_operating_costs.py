"""M17 operating cost statement (drafts; issuing needs G3). Expected values by hand, year 2025
(365 days), living area 50/50/100: unit 02 let until 30.06. (181 days), vacant 184 days.
Weights 18.250 / 9.050 / 9.200 (vacancy) / 36.500 = 73.000. Caretaker 2.000,00 ->
500,00 / 247,95 (rest cent by largest remainder) / 252,05 owner / 1.000,00.
Heating 600,00 from an external statement: 200 / 100 / 300. Tenant A: advances due 100,00,
paid 100,00 -> balance 700,00 - 100,00 = 600,00. D08 and D10 checked separately."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.billing.calc import Share, distribute
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
S = "/api/v1/statements"


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bk17-{RUN}", name=f"BK {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m17admin", "tenant_admin"), ("m17acc", "accountant_no_banking")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_d08_d10_units() -> None:
    parts = distribute(
        Decimal("100.00"),
        [
            Share(("02", "b"), Decimal(1)),
            Share(("01", "a"), Decimal(1)),
            Share(("03", "c"), Decimal(1)),
        ],
    )
    assert parts == {
        ("01", "a"): Decimal("33.34"),
        ("02", "b"): Decimal("33.33"),
        ("03", "c"): Decimal("33.33"),
    }
    reordered = distribute(
        Decimal("100.00"),
        [
            Share(("03", "c"), Decimal(1)),
            Share(("01", "a"), Decimal(1)),
            Share(("02", "b"), Decimal(1)),
        ],
    )
    assert reordered == parts  # screen order does not move the cent


def test_operating_cost_statement(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, gated = clients
    h = bearer(login(client, world, "m17admin"))
    acc_user = bearer(login(client, world, "m17acc"))
    assert (
        _ok(
            client.post(
                f"{S}/co2-split", json={"specific_emissions": "12.0", "costs": "100.00"}, headers=h
            )
        )["tenant"]
        == "90.00"
    )
    assert (
        _ok(
            client.post(
                f"{S}/co2-split", json={"specific_emissions": "11.9", "costs": "100.00"}, headers=h
            )
        )["landlord"]
        == "0.00"
    )

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "771", "name": "Miethaus", "management_type": "rental"},
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
    contracts = {}
    for number, area, start, end in [
        ("01", "50", "2024-01-01", None),
        ("02", "50", "2024-01-01", "2025-06-30"),
        ("03", "100", "2024-01-01", None),
    ]:
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
                json={"allocation_key_id": keys["WFL"], "value": area, "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
        tenant, _ = _party(client, h, f"Mieter{number}")
        body = {"kind": "tenancy", "unit_id": unit, "party_id": tenant, "start_date": start}
        c = _ok(client.post("/api/v1/contracts", json=body, headers=h), 201)
        if end:
            _ok(
                client.post(
                    f"/api/v1/contracts/{c['id']}/termination",
                    json={
                        "end_date": end,
                        "termination_date": "2025-03-31",
                        "termination_reason": "Kündigung Mieter",
                    },
                    headers=h,
                )
            )
        contracts[number] = c
    a = contracts["01"]
    _ok(
        client.post(
            f"/api/v1/contracts/{a['id']}/payments",
            json={
                "payment_type_code": "operating_cost_advance",
                "net": "100.00",
                "gross": "100.00",
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{a['id']}/schedules",
            json={"valid_from": "2024-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )

    ledger = _ok(client.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)[
        "id"
    ]
    revenue = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "061000",
                "name": "BK-Vorauszahlungen",
                "category": "revenue",
                "type": "income",
            },
            headers=h,
        ),
        201,
    )["id"]
    bank = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={"number": "001210", "name": "Mietkonto", "category": "bank", "type": "asset"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "operating_cost_advance", "account_id": revenue},
            headers=h,
        )
    )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2025-01-01", "scope": "contract", "scope_id": a["id"]},
            headers=h,
        ),
        201,
    )
    posted = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-01-31"}, headers=h)
    )[0]
    debtor = item["account_id"]
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "debtor_payment",
                "booking_date": "2025-01-05",
                "text": "Zahlung",
                "lines": [
                    {"account_id": bank, "debit": "100.00"},
                    {"account_id": debtor, "credit": "100.00"},
                ],
                "settlements": [{"open_item_id": item["id"], "amount": "100.00"}],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    assert posted["status"] == "posted"

    st = _ok(
        client.post(
            S,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    assert st["deadline_orientation"] == "2026-12-31"
    occ = _ok(client.get(f"{S}/{st['id']}/occupants", headers=h))
    vacancy_key = next(o["key"] for o in occ if o["contract_id"] is None)
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Hausmeister",
                "amount": "2000.00",
                "allocation_key_id": keys["WFL"],
                "basis": "§ 4 Mietvertrag, Anlage Betriebskosten",
            },
            headers=h,
        ),
        201,
    )
    heating_bad = _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={"label": "Heizung", "amount": "600.00", "heating": True, "basis": "Messdienst"},
            headers=h,
        ),
        201,
    )
    assert (
        client.post(f"{S}/{st['id']}/calculate", headers=h).status_code == 422
    )  # heating only external (H01)
    st = _ok(
        client.post(
            S,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Hausmeister",
                "amount": "2000.00",
                "allocation_key_id": keys["WFL"],
                "basis": "§ 4 Mietvertrag, Anlage Betriebskosten",
            },
            headers=h,
        ),
        201,
    )
    ext = {
        f"contract:{contracts['01']['id']}": "200.00",
        f"contract:{contracts['02']['id']}": "100.00",
        f"contract:{contracts['03']['id']}": "300.00",
    }
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Heizung",
                "amount": "600.00",
                "heating": True,
                "external_amounts": ext,
                "basis": "Messdienstabrechnung 2025",
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    assert heating_bad["id"]
    snap = calc["snapshot"]
    assert calc["status"] == "calculated"
    by = {r["unit_number"]: r for r in snap["results"]}
    assert by["01"]["costs"] == "700.00"
    assert by["02"]["costs"] == "347.95"
    assert by["03"]["costs"] == "1300.00"
    assert snap["vacancy_owner_share"] == "252.05"
    assert Decimal(by["01"]["costs"]) + Decimal(by["02"]["costs"]) + Decimal(
        by["03"]["costs"]
    ) + Decimal(snap["vacancy_owner_share"]) == Decimal("2600.00")
    assert (by["01"]["advances_due"], by["01"]["advances_paid"], by["01"]["balance"]) == (
        "100.00",
        "100.00",
        "600.00",
    )
    assert vacancy_key.startswith("vacancy:")
    assert (
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={"label": "x", "amount": "1", "allocation_key_id": keys["WFL"], "basis": "abc"},
            headers=h,
        ).status_code
        == 409
    )

    # Status model: second person approves internally; issuing needs G3 and the access date.
    assert (
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=h
        ).status_code
        == 403
    )
    _ok(
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=acc_user
        )
    )
    closed = client.post(
        f"{S}/{st['id']}/transition",
        json={"target": "issued", "delivered_at": "2026-09-30"},
        headers=acc_user,
    )
    assert closed.status_code == 403
    gh = bearer(login(gated, world, "m17acc"))
    assert (
        gated.post(f"{S}/{st['id']}/transition", json={"target": "issued"}, headers=gh).status_code
        == 422
    )
    issued = _ok(
        gated.post(
            f"{S}/{st['id']}/transition",
            json={"target": "issued", "delivered_at": "2026-09-30"},
            headers=gh,
        )
    )
    assert issued["status"] == "issued"
    assert (
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "resolved"}, headers=acc_user
        ).status_code
        == 409
    )
    v2 = _ok(client.post(f"{S}/{st['id']}/new-version", headers=h), 201)
    assert v2["version"] == 2
    assert v2["supersedes_id"] == st["id"]
    assert (
        _ok(client.get(f"{S}/{st['id']}", headers=h))["snapshot"]["hash"] == snap["hash"]
    )  # issued version unchanged
