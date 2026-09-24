"""mailbox_oauth_access: Google OAuth client per tenant, default mailbox, mailbox access per
user (M20-01).

Revision ID: 0035
Revises: 0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings", sa.Column("google_client_id", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "tenant_settings", sa.Column("google_client_secret", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "mailbox",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "mailbox_user",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "mailbox_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mailbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("mailbox_id", "user_id", name="uq_mailbox_user"),
    )
    op.create_index("ix_mailbox_user_tenant", "mailbox_user", ["tenant_id", "user_id"])
    for statement in tenant_rls_statements("mailbox_user"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("mailbox_user"):
        op.execute(statement)
    op.drop_table("mailbox_user")
    op.drop_column("mailbox", "is_default")
    op.drop_column("tenant_settings", "google_client_secret")
    op.drop_column("tenant_settings", "google_client_id")
