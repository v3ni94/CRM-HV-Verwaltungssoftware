"""M5 acceptance: contracts with debtor accounts (D15), versions, payments with periods,
ownership transfer (D16, D17), SEV creditor (6.9.11), SEPA mandates, deposits (D56)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
IBAN = "DE02120300000000202051"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"c-{RUN}", name=f"Verträge {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m5admin", "tenant_admin"), ("m5caretaker", "caretaker")]:
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(c: TestClient, h: dict[str, str], number: str, kind: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"Objekt {number}",
        "management_type": kind,
        "street": "Rheinpromenade",
        "house_number": "13",
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    return _ok(c.post("/api/v1/properties", json=body, headers=h))  # type: ignore[no-any-return]


def _unit(c: TestClient, h: dict[str, str], prop_id: str, number: str) -> str:
    building = _ok(
        c.post(f"/api/v1/properties/{prop_id}/buildings", json={"name": "Haus"}, headers=h)
    )
    unit = _ok(
        c.post(
            f"/api/v1/properties/{prop_id}/units",
            json={
                "building_id": building["id"],
                "number": number,
                "label": f"WE {number}",
                "unit_type": "apartment",
            },
            headers=h,
        )
    )
    return str(unit["id"])


def _party(
    c: TestClient, h: dict[str, str], name: str, kind: str = "person", iban: str | None = None
) -> tuple[str, dict[str, Any]]:
    contact: dict[str, Any] = (
        {"kind": "company", "company_name": f"{name} {RUN} GmbH"}
        if kind == "company"
        else {"kind": "person", "first_name": name, "last_name": f"Test{RUN}"}
    )
    if iban:
        contact["bank_accounts"] = [{"iban": iban, "valid_from": "2020-01-01"}]
    created = _ok(c.post("/api/v1/contacts", json=contact, headers=h))
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": created["id"]}]}, headers=h)
    )
    return str(party["id"]), created


def _payment(net: str, gross: str, valid_from: str, code: str = "rent", vat: str = "0") -> Any:
    return {
        "payment_type_code": code,
        "net": net,
        "vat_percent": vat,
        "gross": gross,
        "valid_from": valid_from,
    }


def test_rental_tenancy_lifecycle(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m5admin"))
    prop = _property(client, h, "501", "rental")
    unit = _unit(client, h, prop["id"], "01")
    tenant, _ = _party(client, h, "Mieter")
    tenancy = {"kind": "tenancy", "unit_id": unit, "party_id": tenant, "start_date": "2026-01-01"}
    no_owner = client.post("/api/v1/contracts", json=tenancy, headers=h)
    assert no_owner.status_code == 422

    owner, _ = _party(client, h, "Eigentuemer", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
    )["legal_entity_id"]
    contract = _ok(client.post("/api/v1/contracts", json=tenancy, headers=h))
    assert contract["legal_entity_id"] == entity
    assert len(contract["number"]) == 6
    assert contract["number"].isdigit()
    assert contract["version"] == 1
    assert contract["debtor_account"]["number"] == "090000"
    assert contract["debtor_account"]["name"].startswith("WE 01 ")
    overlap = client.post(
        "/api/v1/contracts", json={**tenancy, "start_date": "2026-06-01"}, headers=h
    )
    assert overlap.status_code == 409

    cid = contract["id"]
    pay = f"/api/v1/contracts/{cid}/payments"
    _ok(client.post(pay, json=_payment("800.00", "800.00", "2026-01-01"), headers=h))
    _ok(
        client.post(
            pay,
            json=_payment("150.00", "150.00", "2026-01-01", "operating_cost_advance"),
            headers=h,
        )
    )
    assert (
        client.post(
            pay, json=_payment("100.00", "119.50", "2026-01-01", vat="19"), headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(pay, json=_payment("-50.00", "-50.00", "2026-03-01"), headers=h).status_code
        == 422
    )
    assert (
        client.post(
            pay, json=_payment("1.00", "1.00", "2026-03-01", "unknown"), headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(pay, json=_payment("1.00", "1.00", "2025-12-01"), headers=h).status_code == 422
    )
    _ok(
        client.post(
            pay, json=_payment("-50.00", "-50.00", "2026-03-01", "rent_reduction"), headers=h
        )
    )
    _ok(client.post(pay, json=_payment("850.00", "850.00", "2027-01-01"), headers=h))
    _ok(
        client.post(
            f"/api/v1/contracts/{cid}/schedules",
            json={"valid_from": "2026-01-01", "due_day": 3},
            headers=h,
        )
    )

    bad_version = client.post(
        f"/api/v1/contracts/{cid}/versions",
        json={"effective_date": "2026-07-01", "dunning_block": True},
        headers=h,
    )
    assert bad_version.status_code == 422
    v2 = _ok(
        client.post(
            f"/api/v1/contracts/{cid}/versions",
            json={
                "effective_date": "2026-07-01",
                "dunning_block": True,
                "dunning_block_reason": "Ratenzahlung vereinbart",
            },
            headers=h,
        )
    )
    assert v2["version"] == 2
    assert v2["number"] == contract["number"]
    assert v2["debtor_account"]["id"] == contract["debtor_account"]["id"]
    assert v2["supersedes_contract_id"] == cid
    v1 = _ok(client.get(f"/api/v1/contracts/{cid}", headers=h), 200)
    assert v1["end_date"] == "2026-06-30"
    assert {(p["payment_type_code"], p["valid_to"]) for p in v1["payments"]} == {
        ("rent", "2026-06-30"),
        ("operating_cost_advance", "2026-06-30"),
        ("rent_reduction", "2026-06-30"),
    }
    assert sorted((p["payment_type_code"], p["valid_from"]) for p in v2["payments"]) == [
        ("operating_cost_advance", "2026-07-01"),
        ("rent", "2026-07-01"),
        ("rent", "2027-01-01"),
        ("rent_reduction", "2026-07-01"),
    ]
    assert len(v2["schedules"]) == 1
    assert v2["schedules"][0]["valid_from"] == "2026-07-01"
    again = client.post(
        f"/api/v1/contracts/{cid}/versions", json={"effective_date": "2026-08-01"}, headers=h
    )
    assert again.status_code == 409
    history = _ok(client.get(f"{pay}", headers=h), 200)
    assert len(history) == 7
    versions = _ok(client.get(f"/api/v1/contracts/{v2['id']}/versions", headers=h), 200)
    assert [v["version"] for v in versions] == [1, 2]

    early = client.post(
        f"/api/v1/contracts/{v2['id']}/termination", json={"end_date": "2026-12-31"}, headers=h
    )
    assert early.status_code == 422  # a rent change from 2027 exists
    ended = _ok(
        client.post(
            f"/api/v1/contracts/{v2['id']}/termination",
            json={"end_date": "2027-06-30", "termination_date": "2027-03-15"},
            headers=h,
        ),
        200,
    )
    assert ended["end_date"] == "2027-06-30"
    assert all(p["valid_to"] is not None for p in ended["payments"])

    occupancy = _ok(
        client.get(
            f"/api/v1/properties/{prop['id']}/occupancy", params={"as_of": "2026-09-01"}, headers=h
        ),
        200,
    )
    assert occupancy[0]["tenancy_contract_id"] == v2["id"]
    assert occupancy[0]["vacant"] is False
    later = _ok(
        client.get(
            f"/api/v1/properties/{prop['id']}/occupancy", params={"as_of": "2027-09-01"}, headers=h
        ),
        200,
    )
    assert later[0]["vacant"] is True
    listed = _ok(
        client.get(
            "/api/v1/contracts", params={"unit_id": unit, "active_on": "2026-03-01"}, headers=h
        ),
        200,
    )
    assert [c["id"] for c in listed] == [cid]

    caretaker = bearer(login(client, world, "m5caretaker"))
    assert client.get("/api/v1/contracts", headers=caretaker).status_code == 403


def test_ownership_transfer_and_sev(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m5admin"))
    weg = _property(client, h, "502", "hoa_with_sev")
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(client, h, weg["id"], "01")
    seller, _ = _party(client, h, "Verkaeufer")
    buyer, _ = _party(client, h, "Kaeufer")
    tenant, _ = _party(client, h, "Mieterin")
    ownership = {
        "kind": "ownership",
        "unit_id": unit,
        "party_id": seller,
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
    }
    assert (
        client.post(
            "/api/v1/contracts", json={**ownership, "title_transfer_date": None}, headers=h
        ).status_code
        == 422
    )
    tenancy = {"kind": "tenancy", "unit_id": unit, "party_id": tenant, "start_date": "2024-01-01"}
    no_owner = client.post("/api/v1/contracts", json=tenancy, headers=h)
    assert no_owner.status_code == 422
    first = _ok(
        client.post("/api/v1/contracts", json={**ownership, "sev_enabled": True}, headers=h)
    )
    assert first["legal_entity_id"] == hoa
    assert first["sev_fee_debtor_party_id"] == seller
    _ok(
        client.post(
            f"/api/v1/contracts/{first['id']}/payments",
            json=_payment("300.00", "300.00", "2020-01-01", "hoa_fee"),
            headers=h,
        )
    )
    lease = _ok(client.post("/api/v1/contracts", json=tenancy, headers=h))
    assert lease["legal_entity_id"] != hoa  # landlord is the owner, not the GdWE (6.9.11)
    assert (
        client.post(
            f"/api/v1/contracts/{first['id']}/termination",
            json={"end_date": "2026-01-01"},
            headers=h,
        ).status_code
        == 422
    )

    transfer = f"/api/v1/contracts/{first['id']}/ownership-transfer"
    same = {
        "new_party_id": seller,
        "title_transfer_date": "2026-04-01",
        "acquisition_kind": "purchase",
    }
    assert client.post(transfer, json=same, headers=h).status_code == 422
    new = _ok(
        client.post(
            transfer,
            json={**same, "new_party_id": buyer, "benefit_burden_date": "2026-03-01"},
            headers=h,
        )
    )
    assert new["party_id"] == buyer
    assert new["start_date"] == "2026-04-01"
    assert new["legal_entity_id"] == hoa
    assert new["debtor_account"]["id"] != first["debtor_account"]["id"]
    assert new["debtor_account"]["number"] == "090001"
    assert new["benefit_burden_date"] == "2026-03-01"
    old = _ok(client.get(f"/api/v1/contracts/{first['id']}", headers=h), 200)
    assert old["end_date"] == "2026-03-31"
    assert old["payments"][0]["valid_to"] == "2026-03-31"
    assert client.post(transfer, json={**same, "new_party_id": buyer}, headers=h).status_code == 422

    plain = _property(client, h, "503", "hoa")
    plain_unit = _unit(client, h, plain["id"], "01")
    assert (
        client.post(
            "/api/v1/contracts", json={**tenancy, "unit_id": plain_unit}, headers=h
        ).status_code
        == 422
    )
    rental = _property(client, h, "504", "rental")
    rental_unit = _unit(client, h, rental["id"], "01")
    assert (
        client.post(
            "/api/v1/contracts", json={**ownership, "unit_id": rental_unit}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/contracts",
            json={**ownership, "unit_id": plain_unit, "sev_enabled": True},
            headers=h,
        ).status_code
        == 422
    )


def test_mandates_direct_debit_and_deposits(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m5admin"))
    prop = _property(client, h, "505", "rental")
    unit = _unit(client, h, prop["id"], "01")
    owner, _ = _party(client, h, "Vermieter", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
    )["legal_entity_id"]
    tenant, contact = _party(client, h, "Zahler", iban=IBAN)
    account_id = contact["bank_accounts"][0]["id"]
    mandate = {
        "party_id": tenant,
        "legal_entity_id": entity,
        "contact_bank_account_id": account_id,
        "reference": f"M{RUN}"[:35],
        "creditor_id": "DE98ZZZ09999999999",
        "signed_at": "2026-01-01",
        "document_id": "0190a000-0000-7000-8000-000000000001",
    }
    assert (
        client.post("/api/v1/sepa-mandates", json={**mandate, "type": "b2b"}, headers=h).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/sepa-mandates",
            json={**mandate, "creditor_id": "DE97ZZZ09999999999"},
            headers=h,
        ).status_code
        == 422
    )
    other, _ = _party(client, h, "Fremd")
    assert (
        client.post(
            "/api/v1/sepa-mandates", json={**mandate, "party_id": other}, headers=h
        ).status_code
        == 422
    )
    created = _ok(client.post("/api/v1/sepa-mandates", json=mandate, headers=h))
    assert created["iban_masked"] == "DE02 **** **** 2051"
    assert created["status"] == "active"
    assert client.post("/api/v1/sepa-mandates", json=mandate, headers=h).status_code == 409
    # Editing the contact keeps bank accounts when omitted; replacing a mandated one conflicts.
    edit = {"kind": "person", "first_name": "Zahler", "last_name": f"Neu{RUN}"}
    kept = _ok(client.put(f"/api/v1/contacts/{contact['id']}", json=edit, headers=h), 200)
    assert [b["id"] for b in kept["bank_accounts"]] == [account_id]
    replace = {**edit, "bank_accounts": [{"iban": IBAN, "valid_from": "2020-01-01"}]}
    assert (
        client.put(f"/api/v1/contacts/{contact['id']}", json=replace, headers=h).status_code == 409
    )
    found = _ok(client.get("/api/v1/search", params={"q": f"Neu{RUN} 2051"}, headers=h), 200)
    assert contact["id"] in [hit["id"] for hit in found]

    tenancy = {"kind": "tenancy", "unit_id": unit, "party_id": tenant, "start_date": "2026-01-01"}
    assert (
        client.post(
            "/api/v1/contracts", json={**tenancy, "direct_debit": True}, headers=h
        ).status_code
        == 422
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={**tenancy, "direct_debit": True, "sepa_mandate_id": created["id"]},
            headers=h,
        )
    )
    revoked = _ok(client.post(f"/api/v1/sepa-mandates/{created['id']}/revoke", headers=h), 200)
    assert revoked["status"] == "revoked"
    assert (
        _ok(client.get(f"/api/v1/contracts/{contract['id']}", headers=h), 200)["direct_debit"]
        is False
    )
    listed = _ok(
        client.get(
            "/api/v1/sepa-mandates", params={"party_id": tenant, "status": "revoked"}, headers=h
        ),
        200,
    )
    assert [m["id"] for m in listed] == [created["id"]]

    rent_account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "rent",
                "iban": IBAN,
                "holder": "Miete",
                "valid_from": "2026-01-01",
            },
            headers=h,
        )
    )
    deposit_account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "deposit",
                "iban": IBAN,
                "holder": "Kaution",
                "valid_from": "2026-01-01",
            },
            headers=h,
        )
    )
    deposit = {
        "kind": "cash",
        "amount_due": "2400.00",
        "installments": 3,
        "valid_from": "2026-01-01",
    }
    deposits = f"/api/v1/contracts/{contract['id']}/deposits"
    assert (
        client.post(
            deposits, json={**deposit, "property_bank_account_id": rent_account["id"]}, headers=h
        ).status_code
        == 422
    )
    dep = _ok(
        client.post(
            deposits, json={**deposit, "property_bank_account_id": deposit_account["id"]}, headers=h
        )
    )
    moves = f"/api/v1/deposits/{dep['id']}/movements"
    after = _ok(
        client.post(
            moves, json={"date": "2026-01-05", "amount": "800.00", "kind": "payment"}, headers=h
        )
    )
    assert after["received"] == "800.00"
    assert after["outstanding"] == "1600.00"
    assert after["movements"][0]["review_required"] is True
    assert (
        client.post(
            moves, json={"date": "2026-02-01", "amount": "100.00", "kind": "payout"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            moves,
            json={"date": "2026-02-01", "amount": "900.00", "kind": "offset", "reason": "Schaden"},
            headers=h,
        ).status_code
        == 422
    )
    final = _ok(
        client.post(
            moves,
            json={"date": "2026-02-01", "amount": "200.00", "kind": "offset", "reason": "Schaden"},
            headers=h,
        )
    )
    assert final["balance"] == "600.00"
    assert len(_ok(client.get(deposits, headers=h), 200)) == 1


def test_d17_one_owner_two_units_and_one_unit_two_owners(client: TestClient, world: World) -> None:
    """D17: party A owns units 01 and 02, party B (two persons, 50/50) owns unit 03. Expected:
    three ownership contracts, a debtor account per party and unit (6.9.2, not per person and
    not one for both units), one receivable per contract and month (3 x 300,00 = 900,00, none
    per co owner), and one head vote per party (§ 25 Abs. 2 WEG as implemented in M25): A yes
    with both units, B no gives 1:1, an owner voting differently with two units is refused."""
    from decimal import Decimal

    h = bearer(login(client, world, "m5admin"))
    weg = _property(client, h, "515", "hoa")
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    party_a, _ = _party(client, h, "Doppel")
    first = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Anna", "last_name": f"Gemein{RUN}"},
            headers=h,
        )
    )
    second = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Bernd", "last_name": f"Gemein{RUN}"},
            headers=h,
        )
    )
    party_b = _ok(
        client.post(
            "/api/v1/parties",
            json={
                "members": [
                    {"contact_id": first["id"], "share_percent": "50"},
                    {"contact_id": second["id"], "role": "co_party", "share_percent": "50"},
                ]
            },
            headers=h,
        )
    )
    assert len(party_b["members"]) == 2
    contracts: dict[str, dict[str, Any]] = {}
    for no, party in [("01", party_a), ("02", party_a), ("03", str(party_b["id"]))]:
        unit = _unit(client, h, weg["id"], no)
        contracts[no] = _ok(
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
            )
        )
        _ok(
            client.post(
                f"/api/v1/contracts/{contracts[no]['id']}/payments",
                json=_payment("300.00", "300.00", "2020-01-01", "hoa_fee"),
                headers=h,
            )
        )
        _ok(
            client.post(
                f"/api/v1/contracts/{contracts[no]['id']}/schedules",
                json={"valid_from": "2020-01-01", "due_day": 3},
                headers=h,
            )
        )
    debtors = {no: c["debtor_account"]["id"] for no, c in contracts.items()}
    assert len(set(debtors.values())) == 3  # per party and unit, never shared or per person
    assert contracts["01"]["party_id"] == contracts["02"]["party_id"] == party_a
    assert contracts["03"]["party_id"] == party_b["id"]

    # No double receivable: one item per contract and month, none per co owner.
    acc = "/api/v1/accounting"
    template = _ok(client.post(f"{acc}/templates/default", headers=h))
    ledger = _ok(
        client.post(
            f"{acc}/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        )
    )["id"]
    accounts = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"{acc}/ledgers/{ledger}/accounts", headers=h), 200)
    }
    _ok(
        client.put(
            f"{acc}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": accounts["060100"]},
            headers=h,
        ),
        200,
    )
    run = _ok(
        client.post(
            f"{acc}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "property", "scope_id": weg["id"]},
            headers=h,
        )
    )
    assert run["totals"]["ready"] == {"count": 3, "amount": "900.00"}
    posted = _ok(client.post(f"{acc}/receivable-runs/{run['id']}/post", headers=h), 200)
    assert posted["status"] == "posted"
    items = _ok(
        client.get(f"{acc}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h),
        200,
    )
    assert sorted(i["contract_id"] for i in items) == sorted(c["id"] for c in contracts.values())
    assert sum(Decimal(i["remaining"]) for i in items) == Decimal("900.00")

    # One head vote per party: A (two units) counts once, B (two persons) counts once.
    hoa_api = "/api/v1/hoa"
    meeting = _ok(
        client.post(
            f"{hoa_api}/meetings",
            json={
                "legal_entity_id": hoa,
                "scheduled_at": "2026-06-20T10:00:00+02:00",
                "voting_principle": "head",
            },
            headers=h,
        )
    )
    unanimous = _ok(
        client.post(
            f"{hoa_api}/meetings/{meeting['id']}/agenda",
            json={"title": "Hausordnung", "proposal": "Die Hausordnung wird geändert."},
            headers=h,
        )
    )
    split = _ok(
        client.post(
            f"{hoa_api}/meetings/{meeting['id']}/agenda",
            json={"title": "Dach", "proposal": "Das Dach wird saniert."},
            headers=h,
        )
    )
    _ok(
        client.post(
            f"{hoa_api}/meetings/{meeting['id']}/invite",
            json={"invited_at": "2026-05-29"},
            headers=h,
        ),
        200,
    )
    for no in ("01", "02", "03"):
        _ok(
            client.post(
                f"{hoa_api}/meetings/{meeting['id']}/attendance",
                json={"contract_id": contracts[no]["id"], "present": True},
                headers=h,
            )
        )
    for no, choice in [("01", "yes"), ("02", "yes"), ("03", "no")]:
        _ok(
            client.post(
                f"{hoa_api}/agenda/{unanimous['id']}/votes",
                json={"contract_id": contracts[no]["id"], "choice": choice},
                headers=h,
            )
        )
    tally = _ok(client.get(f"{hoa_api}/agenda/{unanimous['id']}/tally", headers=h), 200)
    assert (tally["yes"], tally["no"], tally["principle"]) == ("1", "1", "head")
    assert tally["proposal"] == "negative"  # 1:1 is no simple majority; A never counts twice
    for no, choice in [("01", "yes"), ("02", "no"), ("03", "no")]:
        _ok(
            client.post(
                f"{hoa_api}/agenda/{split['id']}/votes",
                json={"contract_id": contracts[no]["id"], "choice": choice},
                headers=h,
            )
        )
    inconsistent = client.get(f"{hoa_api}/agenda/{split['id']}/tally", headers=h)
    assert inconsistent.status_code == 409, inconsistent.text
    assert "Uneinheitliche Stimmabgabe" in inconsistent.json()["detail"]
