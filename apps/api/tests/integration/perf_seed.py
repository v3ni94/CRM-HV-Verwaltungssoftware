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


def seed_bank_accounts(c: TestClient, h: dict[str, str], count: int = ACCOUNTS) -> list[str]:
    """``count`` HOA properties with one bank account each; returns the account ids."""
    ids: list[str] = []
    for n in range(count):
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
