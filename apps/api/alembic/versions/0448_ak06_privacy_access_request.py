"""AK06: intake record of data subject access requests (GAI-507).

Table privacy_access_request (receipt, channel, status) with RLS. The response period stays
a tenant setting without default (AJ13-01); nothing is computed by this migration.

Revision ID: 0448
Revises: 0447
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import tenant_rls_statements

revision: str = "0448"
down_revision: str | None = "0447"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "privacy_access_request"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("export_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("close_note", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'in_progress', 'answered', 'rejected', 'withdrawn')",
            name="ck_privacy_access_request_status",
        ),
        sa.CheckConstraint(
            "channel IN ('email', 'letter', 'portal', 'phone', 'in_person', 'other')",
            name="ck_privacy_access_request_channel",
        ),
    )
    op.create_index(
        "ix_privacy_access_request_status", TABLE, ["tenant_id", "status", "received_on"]
    )
    op.create_index("ix_privacy_access_request_contact", TABLE, ["tenant_id", "contact_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    # Like every table drop of the chain the downgrade removes recorded requests; it is a
    # development tool only (production restores from backup, runbook), the round trip test
    # runs it on populated test databases.
    op.drop_index("ix_privacy_access_request_contact", table_name=TABLE)
    op.drop_index("ix_privacy_access_request_status", table_name=TABLE)
    op.drop_table(TABLE)
