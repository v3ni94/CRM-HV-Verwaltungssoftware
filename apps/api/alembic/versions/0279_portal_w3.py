"""Portal wave 3: ticket external_comments and external_attachments default ``open`` (M19-03).

The columns exist since 0260 with default ``none``. The portal now enforces them (6.6); so that
existing tickets keep the former portal behaviour (comments and attachments visible), all rows
and the default move to ``open`` (ASSUMPTIONS A-Q10-01). Staff can restrict a single ticket.

Revision ID: 0279
Revises: 0278
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0279"
down_revision: str | None = "0278"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("external_comments", "external_attachments")


def upgrade() -> None:
    for column in COLUMNS:
        op.execute(f"UPDATE ticket SET {column} = 'open' WHERE {column} = 'none'")  # noqa: S608
        op.execute(f"ALTER TABLE ticket ALTER COLUMN {column} SET DEFAULT 'open'")


def downgrade() -> None:
    for column in COLUMNS:
        op.execute(f"ALTER TABLE ticket ALTER COLUMN {column} SET DEFAULT 'none'")
