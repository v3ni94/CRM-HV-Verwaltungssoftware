"""User UI preferences (operator request 27.09.2026): server side, per user storage for the
collapsible main navigation state (which menu groups are expanded), so the state is the same on
every device. ``app_user.ui_preferences`` is a small JSONB bag; the accepted keys and validation
live in ``mhvp.core.auth.routers`` (``PATCH /api/v1/auth/me/preferences``). No tenant data, no
money impact, no RLS needed (``app_user`` is a platform table).

Revision ID: 0182
Revises: 0181
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0182"
down_revision: str | None = "0181"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "app_user"
COLUMN = "ui_preferences"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    columns = {c["name"] for c in _inspector().get_columns(TABLE)}
    if COLUMN not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                COLUMN,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    columns = {c["name"] for c in _inspector().get_columns(TABLE)}
    if COLUMN in columns:
        op.drop_column(TABLE, COLUMN)
