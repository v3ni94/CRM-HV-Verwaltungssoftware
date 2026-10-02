"""GAE-02 (AE20): period locks may stem from a closed WEG statement (source hoa_statement).

Widens the check constraint ``ck_period_lock_source``; no data change on upgrade. The downgrade
keeps hoa_statement locks as source statement.

Revision ID: 0398
Revises: 0397
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0398"
down_revision: str | None = "0397"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_period_lock_source"), "period_lock", type_="check")
    op.create_check_constraint(
        op.f("ck_period_lock_source"),
        "period_lock",
        "source IN ('manual', 'statement', 'owner_statement', 'hoa_statement')",
    )


def downgrade() -> None:
    # The migrator is subject to FORCE ROW LEVEL SECURITY and would see no rows, so the
    # narrowed check would fail on existing hoa_statement locks. FORCE is lifted for this
    # transaction only and restored right after. The lock itself is kept (source statement),
    # a period lock is never silently dropped.
    op.execute("ALTER TABLE period_lock NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE period_lock SET source = 'statement' WHERE source = 'hoa_statement'")
    op.execute("ALTER TABLE period_lock FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_period_lock_source"), "period_lock", type_="check")
    op.create_check_constraint(
        op.f("ck_period_lock_source"),
        "period_lock",
        "source IN ('manual', 'statement', 'owner_statement')",
    )
