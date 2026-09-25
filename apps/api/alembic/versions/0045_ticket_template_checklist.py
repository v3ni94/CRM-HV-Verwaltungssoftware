"""ticket_template_checklist: structured checklist items and extra fields (with IBAN support)
on ticket_template; ticket gains extra_fields values and structured checklist entries with
done_by/done_at (M19, docs/plans/M19.md, 25.09.2026).

Revision ID: 0045
Revises: 0044
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ticket_template", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "ticket_template",
        sa.Column("extra_fields", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "ticket_template",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "ticket",
        sa.Column("extra_fields", postgresql.JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("ticket", "extra_fields")
    op.drop_column("ticket_template", "active")
    op.drop_column("ticket_template", "extra_fields")
    op.drop_column("ticket_template", "description")
