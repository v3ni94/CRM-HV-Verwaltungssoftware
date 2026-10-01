"""Package U08 (S16-08 rest): measurements beyond the earlier perf tests. Marked ``slow`` and
skipped unless ``MHVP_PERF=1``; values measured on a shared machine are only plausibility checks.

* Receivable run (Sollstellungslauf) with exactly 1.000 ownership contracts (10 properties,
  100 contracts each, two payment components): preview and posting for scope=all, limit 2 minutes.
* Statement output beyond ``calculate``: internal approval, Gesamtabrechnung PDF on the tenant
  letterhead and all 100 unit PDFs of a WEG, limit 1 minute (operator threshold, as for
  the calculation). Every PDF is checked for content, not only the status code.
"""

import asyncio
import io
import os
import time
from collections.abc import Iterator
from typing import Any
from unittest import mock

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from mhvp.main import create_app
from tests.integration import test_m13_receivables as m13
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m8_import import _settings as s3_settings
from tests.integration.test_m24_hoa import H, OpenG4, _ok

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("MHVP_PERF") != "1", reason="set MHVP_PERF=1 to measure"),
]
CONTRACTS = 1_000
PROPERTIES = 10
RUN_LIMIT_SECONDS = 120.0
OUTPUT_LIMIT_SECONDS = 60.0


@pytest.fixture(scope="module")
def load_world_1000(database: Database, redis_url: str) -> World:
    started = time.perf_counter()
    with (
        mock.patch.object(m13, "LOAD_UNITS", CONTRACTS),
        mock.patch.object(m13, "LOAD_PROPERTIES", PROPERTIES),
    ):
        world = asyncio.run(m13._load_world(base_settings(database, redis_url)))
    print(  # noqa: T201 - measurement protocol
        f"\nPERF receivable_seed contracts={CONTRACTS} seconds={time.perf_counter() - started:.1f}"
    )
    return world


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as c:
        yield c


def test_receivable_run_with_1000_contracts_below_two_minutes(
    client: TestClient, load_world_1000: World
) -> None:
    h = bearer(login(client, load_world_1000, "m13load"))
    t0 = time.perf_counter()
    run = _ok(
        client.post(f"{m13.A}/receivable-runs", json={"period_month": "2026-07-01"}, headers=h),
        201,
    )
    preview_s = time.perf_counter() - t0
    # two components per contract: 1.000 items of hoa_fee and reserve each, nothing blocked
    assert run["totals"]["count"] == run["totals"]["ready"]["count"] == CONTRACTS * 2
    t0 = time.perf_counter()
    done = _ok(client.post(f"{m13.A}/receivable-runs/{run['id']}/post", headers=h))
    post_s = time.perf_counter() - t0
    assert done["status"] == "posted"
    assert sum(1 for i in done["items"] if i["status"] == "posted") == CONTRACTS * 2
    print(  # noqa: T201 - measurement protocol
        f"PERF receivable_run contracts={CONTRACTS} items={CONTRACTS * 2} "
        f"preview={preview_s:.1f}s post={post_s:.1f}s total={preview_s + post_s:.1f}s"
    )
    assert preview_s + post_s < RUN_LIMIT_SECONDS


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"u08-{RUN}", name=f"U08 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("u08admin", "u08second"):
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


def test_statement_output_of_100_units_below_one_minute(database: Database, redis_url: str) -> None:
    from tests.integration.perf_seed import UNITS, seed_statement_data

    world = asyncio.run(_world(base_settings(database, redis_url)))
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = s3_settings(database, redis_url)
        with TestClient(create_app(settings, release_gate_resolver=OpenG4())) as c:
            h = bearer(login(c, world, "u08admin"))
            h2 = bearer(login(c, world, "u08second"))
            _ok(c.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
            data = seed_statement_data(c, h)
            sid = data["statement_id"]
            _ok(c.post(f"{H}/statements/{sid}/calculate", headers=h))
            _ok(
                c.post(
                    f"{H}/statements/{sid}/transition",
                    json={"target": "internally_approved"},
                    headers=h2,
                )
            )
            statement = _ok(c.get(f"{H}/statements/{sid}", headers=h))
            unit_ids = [u["unit_id"] for u in statement["snapshot"]["units"]]
            assert len(unit_ids) == UNITS

            t0 = time.perf_counter()
            total = c.get(f"{H}/statements/{sid}/pdf", headers=h)
            total_s = time.perf_counter() - t0
            assert total.status_code == 200, total.text
            assert "Gesamtabrechnung 2025" in "".join(
                p.extract_text() for p in PdfReader(io.BytesIO(total.content)).pages
            )

            t0 = time.perf_counter()
            pages = 0
            for unit_id in unit_ids:
                response = c.get(f"{H}/statements/{sid}/units/{unit_id}/pdf", headers=h)
                assert response.status_code == 200, response.text
                assert response.content.startswith(b"%PDF")
                pages += len(PdfReader(io.BytesIO(response.content)).pages)
            units_s = time.perf_counter() - t0
    print(  # noqa: T201 - measurement protocol
        f"PERF statement_output units={UNITS} total_pdf={total_s:.1f}s "
        f"unit_pdfs={units_s:.1f}s unit_pages={pages} all={total_s + units_s:.1f}s"
    )
    assert total_s + units_s < OUTPUT_LIMIT_SECONDS
