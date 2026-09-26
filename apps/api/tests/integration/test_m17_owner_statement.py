"""M17 owner statement (7.6 A06, task A25): drafts from the posted ledger; PDF needs G3.

Rental (year 2025, one tenancy): posted rent 500,00 and advance 100,00 for January and
February -> income rent 1.000,00, advances 200,00; January paid 600,00 -> open receivables at
31.12.2025 = 600,00; expense 150,00; payout to the owner 300,00; deposit 1.500,00 recorded
and booked on the deposit bank account; fee setting 25,00 net per month plus 19 % ->
300,00 / 57,00 / 357,00 for 12 months. Bank: 600 - 150 - 300 + 1.500 = 1.650,00; free
liquidity = 1.650,00 - 1.500,00 - 0 = 150,00; operating result 1.200,00 - 150,00 - 357,00 =
693,00.
SEV (WEG with SEV, 2025): unit 01 owner with SEV, Hausgeld resolved and paid 1.200,00, WEG
costs 3.000,00 by MEA 500/500 -> cost share 1.500,00, Abrechnungsspitze 300,00; tenancy on
unit 01 with rent 400,00 and advance 100,00 (January); operating cost statement with 900,00
external amount for the tenant -> owner burden 1.500,00 - 900,00 = 600,00.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
O = "/api/v1/billing/owner-statements"  # noqa: E741
S = "/api/v1/statements"
H = "/api/v1/hoa"


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
        a, _ = await services.provision_tenant(factory, slug=f"ea17-{RUN}", name=f"EA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ea17b-{RUN}", name=f"EAB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ea17admin", a, "tenant_admin"),
            ("ea17acc", a, "accountant_no_banking"),
            ("ea17clerk", a, "clerk_no_accounting"),
            ("ea17badmin", b, "tenant_admin"),
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


def _unit(c: TestClient, h: dict[str, str], prop: str, number: str) -> str:
    building = _ok(
        c.post(f"/api/v1/properties/{prop}/buildings", json={"name": f"Haus {number}"}, headers=h),
        201,
    )["id"]
    return str(
        _ok(
            c.post(
                f"/api/v1/properties/{prop}/units",
                json={"building_id": building, "number": number, "unit_type": "apartment"},
                headers=h,
            ),
            201,
        )["id"]
    )


def _payments(c: TestClient, h: dict[str, str], contract: str, pays: dict[str, str]) -> None:
    for code, amount in pays.items():
        _ok(
            c.post(
                f"/api/v1/contracts/{contract}/payments",
                json={
                    "payment_type_code": code,
                    "net": amount,
                    "gross": amount,
                    "valid_from": "2024-01-01",
                },
                headers=h,
            ),
            201,
        )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract}/schedules",
            json={"valid_from": "2024-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )


def _account(
    c: TestClient,
    h: dict[str, str],
    ledger: str,
    number: str,
    name: str,
    cat: str,
    typ: str,
    **kw: Any,
) -> str:
    return str(
        _ok(
            c.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={"number": number, "name": name, "category": cat, "type": typ, **kw},
                headers=h,
            ),
            201,
        )["id"]
    )


def _map(c: TestClient, h: dict[str, str], ledger: str, code: str, account: str) -> None:
    _ok(
        c.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": code, "account_id": account},
            headers=h,
        )
    )


def _post_run(c: TestClient, h: dict[str, str], contract: str, month: str) -> None:
    run = _ok(
        c.post(
            f"{A}/receivable-runs",
            json={"period_month": month, "scope": "contract", "scope_id": contract},
            headers=h,
        ),
        201,
    )
    assert _ok(c.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))["status"] == "posted"


def _entry(
    c: TestClient,
    h: dict[str, str],
    ledger: str,
    kind: str,
    day: str,
    lines: list[dict[str, str]],
    settlements: list[dict[str, str]] | None = None,
) -> None:
    body: dict[str, Any] = {"kind": kind, "booking_date": day, "text": "Test", "lines": lines}
    if settlements:
        body["settlements"] = settlements
    draft = _ok(c.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))


def _pay_open_items(c: TestClient, h: dict[str, str], ledger: str, bank: str, as_of: str) -> None:
    for item in _ok(c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": as_of}, headers=h)):
        _entry(
            c,
            h,
            ledger,
            "debtor_payment",
            as_of,
            [
                {"account_id": bank, "debit": item["remaining"]},
                {"account_id": item["account_id"], "credit": item["remaining"]},
            ],
            [{"open_item_id": item["id"], "amount": item["remaining"]}],
        )


def test_rental_owner_statement(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, gated = clients
    h = bearer(login(client, world, "ea17admin"))
    acc = bearer(login(client, world, "ea17acc"))
    clerk = bearer(login(client, world, "ea17clerk"))
    other = bearer(login(client, world, "ea17badmin"))

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "772", "name": "Miethaus EA", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, owner_contact = _party(client, h, "Vermieter", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    unit = _unit(client, h, prop["id"], "01")
    tenant, _ = _party(client, h, "MieterEA")
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
    _payments(client, h, contract["id"], {"rent": "500.00", "operating_cost_advance": "100.00"})

    ledger = _ok(client.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)[
        "id"
    ]
    rent_acc = _account(client, h, ledger, "060000", "Mieten", "revenue", "income")
    adv_acc = _account(client, h, ledger, "061000", "BK-Vorauszahlungen", "revenue", "income")
    bank = _account(client, h, ledger, "001210", "Mietkonto", "bank", "asset")
    cost = _account(client, h, ledger, "040100", "Hausmeisterkosten", "cost", "expense")
    owner_acc = _account(
        client,
        h,
        ledger,
        "070000",
        "Verrechnung Eigentümer",
        "creditor",
        "liability",
        contact_id=owner_contact["id"],
    )
    deposit_liab = _account(
        client, h, ledger, "001400", "Kautionsverbindlichkeit", "technical", "liability"
    )
    bank_account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "deposit",
                "iban": "DE89370400440532013000",
                "holder": "Vermieter",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    deposit_bank = _account(
        client,
        h,
        ledger,
        "001220",
        "Kautionskonto",
        "bank",
        "asset",
        property_bank_account_id=bank_account,
    )
    _map(client, h, ledger, "rent", rent_acc)
    _map(client, h, ledger, "operating_cost_advance", adv_acc)
    _post_run(client, h, contract["id"], "2025-01-01")
    _pay_open_items(client, h, ledger, bank, "2025-01-31")
    _post_run(client, h, contract["id"], "2025-02-01")  # stays open
    _entry(
        client,
        h,
        ledger,
        "custom",
        "2025-03-10",
        [{"account_id": cost, "debit": "150.00"}, {"account_id": bank, "credit": "150.00"}],
    )
    _entry(
        client,
        h,
        ledger,
        "custom",
        "2025-04-01",
        [{"account_id": owner_acc, "debit": "300.00"}, {"account_id": bank, "credit": "300.00"}],
    )
    _entry(
        client,
        h,
        ledger,
        "custom",
        "2024-01-20",
        [
            {"account_id": deposit_bank, "debit": "1500.00"},
            {"account_id": deposit_liab, "credit": "1500.00"},
        ],
    )
    deposit = _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/deposits",
            json={
                "kind": "cash",
                "amount_due": "1500.00",
                "valid_from": "2024-01-01",
                "property_bank_account_id": bank_account,
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/deposits/{deposit['id']}/movements",
            json={"date": "2024-01-20", "amount": "1500.00", "kind": "payment"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2024-01-01",
                "vat_percent": "19",
                "amounts_per_unit_type": {"apartment": "25.00"},
            },
            headers=h,
        ),
        201,
    )

    # Rights: no accounting permission -> 403; wrong ledger kind is rejected.
    body = {"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"}
    assert client.post(O, json=body, headers=clerk).status_code == 403
    assert client.get(O, headers=clerk).status_code == 403
    assert (
        client.post(
            O,
            json={"ledger_id": ledger, "period_from": "2025-12-31", "period_to": "2025-01-01"},
            headers=h,
        ).status_code
        == 422
    )

    st = _ok(client.post(O, json=body, headers=h), 201)
    assert (st["kind"], st["status"], st["results"]) == ("rental_owner", "draft", None)
    st = _ok(client.post(f"{O}/{st['id']}/calculate", headers=h))
    assert st["status"] == "calculated"
    r = st["results"]
    assert (r["income"]["rent"], r["income"]["advances"], r["income"]["other"]) == (
        "1000.00",
        "200.00",
        "0.00",
    )
    assert r["expenses"]["total"] == "150.00"
    assert r["expenses"]["lines"][0]["account_number"] == "040100"
    assert (r["admin_fee"]["net"], r["admin_fee"]["vat"], r["admin_fee"]["gross"]) == (
        "300.00",
        "57.00",
        "357.00",
    )
    assert r["payouts"]["total"] == "300.00"
    assert r["open_receivables"]["total"] == "600.00"
    assert {i["component"] for i in r["open_receivables"]["items"]} == {
        "rent",
        "operating_cost_advance",
    }
    assert (r["deposits"]["held"], r["deposits"]["bank_segregated"]) == ("1500.00", "1500.00")
    assert (r["liquidity"]["bank_total"], r["liquidity"]["free"]) == ("1650.00", "150.00")
    assert r["operating_result"]["result"] == "693.00"
    assert "sev_reconciliation" not in r
    assert [f for f in st["findings"] if f["level"] == "error"] == []
    assert st["rule_version"] == "A06-owner-statement-v1"
    assert len(st["snapshot_hash"]) == 64

    # Listing and reading; the snapshot is only in the detail.
    listed = _ok(client.get(O, params={"ledger_id": ledger}, headers=h))
    assert [x["id"] for x in listed] == [st["id"]]
    assert "results" not in listed[0]
    assert _ok(client.get(f"{O}/{st['id']}", headers=h))["snapshot_hash"] == st["snapshot_hash"]

    # Tenant separation: the other tenant sees nothing.
    assert client.get(f"{O}/{st['id']}", headers=other).status_code == 404
    assert _ok(client.get(O, headers=other)) == []
    assert client.post(f"{O}/{st['id']}/calculate", headers=other).status_code == 404

    # Four eyes on the internal approval; recalculation only before approval.
    assert client.post(f"{O}/{st['id']}/approve", headers=h).status_code == 403
    assert client.post(f"{O}/{st['id']}/approve", headers=clerk).status_code == 403
    pdf_early = client.get(f"{O}/{st['id']}/pdf", headers=h)
    assert pdf_early.status_code == 403  # G3 closed, checked before anything else
    assert pdf_early.json()["code"] == "MHVP-GATE-0001"
    approved = _ok(client.post(f"{O}/{st['id']}/approve", headers=acc))
    assert approved["status"] == "internally_approved"
    assert approved["approved_by"] == str(world.users["ea17acc"])
    assert client.post(f"{O}/{st['id']}/calculate", headers=h).status_code == 409

    # Output: G3 closed -> 403 MHVP-GATE-0001; open -> PDF.
    closed = client.get(f"{O}/{st['id']}/pdf", headers=h)
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    h_open = bearer(login(gated, world, "ea17admin"))
    pdf = gated.get(f"{O}/{st['id']}/pdf", headers=h_open)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")


def test_sev_owner_statement_with_reconciliation(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "ea17admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "773", "name": "WEG mit SEV EA", "management_type": "hoa_with_sev"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    owners = {}
    for number, sev in [("01", True), ("02", False)]:
        unit = _unit(client, h, prop["id"], number)
        _ok(
            client.post(
                f"/api/v1/units/{unit}/allocation-values",
                json={"allocation_key_id": keys["MEA"], "value": "500", "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
        party, _ = _party(client, h, f"EigentuemerEA{number}")
        body: dict[str, Any] = {
            "kind": "ownership",
            "unit_id": unit,
            "party_id": party,
            "start_date": "2020-01-01",
            "title_transfer_date": "2020-01-01",
            "acquisition_kind": "first_acquisition",
        }
        if sev:
            body |= {"sev_enabled": True, "sev_fee_debtor_party_id": party}
        contract = _ok(client.post("/api/v1/contracts", json=body, headers=h), 201)
        _payments(client, h, contract["id"], {"hoa_fee": "1200.00"})
        owners[number] = (unit, party, contract)

    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    hoa_ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{hoa_ledger}/accounts", headers=h))
    }
    _map(client, h, hoa_ledger, "hoa_fee", acc["060100"])
    for _, _, contract in owners.values():
        _post_run(client, h, contract["id"], "2025-01-01")
    _pay_open_items(client, h, hoa_ledger, acc["001200"], "2025-01-31")
    hoa_st = _ok(
        client.post(
            f"{H}/statements",
            json={"ledger_id": hoa_ledger, "year": 2025, "reserve_opening": "0.00"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/statements/{hoa_st['id']}/costs",
            json={
                "label": "Bewirtschaftungskosten",
                "amount": "3000.00",
                "allocation_key_id": keys["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
                "account_id": acc["043000"],
            },
            headers=h,
        ),
        201,
    )
    hoa_calc = _ok(client.post(f"{H}/statements/{hoa_st['id']}/calculate", headers=h))
    unit01 = next(u for u in hoa_calc["snapshot"]["units"] if u["unit_number"] == "01")
    assert (unit01["cost_share"], unit01["result"]) == ("1500.00", "300.00")

    # Tenancy on unit 01: the creditor is the SEV owner's legal entity.
    unit, party, _ = owners["01"]
    tenant, _ = _party(client, h, "MieterSEV")
    tenancy = _ok(
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
    sev_entity = tenancy["legal_entity_id"]
    assert sev_entity != hoa
    _payments(client, h, tenancy["id"], {"rent": "400.00", "operating_cost_advance": "100.00"})
    ledger = _ok(client.post(f"{A}/ledgers", json={"legal_entity_id": sev_entity}, headers=h), 201)[
        "id"
    ]
    rent_acc = _account(client, h, ledger, "060000", "Mieten", "revenue", "income")
    adv_acc = _account(client, h, ledger, "061000", "BK-Vorauszahlungen", "revenue", "income")
    bank = _account(client, h, ledger, "001210", "Mietkonto SEV", "bank", "asset")
    _map(client, h, ledger, "rent", rent_acc)
    _map(client, h, ledger, "operating_cost_advance", adv_acc)
    _post_run(client, h, tenancy["id"], "2025-01-01")
    _pay_open_items(client, h, ledger, bank, "2025-01-31")

    # Operating cost statement of the tenancy (external amount, no template key: M17-01).
    bk = _ok(
        client.post(
            S,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    occ = _ok(client.get(f"{S}/{bk['id']}/occupants", headers=h))
    tenant_key = next(o["key"] for o in occ if o["contract_id"] == tenancy["id"])
    _ok(
        client.post(
            f"{S}/{bk['id']}/cost-items",
            json={
                "label": "Umlagefähige Kosten laut WEG-Abrechnung",
                "amount": "900.00",
                "external_amounts": {tenant_key: "900.00"},
                "basis": "§ 2 Mietvertrag, Betriebskostenkatalog",
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{S}/{bk['id']}/calculate", headers=h))

    st = _ok(
        client.post(
            O,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    assert st["kind"] == "sev_owner"
    st = _ok(client.post(f"{O}/{st['id']}/calculate", headers=h))
    r = st["results"]
    assert (r["income"]["rent"], r["income"]["advances"]) == ("400.00", "100.00")
    assert r["liquidity"]["free"] == "500.00"
    sev = r["sev_reconciliation"]
    assert sev["hoa_statement"]["statement_id"] == hoa_st["id"]
    assert [u["unit_number"] for u in sev["units"]] == ["01"]  # never the other owner's unit
    assert (sev["hoa_cost_share"], sev["hausgeld_resolved"], sev["hausgeld_paid"]) == (
        "1500.00",
        "1200.00",
        "1200.00",
    )
    assert sev["hoa_result"] == "300.00"
    assert sev["operating_cost_statements"][0]["statement_id"] == bk["id"]
    assert (sev["tenant_allocable_costs"], sev["owner_burden"]) == ("900.00", "600.00")
    codes = {f["code"]: f["level"] for f in st["findings"]}
    assert "error" not in codes.values()
    assert codes.get("FEE-NOT-CONFIGURED") == "info"  # no fee setting for this SEV owner
