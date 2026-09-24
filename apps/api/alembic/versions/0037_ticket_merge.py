"""ticket_merge: merged_into_ticket_id on ticket for the merge endpoint (M6).

Revision ID: 0037
Revises: 0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ticket", sa.Column("merged_into_ticket_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_ticket_merged_into_ticket_id_ticket"),
        "ticket",
        "ticket",
        ["merged_into_ticket_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_ticket_merged_into_ticket_id_ticket"), "ticket", type_="foreignkey")
    op.drop_column("ticket", "merged_into_ticket_id")
