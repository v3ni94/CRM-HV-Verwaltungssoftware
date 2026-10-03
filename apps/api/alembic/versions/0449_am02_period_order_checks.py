"""AM02 / GAJ-604: CHECK valid_to >= valid_from on five time-bound tables.

Each constraint is added NOT VALID and validated only when no existing row violates it; the
violation count is logged. FORCE RLS is lifted per table for the count only (pattern 0411).

Revision ID: 0449
Revises: 0448
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0449"
down_revision: str | None = "0448"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("property_owner", "property_contact", "contact_relation", "deposit", "majority_rule")
LOG = logging.getLogger("alembic.runtime.migration")
CONDITION = "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from"


def _name(table: str) -> str:
    return f"ck_{table}_period_order"


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        violations = bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE valid_to < valid_from")  # noqa: S608
        ).scalar_one()
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {_name(table)} CHECK ({CONDITION}) NOT VALID"
        )
        if violations == 0:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {_name(table)}")
        LOG.warning("0449 %s: %s violations, validated=%s", table, violations, violations == 0)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {_name(table)}")
