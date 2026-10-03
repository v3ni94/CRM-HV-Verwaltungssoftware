"""AP14 (GAM-410): lightweight access log (who read which personal data, when).

Table access_log (tenant scoped, RLS): user, subject contact (no foreign key, the entry stays
as evidence after an erasure of the contact), entity type and id, action, time. No content is
stored. Whether and in which scope reads are logged and how long entries are kept is a tenant
switch (tenant_settings.sources["access_log"], default off), decision AP14-01 stays open.

Revision ID: 0466
Revises: 0465
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0466"
down_revision: str | None = "0465"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.String(63), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_access_log_tenant_subject",
        "access_log",
        ["tenant_id", "subject_contact_id", "occurred_at"],
    )
    op.create_index("ix_access_log_tenant_occurred", "access_log", ["tenant_id", "occurred_at"])
    for statement in tenant_rls_statements("access_log"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("access_log"):
        op.execute(statement)
    op.drop_index("ix_access_log_tenant_occurred", table_name="access_log")
    op.drop_index("ix_access_log_tenant_subject", table_name="access_log")
    op.drop_table("access_log")
