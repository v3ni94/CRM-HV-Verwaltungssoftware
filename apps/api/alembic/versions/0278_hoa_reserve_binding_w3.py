"""WEG gaps of wave 3 (Lückenliste 30.09.2026): M24-01, M25-07, SA-08.

* ``contract_payment.reserve_id`` and ``receivable_item.reserve_id``: earmarked reserve the
  standing amount and its receivable item are bound to (Zweckbindung der Sollstellung, W08).
* ``statement_kind``: values ``special_levy`` and ``heating`` (annex A.1 attribute "Art der
  Abrechnung", SA-08). Values of a PostgreSQL enum are not removed on downgrade.
* ``hoa_inspection_event``: kinds ``notified`` and ``owner_check`` (M25-07, PÜ13).

Idempotent: every step checks the catalogue first.

Revision ID: 0278
Revises: 0277
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0278"
down_revision: str | None = "0277"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT = "hoa_inspection_event"
BOUND = ("contract_payment", "receivable_item")


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table in BOUND:
        if not _has_column(table, "reserve_id"):
            op.add_column(table, sa.Column("reserve_id", sa.Uuid(), nullable=True))
            op.create_foreign_key(
                op.f(f"fk_{table}_reserve_id_hoa_reserve"),
                table,
                "hoa_reserve",
                ["reserve_id"],
                ["id"],
                ondelete="SET NULL",
            )
            if table == "contract_payment":
                # contracts.models._fk indexes every foreign key column.
                op.create_index(
                    op.f("ix_contract_payment_reserve_id"), table, ["reserve_id"], unique=False
                )
    with op.get_context().autocommit_block():
        for value in ("special_levy", "heating"):
            op.execute(f"ALTER TYPE statement_kind ADD VALUE IF NOT EXISTS '{value}'")
    # Migration 0257 re-created the constraint under a doubled prefix; both names are dropped
    # and the ORM name (naming convention applied to "kind") is restored.
    for name in (f"ck_{EVENT}_kind", f"ck_{EVENT}_ck_{EVENT}_kind"):
        op.execute(f"ALTER TABLE {EVENT} DROP CONSTRAINT IF EXISTS {name}")
    op.create_check_constraint(
        "kind",
        EVENT,
        "kind IN ('status', 'note', 'package', 'retrieval', 'revoked', 'notified', 'owner_check')",
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {EVENT} WHERE kind IN ('notified', 'owner_check')")  # noqa: S608
    op.drop_constraint("kind", EVENT, type_="check")
    # Restore the doubled name that 0257 created (its downgrade drops exactly that name).
    op.create_check_constraint(
        f"ck_{EVENT}_kind",
        EVENT,
        "kind IN ('status', 'note', 'package', 'retrieval', 'revoked')",
    )
    for table in BOUND:
        if table == "contract_payment":
            # IF EXISTS: a database that got the column from an earlier draft has no index.
            op.execute("DROP INDEX IF EXISTS ix_contract_payment_reserve_id")
        op.drop_constraint(f"fk_{table}_reserve_id_hoa_reserve", table, type_="foreignkey")
        op.drop_column(table, "reserve_id")
