"""M24-01 (wave 5): earmarked reserve per position, bank investment and opening balance.

``hoa_reserve`` gets ``bank_account_id`` (bank account of the ledger's legal entity),
``opening_balance`` (entered balance at the start of ``opening_year``) and ``opening_year``.
The reserve binding of migration 0278 stays unchanged. Idempotent.

Revision ID: 0294
Revises: 0293
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0294"
down_revision: str | None = "0293"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "hoa_reserve"


def _has_column(column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column("bank_account_id"):
        op.add_column(TABLE, sa.Column("bank_account_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f("fk_hoa_reserve_bank_account_id_property_bank_account"),
            TABLE,
            "property_bank_account",
            ["bank_account_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _has_column("opening_balance"):
        op.add_column(
            TABLE,
            sa.Column(
                "opening_balance",
                sa.Numeric(14, 2),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if not _has_column("opening_year"):
        op.add_column(TABLE, sa.Column("opening_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "opening_year")
    op.drop_column(TABLE, "opening_balance")
    op.drop_constraint(
        "fk_hoa_reserve_bank_account_id_property_bank_account", TABLE, type_="foreignkey"
    )
    op.drop_column(TABLE, "bank_account_id")
