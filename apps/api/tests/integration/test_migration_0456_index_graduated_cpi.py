"""AO03 / GAK-203: migration 0456 round trip (columns, tables, RLS)."""

import pytest
from alembic import command
from sqlalchemy import Engine, text

from tests.integration.conftest import Database, alembic_config

pytestmark = pytest.mark.integration

_STATE = text(
    "SELECT (SELECT count(*) FROM information_schema.columns WHERE table_name = 'contract' "
    "AND column_name = 'index_agreement'), "
    "(SELECT count(*) FROM pg_class WHERE relname IN "
    "('contract_graduated_step', 'consumer_price_index') AND relkind = 'r'), "
    "(SELECT count(*) FROM pg_class WHERE relname = 'contract_graduated_step' "
    "AND relrowsecurity AND relforcerowsecurity)"
)


def test_round_trip(database: Database, migrator_engine: Engine) -> None:
    config = alembic_config(database.migrator_url)
    command.upgrade(config, "head")
    with migrator_engine.begin() as conn:
        assert tuple(conn.execute(_STATE).one()) == (1, 2, 1)
    command.downgrade(config, "0455")
    with migrator_engine.begin() as conn:
        assert tuple(conn.execute(_STATE).one()) == (0, 0, 0)
    command.upgrade(config, "head")
    with migrator_engine.begin() as conn:
        assert tuple(conn.execute(_STATE).one()) == (1, 2, 1)
