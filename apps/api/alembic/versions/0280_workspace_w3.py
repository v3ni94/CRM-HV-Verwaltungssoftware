"""Workspace wave 3: notification preferences and mail flag (M23-04).

Revision ID: 0280
Revises: 0279
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0280"
down_revision: str | None = "0279"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    stamp = sa.text("now()")
    op.add_column(
        "notification",
        sa.Column("email_pending", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "notification", sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "notification_preference",
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("created_by", uid, nullable=True),
        sa.Column("updated_by", uid, nullable=True),
        sa.Column("user_id", uid, nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("in_app", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_notification_preference_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_notification_preference_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preference")),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "kind",
            name=op.f("uq_notification_preference_tenant_id_user_id_kind"),
        ),
    )
    for statement in tenant_rls_statements("notification_preference"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("notification_preference"):
        op.execute(statement)
    op.drop_table("notification_preference")
    op.drop_column("notification", "email_sent_at")
    op.drop_column("notification", "email_pending")
