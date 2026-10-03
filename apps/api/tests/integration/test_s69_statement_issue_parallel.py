"""GAM-608 (rule 0.1.9): owner statement issued twice in parallel, aborted and repeated.

Fixed expectation from the fixture: rental ledger 2025 with one posted expense of 123,45 EUR
(Hausmeister 040100 against bank 001210), no income, no fee setting, no payout. Hand derived:
expenses 123,45; operating result 0,00 - 123,45 = -123,45 EUR. Issuing (behind G3) may happen
exactly once: one ``issued`` entry in the status log, the snapshot hash and the result stay
unchanged by the parallel call, the retry and the aborted call."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m17_owner_statement import A, O, _account, _ok
from tests.integration.test_s69_statement_status import OpenG3G4, _move, _world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


def _issued_count(st: dict[str, Any]) -> int:
    return sum(1 for e in st["status_log"] if e["to"] == "issued")


def test_statement_issue_parallel_and_retry(
    world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    with TestClient(create_app(settings, release_gate_resolver=OpenG3G4())) as client:
        h = bearer(login(client, world, "s69admin"))
        acc = bearer(login(client, world, "s69acc"))
        prop = _ok(
            client.post(
                "/api/v1/properties",
                json={"number": "698", "name": "Miethaus GAM608", "management_type": "rental"},
                headers=h,
            ),
            201,
        )
        owner, _ = _party(client, h, "VermieterGAM608", "company")
        entity = _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/owners",
                json={"party_id": owner, "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )["legal_entity_id"]
        ledger = _ok(client.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)[
            "id"
        ]
        bank = _account(client, h, ledger, "001210", "Mietkonto", "bank", "asset")
        cost = _account(client, h, ledger, "040100", "Hausmeister", "cost", "expense")
        entry = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "custom",
                    "booking_date": "2025-06-30",
                    "text": "Hausmeister GAM-608",
                    "lines": [
                        {"account_id": cost, "debit": "123.45"},
                        {"account_id": bank, "credit": "123.45"},
                    ],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{entry['id']}/post", headers=h))
        st = _ok(
            client.post(
                O,
                json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
                headers=h,
            ),
            201,
        )
        url = f"{O}/{st['id']}"
        calc = _ok(client.post(f"{url}/calculate", headers=h))
        assert calc["results"]["expenses"]["total"] == "123.45"
        assert calc["results"]["operating_result"]["result"] == "-123.45"
        snapshot_hash = calc["snapshot_hash"]
        _ok(_move(client, acc, url, "internally_approved"))
        _ok(_move(client, h, url, "board_reviewed"))

        # Abort: the status log write raises; the transaction rolls back, nothing is issued.
        with (
            patch(
                "mhvp.billing.owner_statement_routers.lifecycle.log_entry",
                side_effect=RuntimeError("synthetic abort"),
            ),
            TestClient(
                create_app(settings, release_gate_resolver=OpenG3G4()),
                raise_server_exceptions=False,
            ) as broken,
        ):
            assert _move(broken, h, url, "issued").status_code == 500
        after_abort = _ok(client.get(url, headers=h))
        assert (after_abort["status"], _issued_count(after_abort)) == ("board_reviewed", 0)

        # Parallel: two issue calls at the same time, exactly one wins.
        def issue_in_own_client(_: int) -> Any:
            with TestClient(create_app(settings, release_gate_resolver=OpenG3G4())) as own:
                return _move(own, h, url, "issued")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(issue_in_own_client, [1, 2]))
        assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]

        # Retry after success: refused, nothing changes.
        assert _move(client, h, url, "issued").status_code == 409
        final = _ok(client.get(url, headers=h))
        assert final["status"] == "issued"
        assert _issued_count(final) == 1
        assert final["snapshot_hash"] == snapshot_hash
        assert final["results"]["expenses"]["total"] == "123.45"
        assert final["results"]["operating_result"]["result"] == "-123.45"
