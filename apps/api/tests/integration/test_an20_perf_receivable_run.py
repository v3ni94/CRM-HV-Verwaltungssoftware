"""GAK-406 (section 16): receivable run (Sollstellungslauf) for 1.000 contracts below 2
minutes. Marked ``slow`` and skipped unless ``MHVP_PERF=1`` (scheduled run:
.github/workflows/perf.yml). The world is built with the loader of test_m13_receivables
(ownership contracts with two monthly components each), here with exactly 1.000 contracts.
Preview and posting of one run over all properties are timed together on the API path."""

import asyncio
import os
import time
from collections.abc import Iterator
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration import test_m13_receivables as m13
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login
from tests.runtime_limits import scaled_limit

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("MHVP_PERF") != "1", reason="set MHVP_PERF=1 to measure"),
]
CONTRACTS = 1000
LIMIT_SECONDS = 120.0  # section 16: 1.000 contracts in under 2 minutes
A = "/api/v1/accounting"


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    with mock.patch.object(m13, "LOAD_UNITS", CONTRACTS):
        return asyncio.run(m13._load_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_receivable_run_for_1000_contracts_below_two_minutes(
    client: TestClient, world: World
) -> None:
    """Expected by hand: 1.000 contracts x 2 components (hoa_fee 300,00 and reserve 50,00)
    = 2.000 ready positions, all posted; preview plus posting below 120 s (load scaled)."""
    h = bearer(login(client, world, "m13load"))
    started = time.perf_counter()
    run = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-07-01"}, headers=h), 201
    )
    preview_s = time.perf_counter() - started
    assert run["totals"]["ready"]["count"] == CONTRACTS * 2
    posting = time.perf_counter()
    done = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    post_s = time.perf_counter() - posting
    assert done["status"] == "posted"
    assert sum(1 for i in done["items"] if i["status"] == "posted") == CONTRACTS * 2
    total = preview_s + post_s
    print(  # noqa: T201 - measurement protocol
        f"PERF receivable_run contracts={CONTRACTS} preview={preview_s:.1f}s "
        f"posting={post_s:.1f}s total={total:.1f}s target=120s"
    )
    assert total < scaled_limit(LIMIT_SECONDS), total
