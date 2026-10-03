"""AP04: currency column (GAL-101), NUMERIC(20,8) (GAL-102), encrypted deposit IBAN (GAL-108).

Revision ID: 0461
Revises: 0460

The deposit IBAN is re-encrypted in place with the tenant key (same format as
``mhvp.core.crypto.EncryptedText``); this needs ``MHVP_MASTER_KEY`` only when rows with a
deposit IBAN exist. The plaintext column is dropped afterwards.
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0461"
down_revision: str | None = "0460"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# GAL-101: header tables with amounts; the platform is EUR only (ADR 0038).
CURRENCY_TABLES = (
    "journal_entry",
    "open_item",
    "invoice",
    "hoa_statement",
    "deposit_movement",
    "payment_order",
)

# GAL-102: (table, column, old precision, old scale)
NUMERIC_COLUMNS = (
    ("rent_increase_case", "living_area_sqm", 10, 2),
    ("listing", "living_area_sqm", 10, 2),
    ("rent_index_entry", "area_from_sqm", 10, 2),
    ("rent_index_entry", "area_to_sqm", 10, 2),
    ("handover_meter", "value", 14, 3),
    ("objektakte_party_assignment", "share", 9, 6),
    ("deposit_interest_reference_rate", "rate", 8, 5),
    ("deposit_interest_rate", "rate", 8, 5),
    ("deposit_interest_draft", "rate", 8, 5),
    ("statement_advance_rule", "surcharge_percent", 5, 2),
    ("statement_advance_proposal", "surcharge_percent", 5, 2),
)

TABLE = "handover_protocol"


def _master_key() -> bytes:
    from mhvp.core.crypto import decode_master_key

    value = os.environ.get("MHVP_MASTER_KEY")
    if not value:
        raise RuntimeError("MHVP_MASTER_KEY is required to re-encrypt handover deposit IBANs")
    return decode_master_key(value)


def _normalised(value: str) -> str:
    from mhvp.contacts.validation import InvalidValueError, normalise_iban

    try:
        return normalise_iban(value)
    except InvalidValueError:
        return "".join(value.split()).upper()


def upgrade() -> None:
    for table in CURRENCY_TABLES:
        op.add_column(
            table,
            sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        )
        op.create_check_constraint(op.f(f"ck_{table}_currency_eur"), table, "currency = 'EUR'")

    for table, column, _p, _s in NUMERIC_COLUMNS:
        op.alter_column(table, column, type_=sa.Numeric(20, 8), existing_nullable=True)

    from mhvp.core import crypto

    op.add_column(TABLE, sa.Column("deposit_iban_enc", sa.LargeBinary()))
    op.add_column(TABLE, sa.Column("deposit_iban_fingerprint", sa.String(64)))
    op.add_column(TABLE, sa.Column("deposit_iban_suffix", sa.String(4)))
    bind = op.get_bind()
    op.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    rows = bind.execute(
        sa.text(
            "SELECT id, tenant_id, deposit_iban FROM handover_protocol "
            "WHERE deposit_iban IS NOT NULL"
        )
    ).all()
    master = _master_key() if rows else b""
    for row_id, tenant_id, iban in rows:
        scope = str(tenant_id)
        key = _normalised(iban)
        bind.execute(
            sa.text(
                "UPDATE handover_protocol SET deposit_iban_enc = :enc, "
                "deposit_iban_fingerprint = :fp, "
                "deposit_iban_suffix = :suffix WHERE id = :id"
            ),
            {
                "enc": crypto.encrypt_with_master(master, iban, scope),
                "fp": crypto.fingerprint_with_master(master, key, scope),
                "suffix": key[-4:],
                "id": row_id,
            },
        )
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.drop_column(TABLE, "deposit_iban")
    op.alter_column(TABLE, "deposit_iban_enc", new_column_name="deposit_iban")
    op.create_index(
        op.f("ix_handover_protocol_deposit_iban_fingerprint"),
        TABLE,
        ["deposit_iban_fingerprint"],
    )


def downgrade() -> None:
    from mhvp.core import crypto

    op.drop_index(op.f("ix_handover_protocol_deposit_iban_fingerprint"), table_name=TABLE)
    op.add_column(TABLE, sa.Column("deposit_iban_plain", sa.String(34)))
    bind = op.get_bind()
    op.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    rows = bind.execute(
        sa.text("SELECT id, deposit_iban FROM handover_protocol WHERE deposit_iban IS NOT NULL")
    ).all()
    master = _master_key() if rows else b""
    for row_id, blob in rows:
        bind.execute(
            sa.text("UPDATE handover_protocol SET deposit_iban_plain = :iban WHERE id = :id"),
            {"iban": crypto.decrypt_with_master(master, bytes(blob)), "id": row_id},
        )
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.drop_column(TABLE, "deposit_iban")
    op.drop_column(TABLE, "deposit_iban_fingerprint")
    op.drop_column(TABLE, "deposit_iban_suffix")
    op.alter_column(TABLE, "deposit_iban_plain", new_column_name="deposit_iban")

    for table, column, precision, scale in NUMERIC_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Numeric(precision, scale),
            existing_nullable=True,
            postgresql_using=f"round({column}, {scale})::numeric({precision},{scale})",
        )

    for table in CURRENCY_TABLES:
        op.drop_constraint(op.f(f"ck_{table}_currency_eur"), table, type_="check")
        op.drop_column(table, "currency")
