"""AG20 (GAE-12, W07, P01): tenant switch for the allocation proposal of the statement result.

* ``hoa_allocation_proposal_setting``: switch (default off), display only, no posting.

Revision ID: 0438
Revises: 0437
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0438"
down_revision: str | None = "0437"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTING = "hoa_allocation_proposal_setting"


def upgrade() -> None:
    op.create_table(
        SETTING,
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
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{SETTING}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{SETTING}")),
        sa.UniqueConstraint("tenant_id", name=op.f(f"uq_{SETTING}_tenant_id")),
    )
    for statement in tenant_rls_statements(SETTING):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(SETTING):
        op.execute(statement)
    op.drop_table(SETTING)
