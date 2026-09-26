"""ai_posting_enabled: M7-09, M12-01 KI-Kontierung. Mandantenschalter
``tenant_settings.ai_posting_enabled`` (Standard aus); ``propose_posting`` läuft nur bei
gesetztem Schalter und freigegebenem KI-Anbieter mit AVV.

Revision ID: 0113
Revises: 0108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0113"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column("ai_posting_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "ai_posting_enabled")
