"""AE10 / AA07-01: allocation variant per acquisition kind (tenant rule, default manual release).

Revision ID: 0366
Revises: 0365
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0366"
down_revision: str | None = "0365"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "hoa_acquisition_rule"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("acquisition_kind", sa.String(32), nullable=False),
        sa.Column(
            "allocation_variant", sa.String(24), server_default="manual_release", nullable=False
        ),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "allocation_variant IN ('manual_release', 'by_due_date', 'by_resolution_date')",
            name=op.f("ck_hoa_acquisition_rule_allocation_variant_values"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_hoa_acquisition_rule_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_acquisition_rule")),
        sa.UniqueConstraint("tenant_id", "acquisition_kind", name="uq_hoa_acquisition_rule_kind"),
    )
    op.create_index("ix_hoa_acquisition_rule_tenant_id", TABLE, ["tenant_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
