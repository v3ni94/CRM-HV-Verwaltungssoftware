"""AJ03 (GAI-209 to GAI-212, 7.1 B03/B04): database guards of migration 0444.

The guard functions are exercised on temporary copies of the tables (same columns, the same
trigger function), so no foreign key chain is needed; the period lock reads a real ledger and
the counter guard runs on the real ``journal_number_counter``. A last test checks that every
trigger is installed and enabled on the real table."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = [pytest.mark.integration]

IMMUTABLE = psycopg.errors.RaiseException


def _sync(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    settings = _settings(database, redis_url)

    async def build() -> World:
        from mhvp.core.db.engine import create_app_engine, create_session_factory

        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            tenant, _ = await services.provision_tenant(
                factory, slug=f"3-aj03-{RUN}", name=f"AJ03 Wache {RUN}"
            )
            w = World(
                tenant_a=tenant, tenant_b=tenant, app_url=settings.database_url.get_secret_value()
            )
            uid = await services.create_user(
                factory, email=w.email("aj03admin"), display_name="aj03", password=PASSWORD
            )
            w.users["aj03admin"] = uid
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


@pytest.fixture(scope="module")
def ledger_id(database: Database, redis_url: str, world: World) -> str:
    with TestClient(create_app(_settings(database, redis_url))) as client:
        headers = bearer(login(client, world, "aj03admin"))
        acc = "/api/v1/accounting"
        response = client.post(
            "/api/v1/properties",
            json={"number": "903", "name": "Wache AJ03", "management_type": "hoa"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        prop = response.json()
        entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
        template = client.post(f"{acc}/templates/default", json={}, headers=headers).json()
        response = client.post(
            f"{acc}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])


@pytest.fixture
def conn(database: Database, world: World) -> Iterator[psycopg.Connection]:
    """Migrator connection (temporary tables need the TEMP privilege), RLS still forced."""
    with psycopg.connect(_sync(database.migrator_url)) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, false)", (str(world.tenant_a),))
        yield connection
        connection.rollback()


def _copy(conn: psycopg.Connection, table: str, function: str) -> str:
    """Temporary copy of ``table`` without constraints, guarded by ``function``."""
    name = f"aj03_{table}"
    conn.execute(f"CREATE TEMP TABLE {name} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")
    conn.execute(
        f"CREATE TRIGGER g BEFORE UPDATE OR DELETE ON {name} "
        f"FOR EACH ROW EXECUTE FUNCTION {function}()"
    )
    return name


def _refused(conn: psycopg.Connection, sql: str) -> None:
    conn.execute("SAVEPOINT s")
    with pytest.raises(IMMUTABLE, match=r"immutable|locked|never decreases|in use"):
        conn.execute(sql)
    conn.execute("ROLLBACK TO SAVEPOINT s")


def test_open_item_only_open_fields_change(conn: psycopg.Connection) -> None:
    t = _copy(conn, "open_item", "mhvp_open_item_guard")
    conn.execute(
        f"INSERT INTO {t} (id, tenant_id, ledger_id, account_id, journal_entry_id, kind, "
        "booking_date, amount, written_off) VALUES (gen_random_uuid(), gen_random_uuid(), "
        "gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), 'receivable', "
        "'2026-01-31', 100.00, false)"
    )
    conn.execute(
        f"UPDATE {t} SET written_off = true, due_date = '2026-02-15', "
        "notice_received_on = '2026-02-01', contract_id = gen_random_uuid(), updated_at = now()"
    )
    for change in (
        "booking_date = '2026-03-01'",
        "kind = 'payable'",
        "component = 'reserve'",
        "amount = 99.99",
        "tenant_id = gen_random_uuid()",
        "contract_id = gen_random_uuid()",  # already set: no re-assignment
    ):
        _refused(conn, f"UPDATE {t} SET {change}")
    _refused(conn, f"DELETE FROM {t}")


def test_period_lock_refuses_posting_in_locked_period(
    conn: psycopg.Connection, ledger_id: str
) -> None:
    conn.execute("UPDATE ledger SET locked_until = '2026-06-30' WHERE id = %s", (ledger_id,))
    conn.execute(
        "CREATE TEMP TABLE aj03_entry (LIKE journal_entry INCLUDING DEFAULTS) ON COMMIT DROP"
    )
    conn.execute(
        "CREATE TRIGGER p BEFORE INSERT OR UPDATE ON aj03_entry "
        "FOR EACH ROW EXECUTE FUNCTION mhvp_journal_entry_period_lock()"
    )
    insert = (
        "INSERT INTO aj03_entry (id, tenant_id, ledger_id, status, booking_date, text, kind, "
        "source, settlement_plan) VALUES (gen_random_uuid(), gen_random_uuid(), %s, %s, %s, 'x', 'custom', "
        "'manual', '[]'::jsonb)"
    )
    conn.execute(insert, (ledger_id, "draft", "2026-06-30"))  # drafts are not refused
    conn.execute(insert, (ledger_id, "posted", "2026-07-01"))  # open period
    conn.execute("SAVEPOINT s")
    with pytest.raises(IMMUTABLE, match="locked until 2026-06-30"):
        conn.execute(insert, (ledger_id, "posted", "2026-06-30"))
    conn.execute("ROLLBACK TO SAVEPOINT s")
    _refused(conn, "UPDATE aj03_entry SET status = 'posted' WHERE status = 'draft'")
    # An already posted entry (e.g. setting reversed_by_id) is not checked again.
    conn.execute("UPDATE ledger SET locked_until = '2026-12-31' WHERE id = %s", (ledger_id,))
    conn.execute("UPDATE aj03_entry SET reversed_by_id = gen_random_uuid() WHERE status = 'posted'")


def test_payment_order_frozen_after_approval_stage(conn: psycopg.Connection) -> None:
    t = _copy(conn, "payment_order", "mhvp_payment_order_guard")
    conn.execute(
        f"INSERT INTO {t} (id, tenant_id, ledger_id, property_bank_account_id, kind, amount, "
        "discount, counterpart_name, counterpart_iban, counterpart_iban_fingerprint, purpose, "
        "end_to_end_id, execution_date, status) SELECT gen_random_uuid(), gen_random_uuid(), "
        "gen_random_uuid(), gen_random_uuid(), 'transfer', 10.00, 0, 'Payee', 'enc', 'fp', "
        "'Zweck', 'E2E', '2026-10-05', s::payment_order_status "
        "FROM unnest(ARRAY['draft', 'approved', 'exported']) s"
    )
    conn.execute(f"UPDATE {t} SET amount = 12.00 WHERE status IN ('draft', 'approved')")
    conn.execute(
        f"UPDATE {t} SET status = 'submitted', bank_status_reason_code = 'ACSC' "
        "WHERE status = 'exported'"
    )
    for change in (
        "amount = 11.00",
        "counterpart_iban_fingerprint = 'x'",
        "purpose = 'y'",
        "execution_date = '2026-11-01'",
    ):
        _refused(conn, f"UPDATE {t} SET {change} WHERE status = 'submitted'")
    _refused(conn, f"DELETE FROM {t} WHERE status = 'approved'")
    conn.execute(f"DELETE FROM {t} WHERE status = 'draft'")


def test_deposit_movement_insert_only(conn: psycopg.Connection) -> None:
    t = _copy(conn, "deposit_movement", "mhvp_deposit_movement_guard")
    conn.execute(
        f"INSERT INTO {t} (id, tenant_id, deposit_id, date, amount, kind) VALUES "
        "(gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), '2026-01-01', 500.00, "
        "'payment')"
    )
    conn.execute(f"UPDATE {t} SET posting_id = gen_random_uuid()")  # first link to the ledger
    for change in (
        "posting_id = gen_random_uuid()",
        "amount = 1.00",
        "date = '2026-02-01'",
        "reason = 'x'",
    ):
        _refused(conn, f"UPDATE {t} SET {change}")
    _refused(conn, f"DELETE FROM {t}")


def test_receivable_item_status_protection(conn: psycopg.Connection) -> None:
    t = _copy(conn, "receivable_item", "mhvp_receivable_item_guard")
    conn.execute(
        f"INSERT INTO {t} (id, tenant_id, run_id, contract_id, period_month, payment_type_code, "
        "amount, vat_percent, status) SELECT gen_random_uuid(), gen_random_uuid(), "
        "gen_random_uuid(), gen_random_uuid(), '2026-01-01', 'rent', 100.00, 0, "
        "s::receivable_item_status FROM unnest(ARRAY['ready', 'posted']) s"
    )
    conn.execute(f"UPDATE {t} SET amount = 90.00 WHERE status = 'ready'")  # preview is free
    conn.execute(f"DELETE FROM {t} WHERE status = 'ready'")
    _refused(conn, f"UPDATE {t} SET amount = 1.00")
    _refused(conn, f"UPDATE {t} SET status = 'ready'")
    _refused(conn, f"DELETE FROM {t}")
    conn.execute(f"UPDATE {t} SET status = 'reversed', message = 'Storno'")
    _refused(conn, f"UPDATE {t} SET status = 'posted'")
    _refused(conn, f"DELETE FROM {t}")


def test_journal_number_counter_never_decreases(
    conn: psycopg.Connection, world: World, ledger_id: str
) -> None:
    conn.execute(
        "INSERT INTO journal_number_counter (tenant_id, ledger_id, fiscal_year, last_number) "
        "VALUES (%s, %s, 2099, 0)",
        (str(world.tenant_a), ledger_id),
    )
    conn.execute("DELETE FROM journal_number_counter WHERE fiscal_year = 2099")  # unused
    conn.execute(
        "INSERT INTO journal_number_counter (tenant_id, ledger_id, fiscal_year, last_number) "
        "VALUES (%s, %s, 2099, 0)",
        (str(world.tenant_a), ledger_id),
    )
    conn.execute("UPDATE journal_number_counter SET last_number = 5 WHERE fiscal_year = 2099")
    _refused(conn, "UPDATE journal_number_counter SET last_number = 4 WHERE fiscal_year = 2099")
    _refused(conn, "UPDATE journal_number_counter SET fiscal_year = 2098 WHERE fiscal_year = 2099")
    _refused(conn, "DELETE FROM journal_number_counter WHERE fiscal_year = 2099")


def test_triggers_installed_and_enabled(conn: psycopg.Connection) -> None:
    rows = dict(
        conn.execute(
            "SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = ANY(%s)",
            (
                [
                    "open_item_guard",
                    "journal_entry_period_lock",
                    "payment_order_guard",
                    "deposit_movement_guard",
                    "receivable_item_guard",
                    "journal_number_counter_guard",
                ],
            ),
        ).fetchall()
    )
    assert len(rows) == 6, rows
    assert set(rows.values()) == {"O"}, rows
