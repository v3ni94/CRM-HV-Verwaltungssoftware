"""Migration 0221 (review 1.40.2): 0219 created the check constraint of
``tenant_settings.ticket_reopen_window_days`` under a doubled, truncated name; 0221 renames it
to the name the model expects, idempotently for every state (wrong name, both names, right
name only, no check), and the downgrade restores the name of 0219."""

import pytest
from alembic import command
from sqlalchemy import Engine, text

from tests.integration.conftest import Database, alembic_config

pytestmark = pytest.mark.integration

RIGHT = "ck_tenant_settings_ticket_reopen_window_days_range"
WRONG = "ck_tenant_settings_ck_tenant_settings_ticket_reopen_win_d493"
_NAMES = text(
    "SELECT conname FROM pg_constraint "
    "WHERE conrelid = 'tenant_settings'::regclass AND contype = 'c'"
)


def _checks(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {n for n in conn.execute(_NAMES).scalars() if "reopen_win" in n}


def _execute(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql))


def test_0221_renames_the_check_idempotently(database: Database, migrator_engine: Engine) -> None:
    config = alembic_config(database.migrator_url)
    try:
        command.downgrade(config, "0220")
        assert _checks(migrator_engine) == {WRONG}
        command.upgrade(config, "0221")
        assert _checks(migrator_engine) == {RIGHT}

        # Both names present (the right one added by hand): the wrong duplicate is dropped.
        command.downgrade(config, "0220")
        _execute(
            migrator_engine,
            f"ALTER TABLE tenant_settings ADD CONSTRAINT {RIGHT} "
            "CHECK (ticket_reopen_window_days BETWEEN 0 AND 3650)",
        )
        command.upgrade(config, "0221")
        assert _checks(migrator_engine) == {RIGHT}

        # No check at all: created under the right name, the range still holds.
        command.downgrade(config, "0220")
        _execute(migrator_engine, f"ALTER TABLE tenant_settings DROP CONSTRAINT {WRONG}")
        command.upgrade(config, "0221")
        assert _checks(migrator_engine) == {RIGHT}
        with migrator_engine.connect() as conn:
            definition = conn.execute(
                text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
                {"n": RIGHT},
            ).scalar_one()
        assert "3650" in definition

        # Right name only: nothing changes.
        command.downgrade(config, "0220")
        _execute(
            migrator_engine, f"ALTER TABLE tenant_settings RENAME CONSTRAINT {WRONG} TO {RIGHT}"
        )
        command.upgrade(config, "0221")
        assert _checks(migrator_engine) == {RIGHT}
    finally:
        command.upgrade(config, "head")
    command.check(config)
