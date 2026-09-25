"""calendar_event: link table between CRM origin (ticket, handover, manual) and Google Calendar
events (M23-02 operator decision 25.09.2026: bidirectional sync, drafts first, no silent
external changes). Attendees are stored but never sent to Google until a staff user confirms
the "Einladung senden" action (docs/rules/M23-05.md); ``etag``/``is_stale`` support conflict
detection on the read path (no automatic overwrite either way).

Revision ID: 0057
Revises: 0056

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("calendar_event",)


def upgrade() -> None:
    op.create_table(
        "calendar_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
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
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("mailbox_id", sa.UUID(), nullable=False),
        sa.Column("google_event_id", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column(
            "attendees",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invite_confirmed_by", sa.UUID(), nullable=True),
        sa.Column("invite_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etag", sa.String(length=200), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mailbox_id"], ["mailbox.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "mailbox_id", "google_event_id"),
    )
    op.create_index(
        "ix_calendar_event_source",
        "calendar_event",
        ["tenant_id", "source_type", "source_id"],
    )
    for stmt in tenant_rls_statements("calendar_event"):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in drop_tenant_rls_statements("calendar_event"):
        op.execute(stmt)
    op.drop_index("ix_calendar_event_source", table_name="calendar_event")
    op.drop_table("calendar_event")
