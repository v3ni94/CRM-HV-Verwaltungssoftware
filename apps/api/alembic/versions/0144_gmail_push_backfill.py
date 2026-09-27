"""Gmail push notifications and full inbox backfill on ``mailbox`` (operator 26.09.2026).

Watch state of ``users.watch`` (expiration, history id of the watch, last accepted push) and
the progress of the paginated inbox backfill (status, total, done, timestamps, page token for
resumption). ``mailbox`` already carries RLS (tenant table); columns only.

Revision ID: 0144
Revises: 0143
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0144"
down_revision: str | None = "0143"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS: list[sa.Column[object]] = [
    sa.Column("gmail_watch_expiration", sa.DateTime(timezone=True), nullable=True),
    sa.Column("gmail_watch_history_id", sa.String(length=32), nullable=True),
    sa.Column("gmail_last_push_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("backfill_status", sa.String(length=16), nullable=False, server_default="idle"),
    sa.Column("backfill_total", sa.Integer(), nullable=True),
    sa.Column("backfill_done", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("backfill_started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("backfill_finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("backfill_page_token", sa.Text(), nullable=True),
]


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("mailbox", column)


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("mailbox", column.name)
