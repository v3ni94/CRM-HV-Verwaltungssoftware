"""workspace_jobs: tables of the daily jobs tasks.digest (A40) and compliance.deadlines (A41):
job switches per tenant, digest idempotency marker per user and day, deadline list.

Revision ID: 0101
Revises: 0100
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0101"
down_revision: str | None = "0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("workspace_job_settings", "digest_run", "compliance_deadline")


def upgrade() -> None:
    op.create_table(
        "workspace_job_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "digest_mail_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deadline_lead_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_workspace_job_settings_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_job_settings")),
        sa.UniqueConstraint("tenant_id", name="uq_workspace_job_settings_tenant"),
    )
    op.create_table(
        "digest_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mail_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_digest_run_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_digest_run_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digest_run")),
        sa.UniqueConstraint("tenant_id", "user_id", "digest_date", name="uq_digest_run_day"),
    )
    op.create_table(
        "compliance_deadline",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=300), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_compliance_deadline_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_deadline")),
        sa.UniqueConstraint(
            "tenant_id", "kind", "source_id", "due_on", name="uq_compliance_deadline_source"
        ),
    )
    op.create_index(
        "ix_compliance_deadline_due", "compliance_deadline", ["tenant_id", "status", "due_on"]
    )
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_compliance_deadline_due", table_name="compliance_deadline")
    op.drop_table("compliance_deadline")
    op.drop_table("digest_run")
    op.drop_table("workspace_job_settings")
