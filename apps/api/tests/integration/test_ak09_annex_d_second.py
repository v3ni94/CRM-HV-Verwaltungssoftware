"""AK09 (GAI-612, rule 0.1.8): second independent tests for the annex D cases D01 to D25 that
were named by a single test only (SINGLE_TEST_CASES in tests/unit/test_aj19_test_guards.py).

Each test has its own expected values computed by hand in the docstring before the run; no
value is taken from an observed result. The tests use their own world (tenant slug and user
names with the prefix ``ak09``) and vary the inputs or the path compared with the first test
of the case, so a shared error in a helper does not hide behind two identical scenarios.
"""

import asyncio
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.billing.calc import co2_split, deadline
from mhvp.billing.deadline import state_of
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
H = "/api/v1/hoa"
S = "/api/v1/statements"
USERS = ("ak09admin", "ak09second")


class OpenGates:
    """Opens G1, G3 and G4 for the second client; G2 and G5 stay closed."""

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G3, ReleaseGate.G4)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"ak09-{RUN}", name=f"AK09 Anhang D {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in USERS:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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
        TestClient(create_app(settings, release_gate_resolver=OpenGates())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


# D10 and D23: pure rule functions ------------------------------------------------------------


@pytest.mark.annex_d("D10")
def test_ak09_co2_step_boundary_without_early_rounding() -> None:
    """D10 second test, other costs than the first one: CO2 costs 250,00 EUR.
    12,0 kg/m2/a -> step 12 to under 17 -> tenant 90 %: 250,00 * 0,90 = 225,00, landlord 25,00.
    11,99 (comparison value under 12) -> tenant 100 %: 250,00 / 0,00.
    16,99 still step 12 to under 17 -> 225,00 / 25,00; 17,0 -> 80 %: 200,00 / 50,00.
    The input is not rounded first: 11,995 stays below 12 -> 100 % (rounding to 12,0 would
    give the landlord 25,00 more burden, which the case forbids as early rounding).
    Sum check: tenant + landlord = 250,00 in every row."""
    costs = Decimal("250.00")
    expected = {
        "12.0": (90, "225.00", "25.00"),
        "11.99": (100, "250.00", "0.00"),
        "11.995": (100, "250.00", "0.00"),
        "16.99": (90, "225.00", "25.00"),
        "17.0": (80, "200.00", "50.00"),
    }
    for value, (percent, tenant, landlord) in expected.items():
        out = co2_split(Decimal(value), costs)
        assert out["tenant_percent"] == percent, value
        assert out["tenant"] == Decimal(tenant), value
        assert out["landlord"] == Decimal(landlord), value
        assert Decimal(str(out["tenant"])) + Decimal(str(out["landlord"])) == costs
    with pytest.raises(ValueError, match="nicht negativ"):
        co2_split(Decimal("-0.1"), costs)


@pytest.mark.annex_d("D23")
def test_ak09_deadline_counts_access_not_creation() -> None:
    """D23 second test on the rule functions. Period 01.01.2025 to 31.12.2025 -> orientation
    end of the twelfth month after the period: 31.12.2026. Period ending 29.02.2024 -> 28.02.2025
    (no 29.02 in 2025).
    Statement created on 28.12.2026, not yet delivered: state on 28.12.2026 with 14 warning days
    is "warning" (3 days left), not delivered; on 02.01.2027 still undelivered -> "expired"
    (creation before the deadline does not count). Access on 30.12.2026 -> "delivered_in_time";
    access on 04.01.2027 -> "delivered_late"."""
    end = deadline(date(2025, 12, 31))
    assert end == date(2026, 12, 31)
    assert deadline(date(2024, 2, 29)) == date(2025, 2, 28)
    assert state_of(end, None, date(2026, 12, 28), 14) == "warning"
    assert state_of(end, None, date(2026, 10, 1), 14) == "open"
    assert state_of(end, None, date(2027, 1, 2), 14) == "expired"
    assert state_of(end, date(2026, 12, 30), date(2027, 1, 2), 14) == "delivered_in_time"
    assert state_of(end, date(2027, 1, 4), date(2027, 1, 4), 14) == "delivered_late"


# D21 and D22: rental statements --------------------------------------------------------------


def _property(client: TestClient, h: dict[str, str], number: str, kind: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AK09 Objekt {number}", "management_type": kind},
            headers=h,
        ),
        201,
    )


def _keys(client: TestClient, h: dict[str, str], prop: str) -> dict[str, str]:
    rows = _ok(client.get(f"/api/v1/properties/{prop}/allocation-keys", headers=h))
    return {k["code"]: k["id"] for k in rows}


def _unit(client: TestClient, h: dict[str, str], prop: str, building: str, number: str) -> str:
    return str(
        _ok(
            client.post(
                f"/api/v1/properties/{prop}/units",
                json={"building_id": building, "number": number, "unit_type": "apartment"},
                headers=h,
            ),
            201,
        )["id"]
    )


def _value(client: TestClient, h: dict[str, str], unit: str, key: str, value: str) -> None:
    _ok(
        client.post(
            f"/api/v1/units/{unit}/allocation-values",
            json={"allocation_key_id": key, "value": value, "valid_from": "2019-01-01"},
            headers=h,
        ),
        201,
    )


def _rent_statement(client: TestClient, h: dict[str, str], ledger: str) -> str:
    body = {"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"}
    return str(_ok(client.post(S, json=body, headers=h), 201)["id"])


def _calc(
    client: TestClient, h: dict[str, str], ledger: str, item: dict[str, Any]
) -> tuple[int, Any]:
    st = _rent_statement(client, h, ledger)
    _ok(client.post(f"{S}/{st}/cost-items", json=item, headers=h), 201)
    response = client.post(f"{S}/{st}/calculate", headers=h)
    return response.status_code, response.json()


@pytest.mark.annex_d("D21")
def test_ak09_let_condominium_single_owner_uses_recorded_weg_key(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D21 second test: one SEV owner holds both units of a let condominium, 01 with 200 and
    02 with 100 co-ownership shares (declaration of division), living area 50 m2 each.
    Garden cost 900,00 EUR without a deviating rental agreement on the key.
    Living area (template key WFL) would give 900 * 50 / 100 = 450,00 / 450,00; it must be
    refused as automatic m2 rule (message names 556a and WFL).
    Recorded WEG key: 900 * 200 / 300 = 600,00 for 01 and 900 * 100 / 300 = 300,00 for 02,
    sum 900,00 (whole year for both tenancies, no day weighting effect)."""
    client, _ = clients
    h = bearer(login(client, world, "ak09admin"))
    prop = _property(client, h, "921", "hoa_with_sev")
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    keys = _keys(client, h, prop["id"])
    owner = _party(client, h, "AK09SEVEigentuemer")[0]
    units: dict[str, str] = {}
    entities = set()
    for number in ("01", "02"):
        units[number] = _unit(client, h, prop["id"], building, number)
        _value(client, h, units[number], keys["WFL"], "50")
        _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "ownership",
                    "unit_id": units[number],
                    "party_id": owner,
                    "start_date": "2020-01-01",
                    "title_transfer_date": "2020-01-01",
                    "acquisition_kind": "first_acquisition",
                    "sev_enabled": True,
                },
                headers=h,
            ),
            201,
        )
        tenant = _party(client, h, f"AK09SEVMieter{number}")[0]
        entities.add(
            _ok(
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
            )["legal_entity_id"]
        )
    assert len(entities) == 1
    ledger = _ok(
        client.post(f"{A}/ledgers", json={"legal_entity_id": entities.pop()}, headers=h), 201
    )["id"]
    status, body = _calc(
        client,
        h,
        ledger,
        {
            "label": "Gartenpflege",
            "amount": "900.00",
            "allocation_key_id": keys["WFL"],
            "basis": "§ 4 Mietvertrag, keine abweichende Vereinbarung zum Schlüssel",
        },
    )
    assert status == 422
    assert "556a" in str(body["detail"])
    assert "WFL" in str(body["detail"])

    mea = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/allocation-keys",
            json={
                "code": "MEA_AK09",
                "name": "Miteigentumsanteile laut Teilungserklärung vom 01.01.2019",
                "unit_of_measure": "MEA",
                "kind": "static",
            },
            headers=h,
        ),
        201,
    )["id"]
    _value(client, h, units["01"], mea, "200")
    _value(client, h, units["02"], mea, "100")
    status, body = _calc(
        client,
        h,
        ledger,
        {
            "label": "Gartenpflege",
            "amount": "900.00",
            "allocation_key_id": mea,
            "basis": "§ 4 Mietvertrag; WEG-Verteilungsmaßstab laut Teilungserklärung "
            "vom 01.01.2019 (§ 556a Abs. 3 BGB)",
        },
    )
    assert status == 200, body
    by = {r["unit_number"]: r["costs"] for r in body["snapshot"]["results"]}
    assert by == {"01": "600.00", "02": "300.00"}


@pytest.mark.annex_d("D22")
def test_ak09_mixed_invoice_management_share_stays_out(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D22 second test with a management share instead of a repair share: invoice 600,00 EUR,
    of which caretaker 450,00 (allocable) and administration 150,00 (not allocable), posted
    split. Expected: 600,00 on the caretaker account is refused (exceeds the posted 450,00),
    150,00 on the administration account is refused (not allocable); 450,00 on the caretaker
    account reach the single tenant (one unit, whole year): costs 450,00, total 450,00,
    i.e. 600,00 - 150,00."""
    client, _ = clients
    h = bearer(login(client, world, "ak09admin"))
    prop = _property(client, h, "922", "rental")
    owner = _party(client, h, "AK09Vermieter", "company")[0]
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    keys = _keys(client, h, prop["id"])
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _unit(client, h, prop["id"], building, "01")
    _value(client, h, unit, keys["WFL"], "70")
    tenant = _party(client, h, "AK09Mieter")[0]
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

    def account(number: str, name: str, **extra: Any) -> str:
        body = {"number": number, "name": name, "category": "cost", "type": "expense", **extra}
        return str(
            _ok(client.post(f"{A}/ledgers/{ledger}/accounts", json=body, headers=h), 201)["id"]
        )

    caretaker = account("042100", "Hausmeister AK09", allocation_category="allocable_other")
    admin = account("045100", "Verwaltung AK09", allocation_category="non_allocable_other")
    bank = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={"number": "001290", "name": "Mietkonto", "category": "bank", "type": "asset"},
            headers=h,
        ),
        201,
    )["id"]
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "custom",
                "booking_date": "2025-04-01",
                "text": "Rechnung Hausmeister mit Verwaltungsanteil",
                "lines": [
                    {"account_id": caretaker, "debit": "450.00"},
                    {"account_id": admin, "debit": "150.00"},
                    {"account_id": bank, "credit": "600.00"},
                ],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    base = {"allocation_key_id": keys["WFL"], "basis": "§ 4 Mietvertrag, Nr. 14 BetrKV"}
    status, body = _calc(
        client,
        h,
        ledger,
        {"label": "Hausmeister", "amount": "600.00", "account_id": caretaker, **base},
    )
    assert status == 422
    assert "450.00" in str(body["detail"])
    status, body = _calc(
        client, h, ledger, {"label": "Verwaltung", "amount": "150.00", "account_id": admin, **base}
    )
    assert status == 422
    assert "nicht umlagefähig" in str(body["detail"])
    status, body = _calc(
        client,
        h,
        ledger,
        {"label": "Hausmeister", "amount": "450.00", "account_id": caretaker, **base},
    )
    assert status == 200, body
    assert body["snapshot"]["results"][0]["costs"] == "450.00"
    assert body["snapshot"]["total"] == "450.00"


# D01, D02 and D03: WEG statement with monthly advances ---------------------------------------


@pytest.mark.annex_d("D01", "D02", "D03", "D13", "D19")
def test_ak09_hoa_statement_monthly_advances_and_reserve(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """Second test of D01 to D03, other path than the first one: the advances are four monthly
    receivable runs (January to April 2025) instead of one posted month, the costs are two items
    instead of one, and the payments are partial per month.
    MEA 3.000 (unit 01) / 2.500 (unit 02), total 5.500.
    Costs 2.200,00 + 3.300,00 = 5.500,00. Item 1: 2.200 * 3.000 / 5.500 = 1.200,00 and
    2.200 * 2.500 / 5.500 = 1.000,00; item 2: 3.300 * 3.000 / 5.500 = 1.800,00 and 1.500,00.
    Cost share 01: 3.000,00; 02: 2.500,00.
    hoa_fee 700,00 per month for both units, four runs: resolved 2.800,00 each. Payments per
    month 700, 700, 700, 400 = 2.500,00 each.
    D01 unit 01: result 3.000 - 2.800 = 200,00, arrears 2.800 - 2.500 = 300,00, information 500,00.
    D02 unit 02: result 2.500 - 2.800 = -300,00, arrears 300,00, information 0,00.
    D03 reserve unit 01 1.500,00 per month (resolved 6.000,00), paid 1.500 in January to March and
    nothing in April = 4.500,00. Opening 20.000 + 4.500 - 3.000 + 100 = 21.600,00, open
    contributions 1.500,00 (not 23.100,00).
    D19 on the same data: the reserve payments went to the reserve bank account 001201, so the
    bank shows 3 * 1.500 = 4.500,00 against the accounting closing 21.600,00; difference
    4.500 - 21.600 = -17.100,00 is explained in the snapshot and the calculation writes no
    journal entry (entry count unchanged).
    D13 on the same data: internally approved by the second person, no resolution recorded.
    With G4 open the result posting is refused (409) and "resolved" without a resolution is
    refused (422); no open item of 200,00 (result of 01) exists, the open hoa_fee items are the
    arrears 300,00 per unit only, and the direct debit preview lists no result amount."""
    from tests.integration.test_m5_contracts import _unit as unit_of

    client, gated = clients
    h = bearer(login(client, world, "ak09admin"))
    prop = _property(client, h, "901", "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = _keys(client, h, prop["id"])
    contracts: dict[str, str] = {}
    for number, mea, pays in (
        ("01", "3000", {"hoa_fee": "700.00", "reserve": "1500.00"}),
        ("02", "2500", {"hoa_fee": "700.00"}),
    ):
        unit = unit_of(client, h, prop["id"], number)
        _value(client, h, unit, keys["MEA"], mea)
        party = _party(client, h, f"AK09WEGEigentuemer{number}")[0]
        contract = _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "ownership",
                    "unit_id": unit,
                    "party_id": party,
                    "start_date": "2020-01-01",
                    "title_transfer_date": "2020-01-01",
                    "acquisition_kind": "first_acquisition",
                },
                headers=h,
            ),
            201,
        )["id"]
        contracts[contract] = number
        for code, amount in pays.items():
            _ok(
                client.post(
                    f"/api/v1/contracts/{contract}/payments",
                    json={
                        "payment_type_code": code,
                        "net": amount,
                        "gross": amount,
                        "valid_from": "2020-01-01",
                    },
                    headers=h,
                ),
                201,
            )
        _ok(
            client.post(
                f"/api/v1/contracts/{contract}/schedules",
                json={"valid_from": "2020-01-01", "due_day": 3},
                headers=h,
            ),
            201,
        )
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, number in (("hoa_fee", "060100"), ("reserve", "060200")):
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    for month in ("2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"):
        for contract in contracts:
            run = _ok(
                client.post(
                    f"{A}/receivable-runs",
                    json={"period_month": month, "scope": "contract", "scope_id": contract},
                    headers=h,
                ),
                201,
            )
            _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-04-30"}, headers=h)
    )
    assert len(items) == 12  # 4 months x (2 hoa_fee + 1 reserve)
    for item in items:
        april = str(item["due_date"]).startswith("2025-04")
        reserve = item["account_id"] == acc["060200"] or item["remaining"] == "1500.00"
        if reserve:
            pay, bank = ("0.00" if april else "1500.00"), acc["001201"]
        else:
            pay, bank = ("400.00" if april else "700.00"), acc["001200"]
        if pay == "0.00":
            continue
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "debtor_payment",
                    "booking_date": "2025-05-05",
                    "text": "Zahlung AK09",
                    "lines": [
                        {"account_id": bank, "debit": pay},
                        {"account_id": item["account_id"], "credit": pay},
                    ],
                    "settlements": [{"open_item_id": item["id"], "amount": pay}],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    for amount, day in (("2200.00", "2025-03-01"), ("3300.00", "2025-06-01")):
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "custom",
                    "booking_date": day,
                    "text": "Bewirtschaftungskosten AK09",
                    "lines": [
                        {"account_id": acc["043000"], "debit": amount},
                        {"account_id": acc["001200"], "credit": amount},
                    ],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    st = _ok(
        client.post(
            f"{H}/statements",
            json={
                "ledger_id": ledger,
                "year": 2025,
                "reserve_opening": "20000.00",
                "reserve_withdrawals": "3000.00",
                "reserve_interest": "100.00",
            },
            headers=h,
        ),
        201,
    )
    for label, amount in (("Hausreinigung", "2200.00"), ("Hausmeister", "3300.00")):
        _ok(
            client.post(
                f"{H}/statements/{st['id']}/costs",
                json={
                    "label": label,
                    "amount": amount,
                    "allocation_key_id": keys["MEA"],
                    "basis": "Teilungserklärung, Verteilung nach MEA",
                    "account_id": acc["043000"],
                },
                headers=h,
            ),
            201,
        )
    before = len(_ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h)))
    snap = _ok(client.post(f"{H}/statements/{st['id']}/calculate", headers=h))["snapshot"]
    assert len(_ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h))) == before
    by = {u["unit_number"]: u for u in snap["units"]}
    splits = {p["label"]: sorted(p["split"].values()) for p in snap["positions"]}
    assert splits == {
        "Hausreinigung": ["1000.00", "1200.00"],
        "Hausmeister": ["1500.00", "1800.00"],
    }
    one, two = by["01"], by["02"]
    assert (one["cost_share"], one["advances_resolved"], one["advances_paid"]) == (
        "3000.00",
        "2800.00",
        "2500.00",
    )
    assert (one["result"], one["arrears"], one["information_total"]) == (
        "200.00",
        "300.00",
        "500.00",
    )
    assert (two["cost_share"], two["advances_resolved"], two["advances_paid"]) == (
        "2500.00",
        "2800.00",
        "2500.00",
    )
    assert (two["result"], two["arrears"], two["information_total"]) == (
        "-300.00",
        "300.00",
        "0.00",
    )
    reserve = snap["reserve"]
    assert reserve["contributions_resolved"] == "6000.00"
    assert reserve["contributions_paid"] == "4500.00"
    assert reserve["contributions_open"] == "1500.00"
    assert reserve["closing"] == "21600.00"
    assert (reserve["bank_balance"], reserve["bank_difference"]) == ("4500.00", "-17100.00")
    assert "keine Ausgleichsbuchung" in reserve["bank_difference_note"]
    assert (one["reserve_due"], one["reserve_paid"]) == ("6000.00", "4500.00")
    # D02: the credit result is not paid out and the arrears are not cleared by the calculation.
    open_after = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-12-31"}, headers=h)
    )
    rest = {
        contracts[str(i["contract_id"])]: Decimal(i["remaining"])
        for i in open_after
        if i["account_id"] != acc["060200"] and i["remaining"] == "300.00"
    }
    assert rest == {"01": Decimal("300.00"), "02": Decimal("300.00")}
    # D13: internally approved, no resolution -> no result claim, no direct debit of it.
    sid = st["id"]
    h2 = bearer(login(client, world, "ak09second"))
    _ok(
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    no_res = client.post(f"{H}/statements/{sid}/transition", json={"target": "resolved"}, headers=h)
    assert no_res.status_code == 422, no_res.text
    gh = bearer(login(gated, world, "ak09admin"))
    refused = gated.post(f"{H}/statements/{sid}/post", headers=gh)
    assert refused.status_code == 409, refused.text
    current = _ok(client.get(f"{H}/statements/{sid}", headers=h))
    assert (current["status"], current["resolution_id"]) == ("internally_approved", None)
    assert not current["posted_entry_ids"]
    after = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h)
    )
    assert "200.00" not in {i["amount"] for i in after}
    assert "200.00" not in {i["remaining"] for i in after}
    _ok(
        client.put(
            f"{A}/direct-debits/creditor-ids/legal-entities/{hoa}",
            json={"sepa_creditor_id": "DE98ZZZ09999999999"},
            headers=h,
        )
    )
    preview = _ok(
        client.post(
            f"{A}/direct-debits/preview",
            json={"ledger_id": ledger, "collection_date": "2026-12-31", "lead_days": 0},
            headers=h,
        )
    )
    assert "200.00" not in {c["amount"] for c in preview["items"]}
    assert {c["open_item_id"] for c in preview["items"]} <= {i["id"] for i in after}


# D07: partial and overpayment on the journal path --------------------------------------------


def _pay(
    client: TestClient,
    h: dict[str, str],
    ledger: str,
    bank: str,
    account: str,
    amount: str,
    settlements: list[dict[str, str]],
) -> Any:
    return client.post(
        f"{A}/ledgers/{ledger}/entries",
        json={
            "kind": "debtor_payment",
            "booking_date": "2025-02-10",
            "text": "Zahlung AK09 D07",
            "lines": [
                {"account_id": bank, "debit": amount},
                {"account_id": account, "credit": amount},
            ],
            "settlements": settlements,
        },
        headers=h,
    )


@pytest.mark.annex_d("D07")
def test_ak09_partial_then_overpayment_by_journal_entries(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D07 second test, without bank import: the receivable comes from a posted receivable run
    (hoa_fee 1.000,00 for January 2025) and both payments are manual debtor payments.
    Payment 1: 600,00 settled -> rest 1.000 - 600 = 400,00.
    Payment 2: 450,00; a settlement of 450,00 exceeds the rest and is refused (422); settled
    400,00 -> item closed, 450 - 400 = 50,00 stay as credit on the debtor account.
    Trial balance: debtor 1.000 - 600 - 450 = -50,00, revenue 060100 -1.000,00 (credit is no
    additional income), bank 001200 +1.050,00; no further entry kind is created."""
    from tests.integration.test_m5_contracts import _unit as unit_of

    client, _ = clients
    h = bearer(login(client, world, "ak09admin"))
    prop = _property(client, h, "907", "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = unit_of(client, h, prop["id"], "01")
    party = _party(client, h, "AK09D07Eigentuemer")[0]
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{contract}/payments",
            json={
                "payment_type_code": "hoa_fee",
                "net": "1000.00",
                "gross": "1000.00",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{contract}/schedules",
            json={"valid_from": "2020-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": acc["060100"]},
            headers=h,
        )
    )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2025-01-01", "scope": "contract", "scope_id": contract},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    (item,) = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-01-31"}, headers=h)
    )
    assert item["remaining"] == "1000.00"
    debtor = item["account_id"]
    bank = acc["001200"]

    def post(response: Any) -> None:
        draft = _ok(response, 201)
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))

    post(
        _pay(
            client,
            h,
            ledger,
            bank,
            debtor,
            "600.00",
            [{"open_item_id": item["id"], "amount": "600.00"}],
        )
    )
    (rest,) = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-02-28"}, headers=h)
    )
    assert rest["remaining"] == "400.00"
    over = _pay(
        client,
        h,
        ledger,
        bank,
        debtor,
        "450.00",
        [{"open_item_id": item["id"], "amount": "450.00"}],
    )
    if over.status_code == 201:  # refused at posting instead of at drafting
        refused = client.post(f"{A}/ledgers/{ledger}/entries/{over.json()['id']}/post", headers=h)
        assert refused.status_code == 422, refused.text
    else:
        assert over.status_code == 422, over.text
    post(
        _pay(
            client,
            h,
            ledger,
            bank,
            debtor,
            "450.00",
            [{"open_item_id": item["id"], "amount": "400.00"}],
        )
    )
    still_open = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-12-31"}, headers=h)
    )
    assert [i for i in still_open if i["id"] == item["id"]] == []
    tb = _ok(
        client.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2025-12-31"}, headers=h)
    )
    numbers = {a["number"]: a for a in tb["accounts"]}
    debtor_number = next(
        a["number"]
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
        if a["id"] == debtor
    )
    debtor_row = numbers[debtor_number]
    assert tb["balanced"] is True
    assert Decimal(debtor_row["balance"]) == Decimal("-50.00")
    assert Decimal(numbers["060100"]["balance"]) == Decimal("-1000.00")
    assert Decimal(numbers["001200"]["balance"]) == Decimal("1050.00")


# D12: partial invoice paid before the final invoice ------------------------------------------


@pytest.mark.annex_d("D12")
def test_ak09_paid_partial_and_final_invoice_with_two_lines(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D12 second test, other path than the first one: the partial invoice is paid before the
    final invoice arrives, and the final invoice carries two lines.
    Partial invoice 2.000,00 net + 380,00 VAT = 2.380,00, posted and paid (creditor payment
    2.380,00) -> no open payable from it.
    Final invoice 5.950,00 gross = line 1 3.000,00 + 570,00 and line 2 2.000,00 + 380,00
    (5.000,00 + 950,00), deducting the partial 2.380,00 -> payable 5.950 - 2.380 = 3.570,00.
    Expense 041400 = 5.950,00 (not 2.380 + 5.950 = 8.330,00); bank 001200 = -2.380,00;
    open payables after both postings: only 3.570,00."""
    from tests.integration.conftest import approve_bank_accounts

    client, _ = clients
    h = bearer(login(client, world, "ak09admin"))
    h2 = bearer(login(client, world, "ak09second"))
    prop = _property(client, h, "912", "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    iban = "DE89370400440532013000"
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"AK09 Dachdecker {RUN} GmbH",
                "bank_accounts": [{"iban": iban, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, h2, provider)

    def review_release_post(invoice: str) -> None:
        for step in ("completeness", "factual", "arithmetic_tax"):
            _ok(
                client.post(
                    f"{A}/invoices/{invoice}/reviews",
                    json={"step": step, "result": "ok", "reason": f"{step} geprüft"},
                    headers=h,
                ),
                201,
            )
        _ok(client.post(f"{A}/invoices/{invoice}/release", headers=h2))
        _ok(client.post(f"{A}/invoices/{invoice}/post", headers=h))

    base = {
        "ledger_id": ledger,
        "provider_contact_id": provider,
        "invoice_date": "2025-03-01",
        "due_date": "2025-03-15",
        "service_from": "2025-02-01",
        "service_to": "2025-02-28",
        "payee_iban": iban,
        "order_reference": "AUF-AK09-D12",
    }
    part = _ok(
        client.post(
            f"{A}/invoices",
            json={
                **base,
                "number": "AK09-AB-1",
                "kind": "partial",
                "net": "2000.00",
                "vat": "380.00",
                "gross": "2380.00",
                "lines": [
                    {
                        "account_id": acc["041400"],
                        "net": "2000.00",
                        "vat_percent": "19",
                        "vat": "380.00",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    review_release_post(part["id"])
    (payable,) = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-03-31"}, headers=h)
    )
    assert payable["remaining"] == "2380.00"
    pay = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "creditor_payment",
                "booking_date": "2025-03-20",
                "text": "Zahlung Abschlag AK09",
                "lines": [
                    {"account_id": payable["account_id"], "debit": "2380.00"},
                    {"account_id": acc["001200"], "credit": "2380.00"},
                ],
                "settlements": [{"open_item_id": payable["id"], "amount": "2380.00"}],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{pay['id']}/post", headers=h))
    assert (
        _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-03-31"}, headers=h
            )
        )
        == []
    )
    final = _ok(
        client.post(
            f"{A}/invoices",
            json={
                **base,
                "number": "AK09-SR-1",
                "kind": "final",
                "invoice_date": "2025-05-02",
                "due_date": "2025-05-16",
                "net": "5000.00",
                "vat": "950.00",
                "gross": "5950.00",
                "deductions": [{"invoice_id": part["id"], "gross": "2380.00"}],
                "lines": [
                    {
                        "account_id": acc["041400"],
                        "net": "3000.00",
                        "vat_percent": "19",
                        "vat": "570.00",
                    },
                    {
                        "account_id": acc["041400"],
                        "net": "2000.00",
                        "vat_percent": "19",
                        "vat": "380.00",
                    },
                ],
            },
            headers=h,
        ),
        201,
    )
    review_release_post(final["id"])
    tb = _ok(
        client.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2025-12-31"}, headers=h)
    )
    by = {a["number"]: Decimal(a["balance"]) for a in tb["accounts"]}
    assert by["041400"] == Decimal("5950.00")
    assert by["001200"] == Decimal("-2380.00")
    remaining = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-12-31"}, headers=h)
    )
    assert [Decimal(i["remaining"]) for i in remaining] == [Decimal("3570.00")]
