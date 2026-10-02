"""AI02 (GAH-103, 6.9.3, B03): statement_snapshot is insert only (database guard).

Reuses ``mhvp_insert_only()`` from 0010 (same guard as open_item_settlement).

Revision ID: 0439
Revises: 0438
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0439"
down_revision: str | None = "0438"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER statement_snapshot_insert_only BEFORE UPDATE OR DELETE "
        "ON statement_snapshot FOR EACH ROW EXECUTE FUNCTION mhvp_insert_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS statement_snapshot_insert_only ON statement_snapshot")
