"""Gmail back channel: settle period default 180 seconds (was 600).

Existing tenants that still use the old default are moved to 180 seconds; values
set explicitly to anything else are kept.

Revision ID: 0249
Revises: 0248
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0249"
down_revision: str | None = "0248"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("tenant_settings", "gmail_settle_seconds", server_default=sa.text("180"))
    op.execute(
        "UPDATE tenant_settings SET gmail_settle_seconds = 180 WHERE gmail_settle_seconds = 600"
    )


def downgrade() -> None:
    op.alter_column("tenant_settings", "gmail_settle_seconds", server_default=sa.text("600"))
