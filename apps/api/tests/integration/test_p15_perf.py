"""Performance targets of section 16 (S16-08). Marked ``slow`` and skipped unless
``MHVP_PERF=1``: the numbers only mean something on a quiet machine with the production like
PostgreSQL, never in the shared CI run. Each test prints its measurement as a
``PERF`` line (collected in docs/runbooks/leistungsmessung.md).

Targets (16): P95 below 300 ms for a list of 10.000 rows; monthly receivable run of 1.000
contracts below 2 minutes (covered by ``test_m13_receivables.py::test_a27_...``, 869 units);
statement of 100 units below 1 minute; bank retrieval of 100 accounts (connector stub in
``tests/bank_connector_stub.py``, no network). The seeds live in ``perf_seed.py``."""

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
STATEMENT_LIMIT_SECONDS = 60.0
RETRIEVAL_LIMIT_SECONDS = 60.0  # operator threshold, spec names no limit


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


def test_statement_of_100_units_below_one_minute(client: TestClient, world: World) -> None:
    """Statement calculation for a WEG with 100 units (16): below 60 seconds. The seed creates
    owners, ledger, one posted cost payment and the draft; only ``calculate`` is timed."""
    from tests.integration.perf_seed import seed_statement_data

    headers = bearer(login(client, world, "perfadmin"))
    data = seed_statement_data(client, headers)
    started = time.perf_counter()
    response = client.post(
        f"/api/v1/hoa/statements/{data['statement_id']}/calculate", headers=headers
    )
    seconds = time.perf_counter() - started
    assert response.status_code == 200, response.text
    print(  # noqa: T201 - measurement protocol
        f"PERF statement_calculate units={data['units']} seconds={seconds:.1f}"
    )
    assert seconds < STATEMENT_LIMIT_SECONDS


async def _retrieve(
    settings: Any, tenant_id: Any, account_ids: list[str]
) -> tuple[int, int, float]:
    """Retrieval of all accounts through the connector stub into bank_transaction (same import
    path as the finAPI fetch task); returns accounts, new transactions, seconds."""
    from datetime import date
    from uuid import UUID

    from sqlalchemy import select

    from mhvp.banking import services as bank_services
    from mhvp.banking.models import BankSyncRun
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.properties.models import PropertyBankAccount
    from tests.bank_connector_stub import StubBankConnector

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            rows = list(
                await session.scalars(
                    select(PropertyBankAccount).where(
                        PropertyBankAccount.id.in_([UUID(a) for a in account_ids])
                    )
                )
            )
            assert len(rows) == len(account_ids)
            connector = StubBankConnector([r.iban for r in rows])
            infos = {i.iban: i for i in connector.list_accounts()}
            started = time.perf_counter()
            new = 0
            for row in rows:
                raw = connector.fetch_transactions(
                    infos[row.iban], date(2026, 9, 1), date(2026, 9, 30)
                )
                run = BankSyncRun(
                    tenant_id=tenant_id,
                    property_bank_account_id=row.id,
                    source="connector_stub",
                    status="ok",
                    counts={},
                )
                session.add(run)
                await session.flush()
                counts = await bank_services.import_finapi_transactions(
                    session,
                    tenant_id=tenant_id,
                    property_bank_account_id=row.id,
                    legal_entity_id=row.legal_entity_id,
                    iban_fingerprint=crypto.fingerprint(row.iban),
                    run=run,
                    transactions=raw,
                )
                new += counts["new"]
            seconds = time.perf_counter() - started
            assert connector.fetch_calls == len(rows)
        return len(rows), new, seconds
    finally:
        await engine.dispose()


def test_bank_retrieval_of_100_accounts(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Bank retrieval for 100 accounts with the connector stub (16): the stub delivers 20
    transactions per account; all must be imported. Limit is an operator threshold."""
    from tests.integration.perf_seed import ACCOUNTS, seed_bank_accounts

    headers = bearer(login(client, world, "perfadmin"))
    ids = seed_bank_accounts(client, headers, start=200)
    assert len(ids) == ACCOUNTS
    accounts, new, seconds = asyncio.run(
        _retrieve(_settings(database, redis_url), world.tenant_a, ids)
    )
    print(  # noqa: T201 - measurement protocol
        f"PERF bank_retrieval accounts={accounts} transactions={new} seconds={seconds:.1f}"
    )
    assert (accounts, new) == (ACCOUNTS, ACCOUNTS * 20)
    assert seconds < RETRIEVAL_LIMIT_SECONDS
