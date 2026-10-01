"""Synthetic load data seed (S16-08): units and bank accounts through the public API.

No real data: names, numbers and IBANs are generated. IBANs carry a valid check digit
(ISO 13616 mod 97) for the fictitious bank code 10000000, so the API validation accepts them.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

UNITS = 100
ACCOUNTS = 100


def synthetic_iban(index: int) -> str:
    """DE IBAN with bank code 10000000 and a generated account number, valid check digits."""
    bban = f"10000000{index:010d}"
    check = 98 - int(bban + "131400") % 97  # "DE" -> 1314, digits "00" as placeholder
    return f"DE{check:02d}{bban}"


def _post(c: TestClient, h: dict[str, str], url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = c.post(url, json=body, headers=h)
    assert response.status_code == 201, response.text
    return dict(response.json())


def seed_units(c: TestClient, h: dict[str, str], count: int = UNITS) -> str:
    """One WEG property with ``count`` units; returns the property id."""
    prop = _post(
        c,
        h,
        "/api/v1/properties",
        {"number": "901", "name": "Lastobjekt WEG", "management_type": "hoa"},
    )
    building = _post(c, h, f"/api/v1/properties/{prop['id']}/buildings", {"name": "Haus"})
    for n in range(1, count + 1):
        _post(
            c,
            h,
            f"/api/v1/properties/{prop['id']}/units",
            {
                "building_id": building["id"],
                "number": f"{n:03d}",
                "label": f"WE {n:03d}",
                "unit_type": "apartment",
            },
        )
    return str(prop["id"])


def seed_bank_accounts(
    c: TestClient, h: dict[str, str], count: int = ACCOUNTS, start: int = 0
) -> list[str]:
    """``count`` HOA properties with one bank account each; returns the account ids."""
    ids: list[str] = []
    for n in range(start, start + count):
        prop = _post(
            c,
            h,
            "/api/v1/properties",
            {"number": f"{100 + n}", "name": f"Lastkonto {n:03d}", "management_type": "hoa"},
        )
        entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
        account = _post(
            c,
            h,
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            {
                "legal_entity_id": entity,
                "kind": "hoa",
                "iban": synthetic_iban(n),
                "holder": f"GdWE Last {n:03d}",
                "valid_from": "2020-01-01",
            },
        )
        ids.append(str(account["id"]))
    return ids


def seed_statement_data(
    c: TestClient, h: dict[str, str], count: int = UNITS, cost: str = "10000.00"
) -> dict[str, Any]:
    """Statement base data (S16-08): a WEG with ``count`` owned units (MEA 100 each), a ledger,
    one posted cost payment and a draft statement for 2025 with one cost position. Returns the
    statement id; the measurement then covers ``calculate`` only."""
    from tests.integration.test_m24_hoa import _book_cost, _owner

    accounting, hoa_api = "/api/v1/accounting", "/api/v1/hoa"
    prop = _post(
        c,
        h,
        "/api/v1/properties",
        {"number": "902", "name": "Lastobjekt Abrechnung", "management_type": "hoa"},
    )
    entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in c.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h).json()
    }
    for n in range(1, count + 1):
        _owner(c, h, prop["id"], f"{n:03d}", "100", keys["MEA"], {"hoa_fee": "300.00"})
    template = _post(c, h, f"{accounting}/templates/default", {})
    ledger = _post(
        c,
        h,
        f"{accounting}/ledgers",
        {"legal_entity_id": entity, "template_id": template["id"]},
    )["id"]
    accounts = {
        a["number"]: a["id"]
        for a in c.get(f"{accounting}/ledgers/{ledger}/accounts", headers=h).json()
    }
    _book_cost(c, h, ledger, accounts["001200"], accounts["043000"], cost, "2025-03-01")
    statement = _post(
        c,
        h,
        f"{hoa_api}/statements",
        {
            "ledger_id": ledger,
            "year": 2025,
            "reserve_opening": "0.00",
            "reserve_withdrawals": "0.00",
            "reserve_interest": "0.00",
        },
    )
    _post(
        c,
        h,
        f"{hoa_api}/statements/{statement['id']}/costs",
        {
            "label": "Bewirtschaftungskosten",
            "amount": cost,
            "allocation_key_id": keys["MEA"],
            "basis": "Lastdaten, Verteilung nach MEA",
            "account_id": accounts["043000"],
        },
    )
    return {"statement_id": statement["id"], "units": count, "ledger": ledger}
