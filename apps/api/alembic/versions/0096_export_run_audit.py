"""export_run_audit: status, parameters, error and finish time on ``export_run`` for the
machine readable audit export (A26, spec 7.7, case D55). Existing rows (journal CSV, DATEV
batch) were written synchronously and complete, so they read as ``status='done'`` with empty
parameters.

Revision ID: 0096
Revises: 0095
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0096"
down_revision: str | None = "0095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "export_run",
        sa.Column("status", sa.String(16), nullable=False, server_default="done"),
    )
    op.add_column(
        "export_run",
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("export_run", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("export_run", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("export_run", "finished_at")
    op.drop_column("export_run", "error")
    op.drop_column("export_run", "params")
    op.drop_column("export_run", "status")
