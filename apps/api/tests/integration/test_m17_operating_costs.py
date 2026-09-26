"""M17 operating cost statement (drafts; issuing needs G3). Expected values by hand, year 2025
(365 days), living area 50/50/100: unit 02 let until 30.06. (181 days), vacant 184 days.
Weights 18.250 / 9.050 / 9.200 (vacancy) / 36.500 = 73.000. Caretaker 2.000,00 ->
500,00 / 247,95 (rest cent by largest remainder) / 252,05 owner / 1.000,00.
Heating 600,00 from an external statement: 200 / 100 / 300. Tenant A: advances due 100,00,
paid 100,00 -> balance 700,00 - 100,00 = 600,00. D08 and D10 checked separately."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, cast
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
    listed = _ok(client.get(S, params={"ledger_id": ledger}, headers=h))
    assert st["id"] in {x["id"] for x in listed}
    detail = _ok(client.get(f"{S}/{st['id']}", headers=h))
    assert [i["label"] for i in detail["cost_items"]] == ["Hausmeister", "Heizung"]
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


# A23 and A24 (LUECKENLISTE 26.09.2026): annex D cases D21, D22, D23, D28 -----------------


def _rental_world(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    """Rental property with one let unit (living area 60), owner ledger and the WFL key."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Miethaus {number}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(client, h, f"Vermieter{number}", "company")
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
            json={"allocation_key_id": keys["WFL"], "value": "60", "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenant, _ = _party(client, h, f"Mieter{number}")
    contract = _ok(
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
    return {
        "property": prop["id"],
        "unit": unit,
        "contract": contract,
        "ledger": ledger,
        "keys": keys,
    }


def _statement(
    client: TestClient, h: dict[str, str], ledger: str, year: int = 2025
) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        client.post(
            S,
            json={
                "ledger_id": ledger,
                "period_from": f"{year}-01-01",
                "period_to": f"{year}-12-31",
            },
            headers=h,
        ),
        201,
    )


def _account(
    client: TestClient, h: dict[str, str], ledger: str, number: str, name: str, **extra: Any
) -> str:
    body = {"number": number, "name": name, "category": "cost", "type": "expense", **extra}
    return str(_ok(client.post(f"{A}/ledgers/{ledger}/accounts", json=body, headers=h), 201)["id"])


def _calc_error(client: TestClient, h: dict[str, str], ledger: str, item: dict[str, Any]) -> str:
    st = _statement(client, h, ledger)
    _ok(client.post(f"{S}/{st['id']}/cost-items", json=item, headers=h), 201)
    response = client.post(f"{S}/{st['id']}/calculate", headers=h)
    assert response.status_code == 422, response.text
    return str(response.json()["detail"])


def test_d21_let_condominium_needs_recorded_key(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D21: let condominium (SEV) without a deviating agreement. Owner A holds units 01 and 03
    (co-ownership shares 250 and 500 per the declaration of division), owner B unit 02. The
    living area key copied from the tenant template is refused as automatic m² rule; the key
    recorded for the property with its source distributes the owner's cost 750,00 EUR (his
    share from the HOA statement, the transition itself is A06) as 250,00 / 500,00 EUR. Owner
    B's let unit never appears in owner A's statement (legal entity separation)."""
    client, _ = clients
    h = bearer(login(client, world, "m17admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "772", "name": "WEG mit SEV", "management_type": "hoa_with_sev"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    units = {}
    for number in ("01", "02", "03"):
        units[number] = _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/units",
                json={"building_id": building, "number": number, "unit_type": "apartment"},
                headers=h,
            ),
            201,
        )["id"]
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    for number in ("01", "02", "03"):
        _ok(
            client.post(
                f"/api/v1/units/{units[number]}/allocation-values",
                json={"allocation_key_id": keys["WFL"], "value": "50", "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
    ownership = {
        "kind": "ownership",
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
        "sev_enabled": True,
    }
    owners = {"A": _party(client, h, "SEVEigA")[0], "B": _party(client, h, "SEVEigB")[0]}
    contracts = {}
    for number, owner in (("01", "A"), ("02", "B"), ("03", "A")):
        _ok(
            client.post(
                "/api/v1/contracts",
                json={**ownership, "unit_id": units[number], "party_id": owners[owner]},
                headers=h,
            ),
            201,
        )
        tenant, _ = _party(client, h, f"SEVMieter{number}")
        contracts[number] = _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": units[number],
                    "party_id": tenant,
                    "start_date": "2024-01-01",
                },
                headers=h,
            ),
            201,
        )
    sev_entity = contracts["01"]["legal_entity_id"]
    assert sev_entity == contracts["03"]["legal_entity_id"]
    assert sev_entity != contracts["02"]["legal_entity_id"]
    ledger = _ok(client.post(f"{A}/ledgers", json={"legal_entity_id": sev_entity}, headers=h), 201)[
        "id"
    ]

    # Only the SEV owner's unit belongs to the statement.
    st = _statement(client, h, ledger)
    occ = _ok(client.get(f"{S}/{st['id']}/occupants", headers=h))
    assert [o["unit_number"] for o in occ] == ["01", "03"]
    assert occ[0]["contract_id"] == contracts["01"]["id"]

    # Template key (living area) is no automatic distribution basis for a let condominium.
    detail = _calc_error(
        client,
        h,
        ledger,
        {
            "label": "Gartenpflege",
            "amount": "750.00",
            "allocation_key_id": keys["WFL"],
            "basis": "§ 4 Mietvertrag, keine abweichende Vereinbarung zum Schlüssel",
        },
    )
    assert "556a" in detail
    assert "WFL" in detail

    # Key recorded for the property with source (declaration of division) and validity start.
    mea = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/allocation-keys",
            json={
                "code": "MEA_TE",
                "name": "Miteigentumsanteile laut Teilungserklärung vom 01.03.2019",
                "unit_of_measure": "MEA",
                "kind": "static",
            },
            headers=h,
        ),
        201,
    )["id"]
    for number, share in (("01", "250"), ("02", "250"), ("03", "500")):
        _ok(
            client.post(
                f"/api/v1/units/{units[number]}/allocation-values",
                json={"allocation_key_id": mea, "value": share, "valid_from": "2019-03-01"},
                headers=h,
            ),
            201,
        )
    st = _statement(client, h, ledger)
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Gartenpflege",
                "amount": "750.00",
                "allocation_key_id": mea,
                "basis": "§ 4 Mietvertrag; Schlüssel: WEG-Verteilungsmaßstab laut "
                "Teilungserklärung vom 01.03.2019 (§ 556a Abs. 3 BGB)",
            },
            headers=h,
        ),
        201,
    )
    result = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    by = {r["unit_number"]: r for r in result["snapshot"]["results"]}
    assert list(by) == ["01", "03"]
    # 750,00 x 250 / 750 = 250,00 and 750,00 x 500 / 750 = 500,00 (whole year, same days).
    assert (by["01"]["costs"], by["03"]["costs"]) == ("250.00", "500.00")
    assert result["snapshot"]["vacancy_owner_share"] == "0.00"
    position = _ok(client.get(f"{S}/{st['id']}", headers=h))["snapshot"]
    assert position["total"] == "750.00"


def test_d22_mixed_invoice_split_must_be_posted(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D22: mixed invoice 1.000,00 EUR, of which 700,00 EUR caretaker (allocable) and 300,00 EUR
    repair (not allocable), posted split on two accounts. The full 1.000,00 EUR on the
    caretaker account is refused (exceeds the posted 700,00 EUR), the repair account and an
    unclassified account are refused; 700,00 EUR on the caretaker account reach the tenant."""
    client, _ = clients
    h = bearer(login(client, world, "m17admin"))
    w = _rental_world(client, h, "773")
    ledger = w["ledger"]
    caretaker = _account(
        client, h, ledger, "042000", "Hausmeister", allocation_category="allocable_other"
    )
    repair = _account(
        client, h, ledger, "045000", "Instandsetzung", allocation_category="non_allocable_other"
    )
    unclassified = _account(client, h, ledger, "046000", "Kabel-TV")
    bank = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={"number": "001210", "name": "Mietkonto", "category": "bank", "type": "asset"},
            headers=h,
        ),
        201,
    )["id"]
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "custom",
                "booking_date": "2025-03-01",
                "text": "Rechnung Hausmeisterdienst mit Reparaturanteil",
                "lines": [
                    {"account_id": caretaker, "debit": "700.00"},
                    {"account_id": repair, "debit": "300.00"},
                    {"account_id": bank, "credit": "1000.00"},
                ],
            },
            headers=h,
        ),
        201,
    )
    assert (
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))["status"]
        == "posted"
    )
    base = {"allocation_key_id": w["keys"]["WFL"], "basis": "§ 4 Mietvertrag, Nr. 14 BetrKV"}
    whole = _calc_error(
        client,
        h,
        ledger,
        {"label": "Hausmeister", "amount": "1000.00", "account_id": caretaker, **base},
    )
    assert "1000.00" in whole
    assert "700.00" in whole
    assert "Mischrechnung" in whole
    repair_detail = _calc_error(
        client, h, ledger, {"label": "Reparatur", "amount": "300.00", "account_id": repair, **base}
    )
    assert "nicht umlagefähig" in repair_detail
    unclassified_detail = _calc_error(
        client,
        h,
        ledger,
        {"label": "Kabel-TV", "amount": "10.00", "account_id": unclassified, **base},
    )
    assert "nicht eingeordnet" in unclassified_detail
    assert "Kontoname" in unclassified_detail

    st = _statement(client, h, ledger)
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={"label": "Hausmeister", "amount": "700.00", "account_id": caretaker, **base},
            headers=h,
        ),
        201,
    )
    result = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    snap = result["snapshot"]
    assert snap["results"][0]["costs"] == "700.00"
    assert snap["total"] == "700.00"
    detail = _ok(client.get(f"{S}/{st['id']}", headers=h))
    assert detail["snapshot"]["hash"] == snap["hash"]


def test_d23_creation_is_not_access(
    clients: tuple[TestClient, TestClient], world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D23: statement 2025 (deadline orientation 31.12.2026) is calculated on 28.12.2026 with an
    additional payment of 120,00 EUR. Issuing needs the access day: a day before the
    calculation is refused (creation is not access), an access on 05.01.2027 after the deadline
    is refused without a recorded exception, an access before the deadline issues."""
    from datetime import date

    from mhvp.billing import routers as billing_routers

    client, gated = clients
    h = bearer(login(client, world, "m17admin"))
    acc_user = bearer(login(client, world, "m17acc"))
    w = _rental_world(client, h, "774")
    st = _statement(client, h, w["ledger"])
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Gartenpflege",
                "amount": "120.00",
                "allocation_key_id": w["keys"]["WFL"],
                "basis": "§ 4 Mietvertrag, Nr. 10 BetrKV",
            },
            headers=h,
        ),
        201,
    )
    monkeypatch.setattr(billing_routers, "local_today", lambda: date(2026, 12, 28))
    result = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    row = result["snapshot"]["results"][0]
    assert (row["balance"], row["late_claim_blocked"]) == ("120.00", False)
    assert result["deadline_orientation"] == "2026-12-31"
    assert result["delivered_at"] is None  # calculation records no access
    _ok(
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=acc_user
        )
    )
    gh = bearer(login(gated, world, "m17acc"))
    before = gated.post(
        f"{S}/{st['id']}/transition",
        json={"target": "issued", "delivered_at": "2026-09-01"},
        headers=gh,
    )
    assert before.status_code == 422, before.text
    assert "Erstellung gilt nicht als Zugang" in before.json()["detail"]
    late = gated.post(
        f"{S}/{st['id']}/transition",
        json={"target": "issued", "delivered_at": "2027-01-05"},
        headers=gh,
    )
    assert late.status_code == 409, late.text
    assert "Nachforderung nach Fristablauf" in late.json()["detail"]
    assert _ok(client.get(f"{S}/{st['id']}", headers=h))["status"] == "internally_approved"
    issued = _ok(
        gated.post(
            f"{S}/{st['id']}/transition",
            json={"target": "issued", "delivered_at": "2026-12-30"},
            headers=gh,
        )
    )
    assert (issued["status"], issued["delivered_at"]) == ("issued", "2026-12-30")


def test_d28_rule_version_pinned_in_snapshot(
    clients: tuple[TestClient, TestClient], world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D28: a later rule version valid from 01.01.2027 never touches the 2025 statement: the
    issued snapshot keeps its version and hash, a new version of the 2025 statement recomputes
    with the old rule, only a 2027 period picks the new rule."""
    from datetime import date

    from mhvp.billing import calc as billing_calc

    client, gated = clients
    h = bearer(login(client, world, "m17admin"))
    acc_user = bearer(login(client, world, "m17acc"))
    w = _rental_world(client, h, "775")
    item = {
        "label": "Gartenpflege",
        "amount": "120.00",
        "allocation_key_id": w["keys"]["WFL"],
        "basis": "§ 4 Mietvertrag, Nr. 10 BetrKV",
    }
    st = _statement(client, h, w["ledger"])
    _ok(client.post(f"{S}/{st['id']}/cost-items", json=item, headers=h), 201)
    old = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))["snapshot"]
    assert old["rule_version"] == "operating-costs-v1"
    _ok(
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=acc_user
        )
    )
    gh = bearer(login(gated, world, "m17acc"))
    _ok(
        gated.post(
            f"{S}/{st['id']}/transition",
            json={"target": "issued", "delivered_at": "2026-09-30"},
            headers=gh,
        )
    )

    # A new rule is published, valid for periods from 01.01.2027.
    monkeypatch.setattr(
        billing_calc,
        "RULE_VERSIONS",
        (*billing_calc.RULE_VERSIONS, (date(2027, 1, 1), "operating-costs-v2")),
    )
    assert billing_calc.rule_version(date(2025, 1, 1)) == "operating-costs-v1"
    assert billing_calc.rule_version(date(2027, 1, 1)) == "operating-costs-v2"
    kept = _ok(client.get(f"{S}/{st['id']}", headers=h))["snapshot"]
    assert (kept["rule_version"], kept["hash"], kept["id"]) == (
        "operating-costs-v1",
        old["hash"],
        old["id"],
    )
    v2 = _ok(client.post(f"{S}/{st['id']}/new-version", headers=h), 201)
    recalculated = _ok(client.post(f"{S}/{v2['id']}/calculate", headers=h))["snapshot"]
    assert recalculated["rule_version"] == "operating-costs-v1"
    assert recalculated["results"][0]["costs"] == "120.00"
    later = _statement(client, h, w["ledger"], year=2027)
    _ok(client.post(f"{S}/{later['id']}/cost-items", json=item, headers=h), 201)
    assert (
        _ok(client.post(f"{S}/{later['id']}/calculate", headers=h))["snapshot"]["rule_version"]
        == "operating-costs-v2"
    )
    assert _ok(client.get(f"{S}/{st['id']}", headers=h))["snapshot"]["hash"] == old["hash"]


# A34 (7.6 A07): tenant letters from the statement snapshot ------------------------------

LETTER_BUCKET = "mhvp-statement-letters"


def _letter_settings(database: Database, redis_url: str) -> Any:
    from pydantic import SecretStr

    return _settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=LETTER_BUCKET,
        document_max_bytes=2_000_000,
    )


@pytest.fixture
def letter_clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    import boto3
    from moto import mock_aws

    settings = _letter_settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=LETTER_BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
        ):
            yield closed, open_


async def _foreign_tenant(settings: Any, world: World) -> None:
    """Second tenant with an admin for the tenant separation check (World.tenant_b)."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        b, _ = await services.provision_tenant(factory, slug=f"bk17f-{RUN}", name=f"Fremd {RUN}")
        uid = await services.create_user(
            factory, email=world.email("m17other"), display_name="m17other", password=PASSWORD
        )
        world.users["m17other"] = uid
        await services.add_member(
            factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        world.tenant_b = b
    finally:
        await engine.dispose()


def _tenant_contract(
    c: TestClient, h: dict[str, str], unit: str, last_name: str, start: str
) -> dict[str, Any]:
    """Tenancy whose tenant has a complete postal address (letters need one)."""
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "salutation": "Frau",
                "first_name": "Erika",
                "last_name": last_name,
                "addresses": [
                    {
                        "street": "Rheinpromenade",
                        "house_number": "1",
                        "postal_code": "40789",
                        "city": "Monheim am Rhein",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
        201,
    )
    return cast(
        dict[str, Any],
        _ok(
            c.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": unit,
                    "party_id": party["id"],
                    "start_date": start,
                },
                headers=h,
            ),
            201,
        ),
    )


def test_a07_tenant_letters_from_snapshot(
    letter_clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """A07 (A34): letters per tenant come from the snapshot only. Expected by hand: caretaker
    1.200,00 by living area 50/50 over the full year 2025 -> 600,00 per tenant. Tenant 01 has
    one advance of 700,00 due and paid -> Guthaben 100,00; tenant 02 has no advances ->
    Nachzahlung 600,00. Proposal (costs / 12): 50,00 for both, labelled as proposal. Preview
    per tenant and bundled, filing as draft documents linked to the contract, dispatch refused
    with G3 closed (403) and with G3 open (409, not implemented), foreign tenant sees nothing."""
    import io

    from pypdf import PdfReader

    from tests.integration.test_m6_documents import COMPANY

    client, gated = letter_clients
    h = bearer(login(client, world, "m17admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "778", "name": "Briefhaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(client, h, "Vermieter778", "company")
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
    contracts: dict[str, dict[str, Any]] = {}
    for number, last_name in [("01", f"Guthaben{RUN}"), ("02", f"Nachzahler{RUN}")]:
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
                json={"allocation_key_id": keys["WFL"], "value": "50", "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
        contracts[number] = _tenant_contract(client, h, unit, last_name, "2024-01-01")
    a = contracts["01"]
    _ok(
        client.post(
            f"/api/v1/contracts/{a['id']}/payments",
            json={
                "payment_type_code": "operating_cost_advance",
                "net": "700.00",
                "gross": "700.00",
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
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-01-31"}, headers=h)
    )[0]
    payment = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "debtor_payment",
                "booking_date": "2025-01-05",
                "text": "Zahlung",
                "lines": [
                    {"account_id": bank, "debit": "700.00"},
                    {"account_id": item["account_id"], "credit": "700.00"},
                ],
                "settlements": [{"open_item_id": item["id"], "amount": "700.00"}],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{payment['id']}/post", headers=h))

    st = _ok(
        client.post(
            S,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    # No snapshot yet: no letter (nothing is calculated on the fly).
    assert client.post(f"{S}/{st['id']}/letters/preview", headers=h).status_code == 409
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Hausmeister",
                "amount": "1200.00",
                "allocation_key_id": keys["WFL"],
                "basis": "§ 4 Mietvertrag, Anlage Betriebskosten",
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    by = {r["unit_number"]: r for r in calc["snapshot"]["results"]}
    assert (by["01"]["costs"], by["01"]["balance"]) == ("600.00", "-100.00")
    assert (by["02"]["costs"], by["02"]["balance"]) == ("600.00", "600.00")

    # Preview for one tenant: result and proposal come from the snapshot, marked as draft.
    single = client.post(
        f"{S}/{st['id']}/letters/preview",
        json={"letter_date": "2026-03-02", "contract_id": a["id"]},
        headers=h,
    )
    assert single.status_code == 200, single.text
    assert single.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(single.content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Hausverwaltung Müller GmbH" in text  # letterhead of the tenant
    assert f"Sehr geehrte Frau Guthaben{RUN}" in text
    assert "Guthaben zu Ihren Gunsten in Höhe von 100,00 EUR" in text
    assert "600,00 EUR" in text  # tenant's share of costs
    assert "700,00 EUR" in text  # advances due and paid
    assert "50,00 EUR" in text  # proposal: 600,00 / 12
    assert "Vorschlag" in text
    assert "Entwurf" in text
    assert "02.03.2026" in text
    assert "Nachzahler" not in text  # single letter, one tenant only

    # Bundled preview: all tenants in unit order in one PDF.
    bundle = client.post(f"{S}/{st['id']}/letters/preview", headers=h)
    assert bundle.status_code == 200, bundle.text
    pages = PdfReader(io.BytesIO(bundle.content)).pages
    assert len(pages) >= 2
    bundle_text = "\n".join(page.extract_text() for page in pages)
    assert f"Guthaben{RUN}" in bundle_text
    assert f"Nachzahler{RUN}" in bundle_text
    assert "Nachzahlung zu Ihren Lasten in Höhe von 600,00 EUR" in bundle_text
    assert bundle_text.index(f"Guthaben{RUN}") < bundle_text.index(f"Nachzahler{RUN}")

    # Filing: one draft document per tenant, linked to the contract; status unchanged.
    stored = _ok(client.post(f"{S}/{st['id']}/letters", headers=h), 201)
    assert stored["status"] == "calculated"
    assert stored["hinweis"] == "Entwurf, kein Versand"
    assert [x["unit_number"] for x in stored["letters"]] == ["01", "02"]
    by_unit = {x["unit_number"]: x for x in stored["letters"]}
    assert (by_unit["01"]["result"], by_unit["01"]["balance"]) == ("guthaben", "-100.00")
    assert (by_unit["02"]["result"], by_unit["02"]["balance"]) == ("nachzahlung", "600.00")
    assert by_unit["01"]["advance_proposal"] == "50.00"
    assert by_unit["02"]["advance_proposal"] == "50.00"
    for x in stored["letters"]:
        document = _ok(client.get(f"/api/v1/documents/{x['document_id']}", headers=h))
        assert document["mime_type"] == "application/pdf"
        assert "Entwurf" in document["title"]
        linked = {(link["entity_type"], link["entity_id"]) for link in document["links"]}
        assert ("contract", x["contract_id"]) in linked

    # Dispatch stays locked: G3 closed -> gate (403); G3 open -> still refused (409).
    closed = client.post(f"{S}/{st['id']}/letters/send", headers=h)
    assert closed.status_code == 403
    gh = bearer(login(gated, world, "m17admin"))
    opened = gated.post(f"{S}/{st['id']}/letters/send", headers=gh)
    assert opened.status_code == 409
    assert opened.json()["locked"] == "statement_letters_send"

    # Tenant separation: a user of another tenant neither previews nor files anything.
    asyncio.run(_foreign_tenant(_letter_settings(database, redis_url), world))
    other = bearer(login(client, world, "m17other"))
    assert client.post(f"{S}/{st['id']}/letters/preview", headers=other).status_code == 404
    assert client.post(f"{S}/{st['id']}/letters", headers=other).status_code == 404
    assert (
        client.get(f"/api/v1/documents/{stored['letters'][0]['document_id']}", headers=other)
    ).status_code == 404
