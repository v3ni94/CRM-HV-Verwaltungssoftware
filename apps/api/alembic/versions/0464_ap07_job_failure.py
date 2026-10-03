"""AP07 (GAM-504 to GAM-509): failure protocol of background jobs.

Table job_failure (tenant scoped, RLS) for failed tenant steps of scheduled jobs and table
task_failure (platform, no tenant column) for Celery tasks that failed for good. Only job key,
exception class and time are stored, no message text.

Revision ID: 0464
Revises: 0463
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0464"
down_revision: str | None = "0463"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_failure",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("job", sa.String(120), nullable=False),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_type", sa.String(200), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_job_failure_tenant_job", "job_failure", ["tenant_id", "job", "occurred_at"])
    for statement in tenant_rls_statements("job_failure"):
        op.execute(statement)
    op.create_table(
        "task_failure",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task", sa.String(200), nullable=False),
        sa.Column("error_type", sa.String(200), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_task_failure_occurred", "task_failure", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_task_failure_occurred", table_name="task_failure")
    op.drop_table("task_failure")
    for statement in drop_tenant_rls_statements("job_failure"):
        op.execute(statement)
    op.drop_index("ix_job_failure_tenant_job", table_name="job_failure")
    op.drop_table("job_failure")
