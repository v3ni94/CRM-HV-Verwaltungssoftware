"""AB13: platform_audit_event, append-only audit trail of platform actions without tenant context.

Platform table, no RLS (section 5.3). Rows cannot be changed or deleted (trigger
``forbid_mutation`` from revision 0002).

Revision ID: 0332
Revises: 0331
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0332"
down_revision: str | None = "0331"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_audit_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_audit_event")),
    )
    op.create_index("ix_platform_audit_event_occurred_at", "platform_audit_event", ["occurred_at"])
    op.execute(
        "CREATE TRIGGER platform_audit_event_append_only "
        "BEFORE UPDATE OR DELETE OR TRUNCATE ON platform_audit_event "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS platform_audit_event_append_only ON platform_audit_event")
    op.drop_index("ix_platform_audit_event_occurred_at", table_name="platform_audit_event")
    op.drop_table("platform_audit_event")
