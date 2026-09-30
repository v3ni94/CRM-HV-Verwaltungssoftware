"""WEG gaps M24-01, M24-02, M24-04 to M24-07 (Lückenliste 30.09.2026), year 2025.

Two units MEA 1.000 each. Posted costs on 043000: 1.200,00 (receipt-less entry) and
800,00. Taken from the ledger: two positions 1.200,00 and 800,00, each split 600,00/600,00
and 400,00/400,00; key figures: distribution relevant 2.000,00 = distributed 2.000,00.
§ 35a: labour 300,00 on a manual position of 500,00 -> 150,00 per unit."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m24_hoa import (
    H,
    _book_cost,
    _hoa_ledger,
    _ok,
    _owner,
    clients,  # noqa: F401 (fixture)
    world,  # noqa: F401 (fixture)
)

pytestmark = pytest.mark.integration


def test_costs_from_ledger_35a_key_figures_reserves(
    clients: tuple[TestClient, TestClient],  # noqa: F811
    world: World,  # noqa: F811
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "m24admin"))
    w = _hoa_ledger(client, h, "752")
    mea = w["keys"]["MEA"]
    for no in ("01", "02"):
        _owner(client, h, w["property"], no, "1000", mea, {})
    bank, cost = w["acc"]["001200"], w["acc"]["043000"]
    _book_cost(client, h, w["ledger"], bank, cost, "1200.00", "2025-03-01")
    _book_cost(client, h, w["ledger"], bank, cost, "800.00", "2025-04-01")
    st = _ok(
        client.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2025}, headers=h),
        201,
    )["id"]

    body = {"account_id": cost, "allocation_key_id": mea, "basis": "Gemeinschaftsordnung, MEA"}
    taken = _ok(client.post(f"{H}/statements/{st}/costs/from-ledger", json=body, headers=h), 201)
    assert sorted(c["amount"] for c in taken["created"]) == ["1200.00", "800.00"]
    assert all(c["journal_entry_id"] for c in taken["created"])
    again = _ok(client.post(f"{H}/statements/{st}/costs/from-ledger", json=body, headers=h), 201)
    assert again["created"] == []
    assert {s["reason"] for s in again["skipped"]} == {"already_taken"}

    # Validation: labour share above the amount, reserve on a hoa_fee plan item.
    bad = client.post(
        f"{H}/statements/{st}/costs",
        json={
            "label": "Garten",
            "amount": "100.00",
            "allocation_key_id": mea,
            "basis": "Gemeinschaftsordnung",
            "labour_cost_35a": "200.00",
        },
        headers=h,
    )
    assert bad.status_code == 422

    reserve = _ok(
        client.post(f"{H}/reserves", json={"ledger_id": w["ledger"], "name": "Dach"}, headers=h),
        201,
    )
    assert [
        r["name"]
        for r in _ok(client.get(f"{H}/reserves", params={"ledger_id": w["ledger"]}, headers=h))
    ] == ["Dach"]
    _ok(
        client.post(
            f"{H}/statements/{st}/reserve-movements",
            json={
                "reserve_id": reserve["id"],
                "kind": "fee",
                "amount": "10.00",
                "purpose": "Kontoführung",
            },
            headers=h,
        ),
        201,
    )
    assert (
        client.post(
            f"{H}/statements/00000000-0000-7000-8000-000000000000/reserve-movements",
            json={"reserve_id": reserve["id"], "kind": "fee", "amount": "1.00", "purpose": "xyz"},
            headers=h,
        ).status_code
        == 404
    )

    snap: dict[str, Any] = _ok(client.post(f"{H}/statements/{st}/calculate", headers=h))["snapshot"]
    kf = snap["key_figures"]
    assert (kf["costs_distribution_relevant"], kf["costs_distributed"]) == ("2000.00", "2000.00")
    assert snap["reserve"]["positions"][0]["fees"] == "10.00"
    package = _ok(client.get(f"{H}/statements/{st}/package", headers=h))
    assert {c["receipt_status"] for c in package["cost_items"]} == {"entry_only"}
    assert package["missing_receipts"] == []
    assert package["key_figures"] == kf

    # Unit PDF stays behind G4 (closed client).
    unit_id = snap["units"][0]["unit_id"]
    assert client.get(f"{H}/statements/{st}/units/{unit_id}/pdf", headers=h).status_code in (
        403,
        409,
        423,
    )


def test_plan_master_data_and_comparison(
    clients: tuple[TestClient, TestClient],  # noqa: F811
    world: World,  # noqa: F811
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "m24admin"))
    w = _hoa_ledger(client, h, "753")
    mea = w["keys"]["MEA"]
    for no in ("01", "02"):
        _owner(client, h, w["property"], no, "1000", mea, {})
    plan = _ok(
        client.post(
            f"{H}/plans",
            json={
                "ledger_id": w["ledger"],
                "year": 2026,
                "valid_from": "2026-01-01",
                "title": "Wirtschaftsplan 2026",
                "payment_rhythm": "monthly",
                "due_day": 3,
            },
            headers=h,
        ),
        201,
    )
    assert (plan["title"], plan["due_day"], plan["continues_until_new_plan"], plan["obsolete"]) == (
        "Wirtschaftsplan 2026",
        3,
        True,
        False,
    )
    _ok(
        client.post(
            f"{H}/plans/{plan['id']}/items",
            json={
                "label": "Versicherung",
                "component": "hoa_fee",
                "amount": "1200.00",
                "allocation_key_id": mea,
                "basis_amount": "1000.00",
            },
            headers=h,
        ),
        201,
    )
    bad = client.post(
        f"{H}/plans/{plan['id']}/items",
        json={
            "label": "X",
            "component": "hoa_fee",
            "amount": "1.00",
            "allocation_key_id": mea,
            "reserve_id": "00000000-0000-7000-8000-000000000000",
        },
        headers=h,
    )
    assert bad.status_code == 422
    calc = _ok(client.post(f"{H}/plans/{plan['id']}/calculate", headers=h))
    assert calc["snapshot"]["comparison"][0]["deviation"] == "200.00"
