"""AO04 / GAK-205: migration 0457 round trip with the takeover from snapshot.terms."""

import json

import pytest
from alembic import command
from sqlalchemy import Engine, text

from tests.integration.conftest import Database, alembic_config

pytestmark = pytest.mark.integration

_COLUMNS = text(
    "SELECT count(*) FROM information_schema.columns WHERE table_name = 'special_levy' "
    "AND column_name IN ('revenue_account_id', 'reference_date')"
)


def _no_force(conn: object) -> None:
    conn.execute(text("ALTER TABLE special_levy NO FORCE ROW LEVEL SECURITY"))  # type: ignore[attr-defined]


def _set_terms(engine: Engine, levy: object, terms: dict[str, str]) -> None:
    with engine.begin() as conn:
        _no_force(conn)
        conn.execute(
            text("UPDATE special_levy SET snapshot = CAST(:s AS jsonb) WHERE id = :i"),
            {"s": json.dumps({"terms": terms}), "i": levy},
        )
        conn.execute(text("ALTER TABLE special_levy FORCE ROW LEVEL SECURITY"))


def _columns(engine: Engine, levy: object) -> tuple[object, object]:
    with engine.begin() as conn:
        _no_force(conn)
        got = conn.execute(
            text("SELECT revenue_account_id, reference_date FROM special_levy WHERE id = :i"),
            {"i": levy},
        ).one()
        conn.execute(text("ALTER TABLE special_levy FORCE ROW LEVEL SECURITY"))
    return got[0], got[1]


def test_round_trip_takes_terms_over(database: Database, migrator_engine: Engine) -> None:
    config = alembic_config(database.migrator_url)
    command.upgrade(config, "head")
    with migrator_engine.begin() as conn:
        _no_force(conn)
        conn.execute(text("ALTER TABLE ledger_account NO FORCE ROW LEVEL SECURITY"))
        row = conn.execute(
            text(
                "SELECT s.id, s.first_due, a.id FROM special_levy s "
                "JOIN ledger_account a ON a.ledger_id = s.ledger_id AND a.tenant_id = s.tenant_id "
                "LIMIT 1"
            )
        ).first()
        conn.execute(text("ALTER TABLE ledger_account FORCE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE special_levy FORCE ROW LEVEL SECURITY"))
    if row is None:
        pytest.skip("needs a special levy with ledger accounts (run with test_an19 first)")
    levy, first_due, account = row

    # Valid terms are taken over into the columns.
    command.downgrade(config, "0456")
    with migrator_engine.connect() as conn:
        assert conn.execute(_COLUMNS).scalar_one() == 0
    _set_terms(
        migrator_engine,
        levy,
        {"revenue_account_id": str(account), "reference_date": first_due.isoformat()},
    )
    command.upgrade(config, "head")
    with migrator_engine.connect() as conn:
        assert conn.execute(_COLUMNS).scalar_one() == 2
    assert _columns(migrator_engine, levy) == (account, first_due)

    # Unknown account and a reference date after the first due date stay NULL.
    command.downgrade(config, "0456")
    _set_terms(
        migrator_engine, levy, {"revenue_account_id": str(levy), "reference_date": "2999-01-01"}
    )
    command.upgrade(config, "head")
    assert _columns(migrator_engine, levy) == (None, None)

    with migrator_engine.begin() as conn:
        _no_force(conn)
        with pytest.raises(Exception, match="reference_date_order"), conn.begin_nested():
            conn.execute(
                text("UPDATE special_levy SET reference_date = first_due + 1 WHERE id = :i"),
                {"i": levy},
            )
        conn.execute(text("ALTER TABLE special_levy FORCE ROW LEVEL SECURITY"))
