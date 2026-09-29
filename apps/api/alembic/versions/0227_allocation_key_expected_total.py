"""Expected total per allocation key (package C1, Stammdaten in der Oberfläche).

``allocation_key.expected_total`` (NUMERIC(20,8), nullable, no default) is the operator entered
reference sum of a key within a property, for example the total of the Miteigentumsanteile
according to the Teilungserklärung. The CRM compares the sum of the unit values at a reference
date with it and shows a warning only; nothing is blocked or derived (docs/OPEN_QUESTIONS.md
C1-01). No legal value is assumed, the column stays empty until the operator enters one.

Revision ID: 0227
Revises: 0225
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0227"
down_revision: str | None = "0225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "allocation_key"
COLUMN = "expected_total"
CHECK = "ck_allocation_key_expected_total_non_negative"


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if COLUMN not in _columns(TABLE):
        op.add_column(TABLE, sa.Column(COLUMN, sa.Numeric(20, 8), nullable=True))
        op.create_check_constraint(CHECK, TABLE, f"{COLUMN} IS NULL OR {COLUMN} >= 0")


def downgrade() -> None:
    if COLUMN in _columns(TABLE):
        op.drop_constraint(CHECK, TABLE, type_="check")
        op.drop_column(TABLE, COLUMN)
