"""objektakte staging idempotency (Sicherheitsreview 2026-09-25, Befund 3): concurrent
imports of the same objektakte export could double-insert a row before the importer's own
existence check saw the other transaction's not-yet-committed insert. `objektakte_party_
assignment` and `objektakte_document_class` already had a unique constraint on (tenant_id,
source_system, source_id); this migration adds the missing `source_system` column plus the
same unique index to `objektakte_drive_node`, `objektakte_document_review_case` and
`objektakte_document_review_decision`. `source_id` stays nullable there (rows created outside
an objektakte takeover carry neither), so the index is partial (`source_id IS NOT NULL`) and
still allows any number of NULLs.

Revision ID: 0065
Revises: 0064
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065"
down_revision: str | None = "0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "objektakte_drive_node",
    "objektakte_document_review_case",
    "objektakte_document_review_decision",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "source_system", sa.String(length=32), nullable=False, server_default="objektakte"
            ),
        )
        op.alter_column(table, "source_system", server_default=None)
        op.create_index(
            f"ux_{table}_source",
            table,
            ["tenant_id", "source_system", "source_id"],
            unique=True,
            postgresql_where=sa.text("source_id IS NOT NULL"),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ux_{table}_source", table_name=table)
        op.drop_column(table, "source_system")
