"""ADR 0002: tenant isolation through row level security, tested with the real roles."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.rls import tenant_rls_statements
from mhvp.core.db.tenancy import tenant_transaction
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration

PROBE = "rls_probe_m1"
TENANT_A = uuid.UUID("0199a0c0-0000-7000-8000-00000000000a")
TENANT_B = uuid.UUID("0199a0c0-0000-7000-8000-00000000000b")
_BIND = text("SELECT set_config('app.tenant_id', :tenant, true)")

# Guard for every milestone: each table with a tenant_id column must be isolated.
_UNISOLATED = text(
    """
    SELECT c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND c.relkind IN ('r', 'p')
       AND NOT (
             c.relrowsecurity
         AND c.relforcerowsecurity
         AND EXISTS (
               SELECT 1 FROM pg_policy p
                WHERE p.polrelid = c.oid
                  AND p.polname = 'tenant_isolation'
                  AND NOT p.polpermissive
                  AND p.polcmd = '*'
                  AND p.polroles = '{0}'
                  AND pg_get_expr(p.polqual, p.polrelid) = '(tenant_id = app_current_tenant_id())'
                  AND pg_get_expr(p.polwithcheck, p.polrelid)
                      = '(tenant_id = app_current_tenant_id())'
             )
       )
     ORDER BY c.relname
    """
)


def unisolated_tenant_tables(conn: Connection) -> list[str]:
    return list(conn.execute(_UNISOLATED).scalars())


def _insert(conn: Connection, tenant: uuid.UUID, label: str) -> None:
    conn.execute(_BIND, {"tenant": str(tenant)})
    conn.execute(
        text(f"INSERT INTO {PROBE} (id, tenant_id, label) VALUES (gen_random_uuid(), :t, :l)"),
        {"t": tenant, "l": label},
    )


@pytest.fixture
def probe(migrator_engine: Engine) -> Iterator[str]:
    with migrator_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {PROBE}"))
        conn.execute(
            text(
                f"CREATE TABLE {PROBE} (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, "
                "label text NOT NULL)"
            )
        )
        for statement in tenant_rls_statements(PROBE):
            conn.execute(text(statement))
    with migrator_engine.begin() as conn:
        _insert(conn, TENANT_A, "a1")
        _insert(conn, TENANT_A, "a2")
    with migrator_engine.begin() as conn:
        _insert(conn, TENANT_B, "b1")
    yield PROBE
    with migrator_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {PROBE}"))


def _labels(conn: Connection) -> list[str]:
    return list(conn.execute(text(f"SELECT label FROM {PROBE} ORDER BY label")).scalars())


def test_without_tenant_context_nothing_is_visible(probe: str, app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        assert _labels(conn) == []


def test_owner_is_bound_by_forced_rls(probe: str, migrator_engine: Engine) -> None:
    with migrator_engine.begin() as conn:
        assert _labels(conn) == []


async def test_tenant_transaction_sees_only_own_rows(probe: str, database: Database) -> None:
    engine = create_async_engine(database.app_url)
    sessions = create_session_factory(engine)
    try:
        async with tenant_transaction(sessions, TENANT_A) as session:
            rows = (await session.execute(text(f"SELECT label FROM {PROBE} ORDER BY 1"))).scalars()
            assert list(rows) == ["a1", "a2"]
        async with tenant_transaction(sessions, TENANT_B) as session:
            rows = (await session.execute(text(f"SELECT label FROM {PROBE}"))).scalars()
            assert list(rows) == ["b1"]
    finally:
        await engine.dispose()


async def test_tenant_context_does_not_leak_into_next_transaction(
    probe: str, database: Database
) -> None:
    # One pooled connection only, so the second transaction reuses the first connection.
    engine = create_async_engine(database.app_url, pool_size=1, max_overflow=0)
    sessions = create_session_factory(engine)
    try:
        async with tenant_transaction(sessions, TENANT_A) as session:
            assert (await session.execute(text(f"SELECT count(*) FROM {PROBE}"))).scalar_one() == 2
        async with sessions() as session, session.begin():
            setting = await session.execute(text("SELECT app_current_tenant_id()"))
            assert setting.scalar_one() is None
            assert (await session.execute(text(f"SELECT count(*) FROM {PROBE}"))).scalar_one() == 0
    finally:
        await engine.dispose()


async def test_tenant_transaction_requires_uuid(database: Database) -> None:
    engine = create_async_engine(database.app_url)
    try:
        with pytest.raises(TypeError):
            async with tenant_transaction(create_session_factory(engine), "A"):  # type: ignore[arg-type]
                pass
    finally:
        await engine.dispose()


def test_cross_tenant_insert_is_rejected(probe: str, app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(_BIND, {"tenant": str(TENANT_A)})
        with pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(
                text(f"INSERT INTO {PROBE} VALUES (gen_random_uuid(), :t, 'x')"),
                {"t": TENANT_B},
            )


def test_cross_tenant_update_is_rejected(probe: str, app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(_BIND, {"tenant": str(TENANT_A)})
        moved = conn.execute(text(f"UPDATE {PROBE} SET label = 'hacked' WHERE label = 'b1'"))
        assert moved.rowcount == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(text(f"UPDATE {PROBE} SET tenant_id = :t"), {"t": TENANT_B})


def test_insert_without_context_is_rejected(probe: str, app_engine: Engine) -> None:
    with app_engine.begin() as conn, pytest.raises(DBAPIError, match="row-level security"):
        conn.execute(
            text(f"INSERT INTO {PROBE} VALUES (gen_random_uuid(), :t, 'x')"), {"t": TENANT_A}
        )


def test_malformed_context_raises(probe: str, app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(_BIND, {"tenant": "not-a-uuid"})
        with pytest.raises(DBAPIError, match="invalid input syntax for type uuid"):
            conn.execute(text(f"SELECT count(*) FROM {PROBE}"))


def test_extra_permissive_policy_cannot_cross_tenants(
    probe: str, migrator_engine: Engine, app_engine: Engine
) -> None:
    with migrator_engine.begin() as conn:
        conn.execute(text(f"CREATE POLICY leaky ON {PROBE} AS PERMISSIVE FOR ALL USING (true)"))
    with app_engine.begin() as conn:
        conn.execute(_BIND, {"tenant": str(TENANT_A)})
        assert _labels(conn) == ["a1", "a2"]


@pytest.mark.parametrize(
    "statement",
    [
        f"ALTER TABLE {PROBE} DISABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {PROBE} NO FORCE ROW LEVEL SECURITY",
        f"DROP POLICY tenant_isolation ON {PROBE}",
        f"CREATE POLICY open ON {PROBE} USING (true)",
    ],
)
def test_runtime_role_cannot_weaken_rls(probe: str, app_engine: Engine, statement: str) -> None:
    with app_engine.begin() as conn, pytest.raises(DBAPIError, match="must be owner"):
        conn.execute(text(statement))


def test_every_tenant_table_is_isolated(database: Database, migrator_engine: Engine) -> None:
    with migrator_engine.connect() as conn:
        assert unisolated_tenant_tables(conn) == []


def test_guard_accepts_probe_and_detects_missing_rls(probe: str, migrator_engine: Engine) -> None:
    with migrator_engine.begin() as conn:
        assert unisolated_tenant_tables(conn) == []
        conn.execute(text("CREATE TABLE rls_probe_unprotected (tenant_id uuid NOT NULL)"))
        try:
            assert unisolated_tenant_tables(conn) == ["rls_probe_unprotected"]
        finally:
            conn.execute(text("DROP TABLE rls_probe_unprotected"))


@pytest.mark.parametrize(
    "policy",
    [
        "AS RESTRICTIVE FOR ALL TO CURRENT_USER USING (tenant_id = app_current_tenant_id()) "
        "WITH CHECK (tenant_id = app_current_tenant_id())",
        "AS RESTRICTIVE FOR ALL USING (app_current_tenant_id() IS NULL OR true) "
        "WITH CHECK (tenant_id = app_current_tenant_id())",
    ],
)
def test_guard_detects_weak_isolation_policy(migrator_engine: Engine, policy: str) -> None:
    with migrator_engine.begin() as conn:
        conn.execute(text("CREATE TABLE rls_probe_weak (tenant_id uuid NOT NULL)"))
        try:
            conn.execute(text("ALTER TABLE rls_probe_weak ENABLE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE rls_probe_weak FORCE ROW LEVEL SECURITY"))
            conn.execute(text(f"CREATE POLICY tenant_isolation ON rls_probe_weak {policy}"))
            assert unisolated_tenant_tables(conn) == ["rls_probe_weak"]
        finally:
            conn.execute(text("DROP TABLE rls_probe_weak"))
