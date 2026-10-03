"""AP05 (GAL-104 to GAL-107): guards, author columns and CHECKs of migration 0462.

The trigger functions run on temporary copies of the tables (pattern ``test_aj03``): insert is
allowed, update and delete are refused. The reserve movement guard reads ``hoa_statement``;
a temporary table of that name shadows the real one (``pg_temp`` comes first in the search
path), so no foreign key chain is needed. CHECKs are exercised on copies that include the
constraints. A last block checks installation on the real tables and the round trip."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from alembic import command

from tests.integration.conftest import Database, alembic_config

pytestmark = [pytest.mark.integration]

IMMUTABLE = psycopg.errors.RaiseException
CHECK = psycopg.errors.CheckViolation
U = "gen_random_uuid()"


def _sync(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def conn(database: Database) -> Iterator[psycopg.Connection]:
    with psycopg.connect(_sync(database.migrator_url)) as connection:
        yield connection
        connection.rollback()


def _copy(conn: psycopg.Connection, table: str, function: str | None = None) -> str:
    name = f"ap05_{table}"
    conn.execute(
        f"CREATE TEMP TABLE {name} (LIKE {table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS) "
        "ON COMMIT DROP"
    )
    if function:
        conn.execute(
            f"CREATE TRIGGER g BEFORE UPDATE OR DELETE ON {name} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )
    return name


def _refused(conn: psycopg.Connection, sql: str, error: type[Exception] = IMMUTABLE) -> None:
    conn.execute("SAVEPOINT s")
    with pytest.raises(error):
        conn.execute(sql)
    conn.execute("ROLLBACK TO SAVEPOINT s")


# GAL-104 -------------------------------------------------------------------------------------


def test_approval_decision_only_first_invalidation(conn: psycopg.Connection) -> None:
    t = _copy(conn, "approval_decision", "mhvp_approval_decision_guard")
    conn.execute(
        f"INSERT INTO {t} (id, tenant_id, subject_type, subject_id, step, user_id, "
        f"subject_snapshot_hash, status, decided_at, warnings) VALUES ({U}, {U}, 'invoice', "
        f"{U}, 'release', {U}, 'h', 'valid', now(), '{{}}')"
    )
    for change in ("subject_snapshot_hash = 'x'", f"user_id = {U}"):
        _refused(conn, f"UPDATE {t} SET {change}")
    _refused(conn, f"DELETE FROM {t}")
    conn.execute(
        f"UPDATE {t} SET status = 'invalidated', invalidated_at = now(), "
        "invalidation_reason = 'changed'"
    )
    _refused(conn, f"UPDATE {t} SET invalidation_reason = 'other'")
    _refused(conn, f"UPDATE {t} SET status = 'valid'")


@pytest.mark.parametrize("table", ["migrated_journal_line", "statement_event"])
def test_insert_only_tables(conn: psycopg.Connection, table: str) -> None:
    t = _copy(conn, table, "mhvp_insert_only_guard")
    if table == "migrated_journal_line":
        conn.execute(
            f"INSERT INTO {t} (id, tenant_id, entry_id, line_no, account_number, debit, credit, "
            f"raw) VALUES ({U}, {U}, {U}, 1, '1000', 10.00, 0, '{{}}')"
        )
        change = "debit = 11.00"
    else:
        conn.execute(
            f"INSERT INTO {t} (id, tenant_id, statement_id, from_status, to_status, created_at) "
            f"VALUES ({U}, {U}, {U}, 'draft', 'calculated', now())"
        )
        change = "to_status = 'posted'"
    _refused(conn, f"UPDATE {t} SET {change}")
    _refused(conn, f"DELETE FROM {t}")


def test_reserve_movement_frozen_after_calculation(conn: psycopg.Connection) -> None:
    conn.execute("CREATE TEMP TABLE hoa_statement (id uuid, status text) ON COMMIT DROP")
    conn.execute(
        "INSERT INTO pg_temp.hoa_statement VALUES "
        "('00000000-0000-0000-0000-000000000001', 'draft'), "
        "('00000000-0000-0000-0000-000000000002', 'calculated')"
    )
    t = _copy(conn, "hoa_reserve_movement", "mhvp_hoa_reserve_movement_guard")
    for n in (1, 2):
        conn.execute(
            f"INSERT INTO {t} (id, tenant_id, statement_id, reserve_id, kind, amount, purpose) "
            f"VALUES ({U}, {U}, '00000000-0000-0000-0000-00000000000{n}', {U}, 'withdrawal', "
            "100.00, 'Dach')"
        )
    calculated = "statement_id = '00000000-0000-0000-0000-000000000002'"
    _refused(conn, f"UPDATE {t} SET amount = 1.00 WHERE {calculated}")
    _refused(conn, f"DELETE FROM {t} WHERE {calculated}")
    draft = "statement_id = '00000000-0000-0000-0000-000000000001'"
    conn.execute(f"UPDATE {t} SET amount = 1.00 WHERE {draft}")
    conn.execute(f"DELETE FROM {t} WHERE {draft}")


def test_bank_transaction_money_fields_frozen(conn: psycopg.Connection) -> None:
    t = _copy(conn, "bank_transaction", "mhvp_bank_transaction_guard")
    conn.execute(
        f"INSERT INTO {t} (id, tenant_id, property_bank_account_id, legal_entity_id, "
        f"booking_date, amount, currency, hash, raw, status, attempt) VALUES ({U}, {U}, {U}, "
        f"{U}, '2026-01-02', 50.00, 'EUR', 'h1', '{{}}', 'new', 0)"
    )
    conn.execute(f"UPDATE {t} SET journal_entry_id = {U}, counterpart_name = 'X'")
    for change in (
        "amount = 49.99",
        "booking_date = '2026-01-03'",
        "value_date = '2026-01-03'",
        "bank_reference = 'R'",
        "end_to_end_id = 'E'",
        "mandate_reference = 'M'",
        "hash = 'h2'",
        f"property_bank_account_id = {U}",
    ):
        _refused(conn, f"UPDATE {t} SET {change}")
    _refused(conn, f"DELETE FROM {t}")


# GAL-106 / GAL-107 ---------------------------------------------------------------------------


def test_access_grant_checks(conn: psycopg.Connection) -> None:
    t = _copy(conn, "access_grant")
    cols = (
        '(id, tenant_id, account_id, scope_type, scope_id, "right", legal_basis, role, '
        "valid_from, valid_to)"
    )

    def row(
        scope: str = "unit",
        right: str = "read",
        basis: str = "contract",
        role: str = "tenant",
        to: str = "NULL",
    ) -> str:
        return (
            f"INSERT INTO {t} {cols} VALUES ({U}, {U}, {U}, '{scope}', {U}, '{right}', "
            f"'{basis}', '{role}', '2026-01-01', {to})"
        )

    conn.execute(row(to="'2026-01-01'"))
    for bad in (
        row(to="'2025-12-31'"),
        row(scope="everything"),
        row(right="delete"),
        row(basis="free text"),
        row(role="admin"),
    ):
        _refused(conn, bad, CHECK)


@pytest.mark.parametrize("table", ["economic_plan", "hoa_statement", "reserve_statement"])
def test_resolved_needs_resolution(conn: psycopg.Connection, table: str) -> None:
    conn.execute(
        f"CREATE TEMP TABLE ap05_{table} (status statement_status, resolution_id uuid) "
        "ON COMMIT DROP"
    )
    condef = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (f"ck_{table}_resolved_needs_resolution",),
    ).fetchone()
    assert condef is not None
    conn.execute(f"ALTER TABLE ap05_{table} ADD CONSTRAINT c {condef[0]}")
    conn.execute(f"INSERT INTO ap05_{table} VALUES ('internally_approved', NULL)")
    conn.execute(f"INSERT INTO ap05_{table} VALUES ('resolved', {U})")
    for status in ("resolved", "issued", "posted", "locked"):
        _refused(conn, f"INSERT INTO ap05_{table} VALUES ('{status}', NULL)", CHECK)


def test_active_bank_rule_needs_release(conn: psycopg.Connection) -> None:
    t = _copy(conn, "bank_rule")
    base = (
        f"INSERT INTO {t} (id, tenant_id, name, legal_entity_id, match, action, priority, "
        "hit_count, learned_from_ai, contradiction_count, approval_state, approved_by, "
        "approved_at, max_amount, test_evidence_document_id) VALUES "
        f"({U}, {U}, 'r', {U}, '{{}}', '{{}}', 1, 0, false, 0, "
    )
    conn.execute(base + "'approved', NULL, NULL, NULL, NULL)")
    conn.execute(base + f"'active', {U}, now(), 500.00, {U})")
    for bad in (
        f"'active', NULL, now(), 500.00, {U})",
        f"'active', {U}, now(), 0, {U})",
        f"'active', {U}, now(), 500.00, NULL)",
        f"'active', {U}, NULL, 500.00, {U})",
    ):
        _refused(conn, base + bad, CHECK)


# Installation and round trip -----------------------------------------------------------------


def test_installed_on_real_tables(conn: psycopg.Connection) -> None:
    rows = dict(
        conn.execute(
            "SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = ANY(%s)",
            (
                [
                    "approval_decision_guard",
                    "migrated_journal_line_guard",
                    "statement_event_guard",
                    "hoa_reserve_movement_guard",
                    "bank_transaction_guard",
                ],
            ),
        ).fetchall()
    )
    assert len(rows) == 5, rows
    assert set(rows.values()) == {"O"}, rows
    count = conn.execute(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND "
        "table_name IN ('hoa_reserve_movement', 'economic_plan_item', 'hoa_cost_item', "
        "'invoice_line', 'role_permission', 'membership_role') AND column_name IN "
        "('created_at', 'updated_at', 'created_by', 'updated_by')"
    ).fetchone()
    assert count == (24,)


def test_round_trip(database: Database) -> None:
    config = alembic_config(database.migrator_url)
    command.downgrade(config, "0461")
    with psycopg.connect(_sync(database.migrator_url)) as c:
        gone = c.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'bank_transaction_guard'"
        ).fetchone()
    assert gone == (0,)
    command.upgrade(config, "0462")
    with psycopg.connect(_sync(database.migrator_url)) as c:
        back = c.execute(
            "SELECT count(*) FROM pg_constraint WHERE conname LIKE 'ck_%%' AND convalidated "
            "AND conname = ANY(%s)",
            (["ck_access_grant_role_values", "ck_bank_rule_active_needs_release"],),
        ).fetchone()
    assert back == (2,)
    command.upgrade(config, "head")
