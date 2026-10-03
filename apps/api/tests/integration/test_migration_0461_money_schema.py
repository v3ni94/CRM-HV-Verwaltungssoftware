"""AP04: migration 0461 round trip (GAL-101, GAL-102, GAL-108) with the IBAN takeover."""

import base64
import os
import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from mhvp.core import crypto
from tests.integration.conftest import Database, alembic_config

pytestmark = pytest.mark.integration

IBAN = "DE89 3704 0044 0532 0130 00"
NORMALISED = "DE89370400440532013000"


def _type(engine: Engine, table: str, column: str) -> tuple[int, int]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).one()
    return int(row[0]), int(row[1])


def _protocol(engine: Engine, protocol: uuid.UUID) -> tuple[object, object, object]:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE handover_protocol NO FORCE ROW LEVEL SECURITY"))
        row = conn.execute(
            text(
                "SELECT deposit_iban, deposit_iban_fingerprint, deposit_iban_suffix "
                "FROM handover_protocol WHERE id = :i"
            ),
            {"i": protocol},
        ).one()
        conn.execute(text("ALTER TABLE handover_protocol FORCE ROW LEVEL SECURITY"))
    return row[0], row[1], row[2]


def test_round_trip_encrypts_deposit_iban(
    database: Database, migrator_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    master = os.urandom(32)
    monkeypatch.setenv("MHVP_MASTER_KEY", base64.b64encode(master).decode())
    config = alembic_config(database.migrator_url)
    previous = ScriptDirectory.from_config(config).get_revision("0461").down_revision
    assert isinstance(previous, str)
    command.upgrade(config, "0461")
    command.downgrade(config, previous)
    assert _type(migrator_engine, "statement_advance_rule", "surcharge_percent") == (5, 2)

    protocol = uuid.uuid4()
    with migrator_engine.begin() as conn:
        tenant = conn.execute(text("SELECT id FROM tenant LIMIT 1")).scalar()
        if tenant is None:
            pytest.skip("needs a tenant (run make seed or any tenant test first)")
        conn.execute(text("ALTER TABLE handover_protocol NO FORCE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                "INSERT INTO handover_protocol (id, tenant_id, number, version, kind, status, "
                "current_step, deposit_iban) VALUES (:i, :t, :n, 1, 'move_out', 'draft', "
                "'basics', :iban)"
            ),
            {"i": protocol, "t": tenant, "n": f"AP04-{protocol.hex[:8]}", "iban": IBAN},
        )
        conn.execute(text("ALTER TABLE handover_protocol FORCE ROW LEVEL SECURITY"))
    try:
        command.upgrade(config, "0461")
        blob, fingerprint, suffix = _protocol(migrator_engine, protocol)
        assert isinstance(blob, (bytes, memoryview))
        assert IBAN.encode() not in bytes(blob)
        assert crypto.ciphertext_scope(bytes(blob)) == str(tenant)
        assert crypto.decrypt_with_master(master, bytes(blob)) == IBAN
        assert fingerprint == crypto.fingerprint_with_master(master, NORMALISED, str(tenant))
        assert suffix == "3000"
        assert _type(migrator_engine, "statement_advance_rule", "surcharge_percent") == (20, 8)
        assert _type(migrator_engine, "objektakte_party_assignment", "share") == (20, 8)
        with migrator_engine.connect() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE column_name = 'currency' AND table_name IN "
                        "('journal_entry', 'open_item', 'invoice', "
                        "'hoa_statement', 'deposit_movement', 'payment_order')"
                    )
                ).scalar_one()
                == 6
            )

        # Back down: plaintext restored, then up again.
        command.downgrade(config, previous)
        assert _protocol_plain(migrator_engine, protocol) == IBAN
        command.upgrade(config, "0461")
    finally:
        command.upgrade(config, "0461")
        with migrator_engine.begin() as conn:
            conn.execute(text("ALTER TABLE handover_protocol NO FORCE ROW LEVEL SECURITY"))
            conn.execute(text("DELETE FROM handover_protocol WHERE id = :i"), {"i": protocol})
            conn.execute(text("ALTER TABLE handover_protocol FORCE ROW LEVEL SECURITY"))


def _protocol_plain(engine: Engine, protocol: uuid.UUID) -> object:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE handover_protocol NO FORCE ROW LEVEL SECURITY"))
        value = conn.execute(
            text("SELECT deposit_iban FROM handover_protocol WHERE id = :i"), {"i": protocol}
        ).scalar_one()
        conn.execute(text("ALTER TABLE handover_protocol FORCE ROW LEVEL SECURITY"))
    return value


def test_currency_check_rejects_other_currency(migrator_engine: Engine) -> None:
    with migrator_engine.connect() as conn:
        definition = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_invoice_currency_eur'"
            )
        ).scalar_one()
    assert "EUR" in definition
