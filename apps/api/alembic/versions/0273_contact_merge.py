"""Contact merge proposals and merged marker on contacts (M3-03).

Revision ID: 0273
Revises: 0272
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0273"
down_revision: str | None = "0272"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uid = postgresql.UUID(as_uuid=True)
TABLE = "contact_merge"


def upgrade() -> None:
    op.add_column("contact", sa.Column("merged_into_id", uid, nullable=True))
    op.add_column("contact", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    stamp = sa.text("now()")
    op.create_table(
        TABLE,
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("created_by", uid),
        sa.Column("updated_by", uid),
        sa.Column("source_id", uid, nullable=False),
        sa.Column("target_id", uid, nullable=False),
        sa.Column("status", sa.String(16), server_default="proposed", nullable=False),
        sa.Column("reason", sa.String(1000)),
        sa.Column(
            "check_result",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("proposed_by", uid),
        sa.Column("decided_by", uid),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.String(1000)),
        sa.Column("result", postgresql.JSONB()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_contact_merge_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["contact.id"],
            name=op.f("fk_contact_merge_source_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["contact.id"],
            name=op.f("fk_contact_merge_target_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'executed', 'rejected')",
            name=op.f("ck_contact_merge_ck_contact_merge_status"),
        ),
        sa.CheckConstraint(
            "source_id <> target_id", name=op.f("ck_contact_merge_ck_contact_merge_distinct")
        ),
    )
    op.create_index("ix_contact_merge_tenant_status", TABLE, ["tenant_id", "status"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
    op.drop_column("contact", "merged_at")
    op.drop_column("contact", "merged_into_id")
