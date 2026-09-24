"""flow_import_run: FLOW SQL dump import previews (M28 stage 4, docs/rules/M28-01.md).

Revision ID: 0040
Revises: 0038 (TEMP, rebase onto 0039_mail_approval at merge)

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0040"
down_revision: str | None = "0038"  # TEMP: rebase onto 0039_mail_approval once merged
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("flow_import_run",)
ENUMS: tuple[str, ...] = ()


def upgrade() -> None:
    op.create_table(
        "flow_import_run",
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="previewed"),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "rows",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_flow_import_run_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_import_run")),
    )
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_table("flow_import_run")
    for enum in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
