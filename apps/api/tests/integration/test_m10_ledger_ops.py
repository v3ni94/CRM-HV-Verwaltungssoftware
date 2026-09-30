"""M10 gap list 30.09.2026: cost account allocation with exact 100 % total (M10-01), creditor
accounts per provider relation (M10-05), cost transfer and interest drafts (M10-06).

Expected values by hand (rule 0.1.8): allocation 60 % + 40 % = 100 % accepted, 60 % + 30 % =
90 % refused; cost transfer 120.00 EUR: target debit 120.00, source credit 120.00; interest
received 3.50 EUR: bank debit 3.50, revenue credit 3.50."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _hoa_ledger, _ok, _world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _rows(c: TestClient, h: dict[str, str], ledger: str) -> list[dict[str, Any]]:
    return _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))  # type: ignore[no-any-return]


def _of(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["category"] == category and r["active"]]


def _property_of(c: TestClient, h: dict[str, str], ledger: str) -> str:
    return str(_ok(c.get(f"{A}/ledgers/{ledger}", headers=h))["property_id"])


def _keys(c: TestClient, h: dict[str, str], prop: str) -> list[str]:
    keys = _ok(c.get(f"/api/v1/properties/{prop}/allocation-keys", headers=h))
    for code in ("P01A", "P01B"):
        if len(keys) >= 2:
            break
        keys.append(
            _ok(
                c.post(
                    f"/api/v1/properties/{prop}/allocation-keys",
                    json={
                        "code": code,
                        "name": f"Schlüssel {code}",
                        "unit_of_measure": "Stk",
                        "kind": "static",
                    },
                    headers=h,
                ),
                201,
            )
        )
    return [k["id"] for k in keys[:2]]


def test_cost_account_allocation_total_100(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m10admin"))
    ledger, _, _ = _hoa_ledger(client, h, "731")
    rows = _rows(client, h, ledger)
    cost = _of(rows, "cost")[0]["id"]
    bank = _of(rows, "bank")[0]["id"]
    k1, k2 = _keys(client, h, _property_of(client, h, ledger))
    url = f"{A}/ledgers/{ledger}/accounts/{cost}/allocations"
    assert _ok(client.get(url, headers=h))["items"] == []
    bad = client.put(
        url,
        json={
            "items": [
                {"allocation_key_id": k1, "share_percent": "60"},
                {"allocation_key_id": k2, "share_percent": "30"},
            ]
        },
        headers=h,
    )
    assert bad.status_code == 422, bad.text
    dup = client.put(
        url,
        json={
            "items": [
                {"allocation_key_id": k1, "share_percent": "50"},
                {"allocation_key_id": k1, "share_percent": "50"},
            ]
        },
        headers=h,
    )
    assert dup.status_code == 422
    out = _ok(
        client.put(
            url,
            json={
                "items": [
                    {"allocation_key_id": k1, "share_percent": "60"},
                    {"allocation_key_id": k2, "share_percent": "40"},
                ]
            },
            headers=h,
        )
    )
    assert out["total_percent"] in ("100.00000000", "100")
    assert len(out["items"]) == 2
    # replace with a single key, then clear
    assert (
        len(
            _ok(
                client.put(
                    url,
                    json={"items": [{"allocation_key_id": k2, "share_percent": "100"}]},
                    headers=h,
                )
            )["items"]
        )
        == 1
    )
    assert _ok(client.put(url, json={"items": []}, headers=h))["items"] == []
    # only cost accounts
    not_cost = client.put(
        f"{A}/ledgers/{ledger}/accounts/{bank}/allocations",
        json={"items": [{"allocation_key_id": k1, "share_percent": "100"}]},
        headers=h,
    )
    assert not_cost.status_code == 422
    # read only: 403 on write; other tenant: 404
    reader = bearer(login(client, world, "m10reader"))
    assert client.get(url, headers=reader).status_code == 200
    assert client.put(url, json={"items": []}, headers=reader).status_code == 403
    other = bearer(login(client, world, "m10other"))
    assert client.get(url, headers=other).status_code == 404


def test_cost_transfer_and_interest_drafts(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m10admin"))
    ledger, _, _ = _hoa_ledger(client, h, "732")
    rows = _rows(client, h, ledger)
    c1, c2 = (r["id"] for r in _of(rows, "cost")[:2])
    bank = _of(rows, "bank")[0]["id"]
    revenue = _of(rows, "revenue")[0]["id"]
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/cost-transfer",
            json={
                "booking_date": "2026-03-01",
                "from_account_id": c1,
                "to_account_id": c2,
                "amount": "120.00",
                "text": "Umbuchung Fehlkontierung",
            },
            headers=h,
        ),
        201,
    )
    assert draft["kind"] == "cost_transfer"
    assert draft["status"] == "draft"
    lines = {line["account_id"]: line for line in draft["lines"]}
    assert lines[c2]["debit"] == "120.00"
    assert lines[c1]["credit"] == "120.00"
    posted = _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    assert posted["status"] == "posted"
    same = client.post(
        f"{A}/ledgers/{ledger}/entries/cost-transfer",
        json={
            "booking_date": "2026-03-01",
            "from_account_id": c1,
            "to_account_id": c1,
            "amount": "1.00",
            "text": "gleich",
        },
        headers=h,
    )
    assert same.status_code == 422
    wrong = client.post(
        f"{A}/ledgers/{ledger}/entries/cost-transfer",
        json={
            "booking_date": "2026-03-01",
            "from_account_id": bank,
            "to_account_id": c1,
            "amount": "1.00",
            "text": "Bank ist kein Kostenkonto",
        },
        headers=h,
    )
    assert wrong.status_code == 422
    negative = client.post(
        f"{A}/ledgers/{ledger}/entries/cost-transfer",
        json={
            "booking_date": "2026-03-01",
            "from_account_id": c1,
            "to_account_id": c2,
            "amount": "-1.00",
            "text": "negativ",
        },
        headers=h,
    )
    assert negative.status_code == 422

    interest = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/interest",
            json={
                "booking_date": "2026-03-31",
                "bank_account_id": bank,
                "interest_account_id": revenue,
                "amount": "3.50",
                "direction": "credit",
                "text": "Habenzinsen Q1",
            },
            headers=h,
        ),
        201,
    )
    lines = {line["account_id"]: line for line in interest["lines"]}
    assert interest["kind"] == "interest"
    assert lines[bank]["debit"] == "3.50"
    assert lines[revenue]["credit"] == "3.50"
    mismatch = client.post(
        f"{A}/ledgers/{ledger}/entries/interest",
        json={
            "booking_date": "2026-03-31",
            "bank_account_id": bank,
            "interest_account_id": revenue,
            "amount": "3.50",
            "direction": "debit",
            "text": "Sollzinsen auf Erlöskonto",
        },
        headers=h,
    )
    assert mismatch.status_code == 422
    reader = bearer(login(client, world, "m10reader"))
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/entries/interest",
            json={
                "booking_date": "2026-03-31",
                "bank_account_id": bank,
                "interest_account_id": revenue,
                "amount": "3.50",
                "direction": "credit",
                "text": "Leser",
            },
            headers=reader,
        ).status_code
        == 403
    )
    other = bearer(login(client, world, "m10other"))
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/entries/cost-transfer",
            json={
                "booking_date": "2026-03-01",
                "from_account_id": c1,
                "to_account_id": c2,
                "amount": "1.00",
                "text": "fremd",
            },
            headers=other,
        ).status_code
        == 404
    )


def test_creditor_accounts_from_provider_relations(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m10admin"))
    ledger, _, _ = _hoa_ledger(client, h, "733")
    prop = _property_of(client, h, ledger)
    person = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "person", "last_name": f"Kred{RUN}"}, headers=h
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/properties/{prop}/service-providers",
            json={
                "contact_id": person["id"],
                "contract_type_code": "caretaker",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    first = _ok(client.post(f"{A}/ledgers/{ledger}/sync-creditors", headers=h))
    assert first == {"created": 1, "linked": 1}
    again = _ok(client.post(f"{A}/ledgers/{ledger}/sync-creditors", headers=h))
    assert again == {"created": 0, "linked": 0}  # idempotent (B08)
    creditors = _of(_rows(client, h, ledger), "creditor")
    assert len(creditors) == 1
    assert creditors[0]["number"].startswith("07")
    providers = _ok(client.get(f"/api/v1/properties/{prop}/service-providers", headers=h))
    assert providers[0]["creditor_account_id"] == creditors[0]["id"]
    reader = bearer(login(client, world, "m10reader"))
    assert client.post(f"{A}/ledgers/{ledger}/sync-creditors", headers=reader).status_code == 403
    other = bearer(login(client, world, "m10other"))
    assert client.post(f"{A}/ledgers/{ledger}/sync-creditors", headers=other).status_code == 404
