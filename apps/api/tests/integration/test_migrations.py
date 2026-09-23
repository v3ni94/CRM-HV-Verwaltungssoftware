"""Alembic baseline: round trip and no autogenerate drift (CI migration check)."""

import pytest
from alembic import command
from sqlalchemy import Engine, text

from tests.integration.conftest import Database, alembic_config

pytestmark = pytest.mark.integration

_FUNCTION_EXISTS = text("SELECT count(*) FROM pg_proc WHERE proname = 'app_current_tenant_id'")


def test_downgrade_and_upgrade_round_trip(database: Database, migrator_engine: Engine) -> None:
    config = alembic_config(database.migrator_url)
    command.downgrade(config, "base")
    with migrator_engine.connect() as conn:
        assert conn.execute(_FUNCTION_EXISTS).scalar_one() == 0
    command.upgrade(config, "head")
    with migrator_engine.connect() as conn:
        assert conn.execute(_FUNCTION_EXISTS).scalar_one() == 1
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001"


def test_no_autogenerate_drift(database: Database) -> None:
    command.check(alembic_config(database.migrator_url))


def test_required_extensions_present(migrator_engine: Engine) -> None:
    with migrator_engine.connect() as conn:
        names = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert {"pgcrypto", "pg_trgm", "btree_gist", "vector"} <= names


def test_current_tenant_function(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        assert conn.execute(text("SELECT app_current_tenant_id()")).scalar_one() is None
        conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        assert conn.execute(text("SELECT app_current_tenant_id()")).scalar_one() is None
        tenant = "0199a0c0-0000-7000-8000-00000000000a"
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        assert str(conn.execute(text("SELECT app_current_tenant_id()")).scalar_one()) == tenant
