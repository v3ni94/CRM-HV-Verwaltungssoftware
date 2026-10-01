"""M17-04: tenant switches for the statement deadline (policy, warning job).

Revision ID: 0374
Revises: 0373
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import tenant_rls_statements

revision: str = "0374"
down_revision: str | None = "0373"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "statement_deadline_setting",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy", sa.String(16), nullable=False, server_default="block_claims"),
        sa.Column("watch_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("warn_days_first", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("warn_days_second", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_statement_deadline_setting_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", name="uq_statement_deadline_setting_tenant"),
        sa.CheckConstraint(
            "policy IN ('block_claims', 'notice')", name="ck_statement_deadline_setting_policy"
        ),
        sa.CheckConstraint(
            "warn_days_first > 0 AND warn_days_second > 0",
            name="ck_statement_deadline_setting_warn_days",
        ),
    )
    for statement in tenant_rls_statements("statement_deadline_setting"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("statement_deadline_setting")
