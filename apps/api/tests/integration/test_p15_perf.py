"""Performance targets of section 16 (S16-08). Marked ``slow`` and skipped unless
``MHVP_PERF=1``: the numbers only mean something on a quiet machine with the production like
PostgreSQL, never in the shared CI run. Each test prints its measurement as a
``PERF`` line (collected in docs/runbooks/leistungsmessung.md).

Targets (16): P95 below 300 ms for a list of 10.000 rows; monthly receivable run of 1.000
contracts below 2 minutes (covered by ``test_m13_receivables.py::test_a27_...``, 869 units);
statement of 100 units below 1 minute; bank retrieval of 100 accounts. The seed lives in
``perf_seed.py``; the last two still lack statement data and a connector stub and are skipped
with that reason, not faked."""

import asyncio
import os
import statistics
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, World, _settings, bearer, login

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("MHVP_PERF") != "1", reason="set MHVP_PERF=1 to measure"),
]
ROWS = 10_000
SAMPLES = 40
P95_LIMIT_SECONDS = 0.3


async def _seed(settings: Any) -> World:
    from sqlalchemy import insert

    from mhvp.contacts.models import Contact
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.platform import services
    from tests.integration.test_m2_platform import PASSWORD

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant, _ = await services.provision_tenant(factory, slug=f"perf-{RUN}", name=f"Perf {RUN}")
        world = World(
            tenant_a=tenant, tenant_b=tenant, app_url=settings.database_url.get_secret_value()
        )
        uid = await services.create_user(
            factory, email=world.email("perfadmin"), display_name="perf", password=PASSWORD
        )
        world.users["perfadmin"] = uid
        await services.add_member(
            factory, tenant_id=tenant, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        async with tenant_transaction(factory, tenant) as session:
            for start in range(0, ROWS, 1000):
                await session.execute(
                    insert(Contact),
                    [
                        {
                            "tenant_id": tenant,
                            "kind": "person",
                            "first_name": f"Vorname{i}",
                            "last_name": f"Nachname{i:05d}",
                            "display_name": f"Nachname{i:05d}, Vorname{i}",
                            "language": "de",
                        }
                        for i in range(start, start + 1000)
                    ],
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_seed(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def test_list_of_10000_contacts_p95_below_300_ms(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "perfadmin"))
    first = client.get("/api/v1/contacts", params={"page_size": 50}, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["total"] >= ROWS
    timings: list[float] = []
    for index in range(SAMPLES):
        params = {"page_size": 50, "page": 1 + index % 100}
        if index % 2:
            params["q"] = f"Nachname{index:05d}"
        started = time.perf_counter()
        response = client.get("/api/v1/contacts", params=params, headers=headers)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    print(  # noqa: T201 - measurement protocol
        f"PERF contacts_list rows={ROWS} samples={SAMPLES} "
        f"median={statistics.median(timings) * 1000:.0f}ms p95={p95 * 1000:.0f}ms"
    )
    assert p95 < P95_LIMIT_SECONDS


def test_seed_of_100_units_and_100_bank_accounts(client: TestClient, world: World) -> None:
    """Load data seed (S16-08): 100 units and 100 bank accounts of synthetic data. It is the
    base for the statement and bank retrieval measurements."""
    from tests.integration.perf_seed import ACCOUNTS, UNITS, seed_bank_accounts, seed_units

    headers = bearer(login(client, world, "perfadmin"))
    started = time.perf_counter()
    property_id = seed_units(client, headers)
    units = client.get(f"/api/v1/properties/{property_id}/units", headers=headers)
    assert units.status_code == 200, units.text
    assert len(units.json()) >= UNITS
    accounts = seed_bank_accounts(client, headers)
    assert len(set(accounts)) == ACCOUNTS
    print(  # noqa: T201 - measurement protocol
        f"PERF seed units={UNITS} bank_accounts={ACCOUNTS} "
        f"seconds={time.perf_counter() - started:.1f}"
    )


def test_statement_of_100_units_below_one_minute() -> None:
    pytest.skip(
        "Seed der 100 Einheiten vorhanden; Abrechnungsdaten (Wirtschaftsplan, Kosten) fehlen (S16-08)"
    )


def test_bank_retrieval_of_100_accounts() -> None:
    pytest.skip("Seed der 100 Konten vorhanden; Konnektor-Attrappe für den Abruf fehlt (S16-08)")
