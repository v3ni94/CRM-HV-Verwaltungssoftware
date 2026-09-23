"""ADR 0002: the runtime role cannot bypass row level security (M1: RLS roles)."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from mhvp.core import health
from mhvp.core.health import HealthCheckFailedError
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration

_ATTRIBUTES = text(
    "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolinherit, rolreplication "
    "FROM pg_roles WHERE rolname = :name"
)


@pytest.mark.parametrize("role", ["app", "migrator"])
def test_roles_have_no_elevated_attributes(
    role: str, database: Database, migrator_engine: Engine
) -> None:
    name = database.app_role if role == "app" else database.migrator_role
    with migrator_engine.connect() as conn:
        row = conn.execute(_ATTRIBUTES, {"name": name}).one()
    assert tuple(row) == (False, False, False, False, False, False)


def test_runtime_role_owns_nothing(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        owned = conn.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
                "WHERE r.rolname = current_user"
            )
        ).scalar_one()
        schemas = conn.execute(
            text(
                "SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner "
                "WHERE r.rolname = current_user"
            )
        ).scalar_one()
    assert (owned, schemas) == (0, 0)


def test_runtime_role_cannot_create_tables(app_engine: Engine) -> None:
    with app_engine.connect() as conn, pytest.raises(DBAPIError, match="permission denied"):
        conn.execute(text("CREATE TABLE sneaky (id int)"))


def test_runtime_role_cannot_assume_migrator(database: Database, app_engine: Engine) -> None:
    with app_engine.connect() as conn, pytest.raises(DBAPIError, match="permission denied"):
        conn.execute(text(f'SET ROLE "{database.migrator_role}"'))


def test_runtime_role_reads_but_cannot_write_migration_state(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    with app_engine.connect() as conn, pytest.raises(DBAPIError, match="permission denied"):
        conn.execute(text("UPDATE alembic_version SET version_num = 'forged'"))


async def test_readiness_role_check_accepts_runtime_role(database: Database) -> None:
    engine = create_async_engine(database.app_url)
    try:
        await health.database_role_check(engine)()
        await health.database_check(engine)()
        await health.migrations_check(engine, Path("alembic.ini"))()
    finally:
        await engine.dispose()


async def test_readiness_role_check_rejects_owner_role(database: Database) -> None:
    engine = create_async_engine(database.migrator_url)
    try:
        with pytest.raises(HealthCheckFailedError, match="owns database objects"):
            await health.database_role_check(engine)()
    finally:
        await engine.dispose()
