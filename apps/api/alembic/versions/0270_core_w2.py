"""Core wave 2: rule test mode (S15-04), tenant job schedules (S15-03), handover defect
tickets and move direction (S13-01, S13-02).

Revision ID: 0270
Revises: 0269
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0270"
down_revision: str | None = "0269"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uid = postgresql.UUID(as_uuid=True)
TABLE = "tenant_job_schedule"


def upgrade() -> None:
    op.add_column(
        "automation_rule",
        sa.Column("test_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("handover_defect", sa.Column("ticket_id", uid, nullable=True))
    op.create_foreign_key(
        op.f("fk_handover_defect_ticket_id_ticket"),
        "handover_defect",
        "ticket",
        ["ticket_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("handover_protocol", sa.Column("move_direction", sa.String(3)))
    stamp = sa.text("now()")
    op.create_table(
        TABLE,
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("created_by", uid),
        sa.Column("updated_by", uid),
        sa.Column("job_key", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("run_at", sa.String(5)),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_tenant_job_schedule_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "job_key", name="uq_tenant_job_schedule_key"),
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
    op.drop_column("handover_protocol", "move_direction")
    op.drop_column("handover_defect", "ticket_id")
    op.drop_column("automation_rule", "test_mode")
