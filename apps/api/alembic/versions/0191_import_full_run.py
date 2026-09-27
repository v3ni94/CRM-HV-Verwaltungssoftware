"""import_full_run: full import and reconciliation of the Immoware24 exports with cut-off
date (M8-01, M8-02, V9). One row per stored run: files with SHA-256 and row counts, per
entity target/actual report with difference list, opening balance proposals as draft (G1
closed, nothing is posted).

Revision ID: 0191
Revises: 0190
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0191"
down_revision: str | None = "0190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "import_full_run"
ENUM_NAME = "import_full_run_status"
_STATUS = postgresql.ENUM("preview", "applied", "reconciled", name=ENUM_NAME)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table(TABLE):
        return
    _STATUS.create(op.get_bind(), checkfirst=True)
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "status",
            postgresql.ENUM("preview", "applied", "reconciled", name=ENUM_NAME, create_type=False),
            nullable=False,
        ),
        sa.Column("cutoff_date", sa.Date(), nullable=False),
        sa.Column("files", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("counts", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("report", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("opening_balances", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("differences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_run_id"], ["import_run.id"], ondelete="SET NULL"),
    )
    op.create_index(f"ix_{TABLE}_tenant_created", TABLE, ["tenant_id", "created_at"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
    _STATUS.drop(op.get_bind(), checkfirst=True)
