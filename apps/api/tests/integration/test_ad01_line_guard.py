"""AD01: the journal line guard looks the entry up with an index condition (ADR 0021).

``test_guard_lookup_*`` run in every integration run. The load test (200,000 lines with the
guard active) is marked ``slow`` and runs only with ``MHVP_PERF=1``."""

import asyncio
import os
import time
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = [pytest.mark.integration]

NEW_LOOKUP = "SELECT e.status, e.ledger_id FROM journal_entry e WHERE e.id = $1"
OLD_LOOKUP = "SELECT * FROM journal_entry WHERE id = COALESCE($1, $2)"
LOAD_LIMIT_SECONDS = float(os.environ.get("MHVP_PERF_GUARD_LIMIT", "300"))


def _sync(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _generic_plan(conn: psycopg.Connection, name: str, sql: str, types: str, args: str) -> str:
    conn.execute(f"PREPARE {name}({types}) AS {sql}")
    rows = conn.execute(f"EXPLAIN EXECUTE {name}({args})").fetchall()
    return "\n".join(r[0] for r in rows)


def test_guard_lookup_uses_primary_key_index(database: Database) -> None:
    """The deployed guard body has no COALESCE lookup, and its lookup query gets an index
    condition on the primary key in the generic plan PL/pgSQL uses (app role, RLS active).
    The 0010 lookup is planned with the id only as a filter (contrast, the defect)."""
    with psycopg.connect(_sync(database.app_url), autocommit=True) as conn:
        body = conn.execute(
            "SELECT pg_get_functiondef('mhvp_journal_line_guard'::regproc)"
        ).fetchone()
        assert body is not None
        assert "COALESCE" not in body[0].upper()
        assert "WHERE e.id = entry_id" in body[0]
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(uuid.uuid4()),))
        conn.execute("SET plan_cache_mode = force_generic_plan")
        new_plan = _generic_plan(conn, "ad01_new", NEW_LOOKUP, "uuid", "gen_random_uuid()")
        old_plan = _generic_plan(
            conn, "ad01_old", OLD_LOOKUP, "uuid, uuid", "gen_random_uuid(), NULL"
        )
    assert "Index Scan using pk_journal_entry" in new_plan, new_plan
    assert "Index Cond: (id = $1)" in new_plan, new_plan
    assert "Seq Scan" not in new_plan
    assert "Index Cond: (id =" not in old_plan, old_plan


def test_guard_trigger_enabled(database: Database) -> None:
    with psycopg.connect(_sync(database.migrator_url)) as conn:
        row = conn.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgname = 'journal_line_guard'"
        ).fetchone()
    assert row == ("O",)


perf = pytest.mark.skipif(os.environ.get("MHVP_PERF") != "1", reason="set MHVP_PERF=1")


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    settings = _settings(database, redis_url)

    async def build() -> World:
        from mhvp.core import crypto
        from mhvp.core.db.engine import create_app_engine, create_session_factory

        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            tenant, _ = await services.provision_tenant(
                factory, slug=f"ad01perf-{RUN}", name=f"AD01 Perf {RUN}"
            )
            w = World(
                tenant_a=tenant, tenant_b=tenant, app_url=settings.database_url.get_secret_value()
            )
            uid = await services.create_user(
                factory, email=w.email("ad01perf"), display_name="perf", password=PASSWORD
            )
            w.users["ad01perf"] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
            )
            return w
        finally:
            await engine.dispose()

    return asyncio.run(build())


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


@pytest.mark.slow
@perf
def test_bulk_load_200k_lines_with_guard_active(
    client: TestClient, world: World, database: Database
) -> None:
    from tests.integration.perf_seed import seed_journal_entries

    headers = bearer(login(client, world, "ad01perf"))
    accounting = "/api/v1/accounting"
    prop = client.post(
        "/api/v1/properties",
        json={"number": "904", "name": "Lastobjekt Wache", "management_type": "hoa"},
        headers=headers,
    ).json()
    entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = client.post(f"{accounting}/templates/default", json={}, headers=headers).json()
    ledger = client.post(
        f"{accounting}/ledgers",
        json={"legal_entity_id": entity, "template_id": template["id"]},
        headers=headers,
    ).json()["id"]
    accounts = {
        a["number"]: a["id"]
        for a in client.get(f"{accounting}/ledgers/{ledger}/accounts", headers=headers).json()
    }
    tenant = str(world.tenant_a)
    started = time.perf_counter()
    seed_journal_entries(
        database.app_url,
        database.migrator_url,
        tenant,
        ledger,
        accounts["001200"],
        accounts["043000"],
        100_000,
    )
    seconds = time.perf_counter() - started
    print(f"PERF guard_bulk_lines=200000 seconds={seconds:.1f}")  # noqa: T201
    assert seconds < LOAD_LIMIT_SECONDS
    with psycopg.connect(_sync(database.app_url)) as conn:
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
        count = conn.execute(
            "SELECT count(*) FROM journal_line l JOIN journal_entry e "
            "ON e.id = l.journal_entry_id WHERE e.ledger_id = %s AND e.status = 'posted'",
            (ledger,),
        ).fetchone()
        assert count == (200_000,)
        # The guard still protects the loaded, posted lines (B02).
        with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
            conn.execute(
                "UPDATE journal_line SET debit = debit WHERE journal_entry_id = "
                "(SELECT id FROM journal_entry WHERE ledger_id = %s LIMIT 1)",
                (ledger,),
            )
