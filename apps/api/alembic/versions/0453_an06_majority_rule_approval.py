"""AN06: four eyes approval of meeting majority rules (GAJ-602, AM02-01 open).

Tenant switch hoa_majority_rule_four_eyes (default off); majority_rule gets requires_approval,
approved_by and approved_at. Existing rows keep requires_approval false (behaviour unchanged).

Revision ID: 0453
Revises: 0452
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0453"
down_revision: str | None = "0452"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "hoa_majority_rule_four_eyes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "majority_rule",
        sa.Column(
            "requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("majority_rule", sa.Column("approved_by", sa.UUID(), nullable=True))
    op.add_column(
        "majority_rule", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("majority_rule", "approved_at")
    op.drop_column("majority_rule", "approved_by")
    op.drop_column("majority_rule", "requires_approval")
    op.drop_column("tenant_settings", "hoa_majority_rule_four_eyes")
