"""Gmail archive tracking per message (operator report 27.09.2026: "Erledigt" is not written
back to Gmail). ``message`` gets ``archive_status`` (pending, archived, skipped, failed,
scope_missing), ``archive_error``, ``archive_attempted_at`` and ``archived_at`` so that every
archive attempt is visible in the CRM, the job is idempotent and the beat job
``communication-archive-retry`` can catch up on completed mails that were never archived.

Revision ID: 0158
Revises: 0157
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0158"
down_revision: str | None = "0157"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "message"
INDEX = "ix_message_archive_open"
COLUMNS = ("archive_status", "archive_error", "archive_attempted_at", "archived_at")


def _existing_columns(name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(name)}


def upgrade() -> None:
    existing = _existing_columns(TABLE)
    if "archive_status" not in existing:
        op.add_column(TABLE, sa.Column("archive_status", sa.String(length=16), nullable=True))
    if "archive_error" not in existing:
        op.add_column(TABLE, sa.Column("archive_error", sa.Text(), nullable=True))
    if "archive_attempted_at" not in existing:
        op.add_column(
            TABLE, sa.Column("archive_attempted_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "archived_at" not in existing:
        op.add_column(TABLE, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (tenant_id, archive_status) "
        "WHERE archive_status IN ('pending', 'failed', 'scope_missing')"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
    existing = _existing_columns(TABLE)
    for column in COLUMNS:
        if column in existing:
            op.drop_column(TABLE, column)
