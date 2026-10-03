"""GAM-607 (rule 0.1.9): concurrent dunning runs for the same open item.

Fixed expectations from the fixture: one contract with 300,00 hoa_fee + 50,00 reserve due on
03.03.2026, run date 20.03.2026 (17 days overdue, level 1 from 10 days), level 1 is a reminder
without fee, so exactly one level 1 case with fee 0,00 EUR and total 350,00 EUR may be sent.
A second run of the same day must not produce a second reminder letter for the same item."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login
from tests.integration.test_m13_receivables import _contract
from tests.integration.test_m16_dunning import A, OpenG1, _ok, clients, world  # noqa: F401

pytestmark = pytest.mark.integration


def _setup(client: TestClient, gated: TestClient, h: dict[str, str], gh: dict[str, str]) -> str:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "767", "name": "Parallelmahnhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    contract = _contract(client, h, prop["id"], "01", "2020-01-01")
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
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "property", "scope_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    _ok(
        client.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 30, "text": "Mahnung"},
                ],
                "threshold_amount": "20.00",
            },
            headers=h,
        )
    )
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    return str(contract["id"])


def test_dunning_run_parallel_same_stage(
    clients: tuple[TestClient, TestClient],  # noqa: F811
    world: World,  # noqa: F811
    database: Database,
    redis_url: str,
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "m16admin"))
    acc_user = bearer(login(client, world, "m16acc"))
    gh = bearer(login(gated, world, "m16acc"))
    contract_id = _setup(client, gated, h, gh)
    settings = _settings(database, redis_url)

    def own(method: str, path: str, headers: dict[str, str], body: Any = None) -> Any:
        with TestClient(create_app(settings, release_gate_resolver=OpenG1())) as c:
            return c.request(method, path, json=body, headers=headers)

    # Two runs for the same day created at the same time.
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(
            pool.map(
                lambda _: own("POST", f"{A}/dunning-runs", h, {"run_date": "2026-03-20"}), [1, 2]
            )
        )
    runs = [_ok(r, 201) for r in created]
    mine = [next(c for c in r["cases"] if c["contract_id"] == contract_id) for r in runs]
    for case in mine:
        assert (case["status"], case["level"]) == ("proposed", 1)
        assert (case["fee_amount"], case["total"]) == ("0.00", "350.00")

    # The same run approved twice at the same time: exactly one 200, one 409.
    first = runs[0]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        twice = list(
            pool.map(lambda _: own("POST", f"{A}/dunning-runs/{first}/approve", acc_user), [1, 2])
        )
    assert sorted(r.status_code for r in twice) == [200, 409], [r.text for r in twice]

    # Approve the second run and mark both level 1 cases as sent at the same time: exactly one
    # reminder for the item may go out (GAM-607 expectation), the other call is refused.
    _ok(own("POST", f"{A}/dunning-runs/{runs[1]['id']}/approve", acc_user))
    with ThreadPoolExecutor(max_workers=2) as pool:
        sent = list(
            pool.map(
                lambda case: own(
                    "POST", f"{A}/dunning-cases/{case['id']}/mark-sent", h, {"channel": "post"}
                ),
                mine,
            )
        )
    codes = sorted(r.status_code for r in sent)
    statuses = []
    for run in runs:
        detail = _ok(client.get(f"{A}/dunning-runs/{run['id']}", headers=h))
        statuses += [c for c in detail["cases"] if c["contract_id"] == contract_id]
    sent_level_1 = [c for c in statuses if c["status"] == "sent" and c["level"] == 1]
    assert len(sent_level_1) == 1, (codes, [(c["status"], c["level"]) for c in statuses])
    assert sent_level_1[0]["fee_amount"] == "0.00"
    assert codes == [200, 409]
