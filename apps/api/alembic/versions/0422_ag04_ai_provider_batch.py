"""AG04: provider batch switch and price factor on ai_provider_config (GAB-09).

Revision ID: 0422
Revises: 0421
"""

import sqlalchemy as sa
from alembic import op

revision = "0422"
down_revision = "0421"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_provider_config",
        sa.Column("batch_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "ai_provider_config",
        sa.Column("batch_price_factor", sa.Numeric(20, 8), nullable=False, server_default="1.00"),
    )
    op.create_check_constraint(
        op.f("ck_ai_provider_config_batch_price_factor_range"),
        "ai_provider_config",
        "batch_price_factor > 0 AND batch_price_factor <= 1",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ai_provider_config_batch_price_factor_range"), "ai_provider_config")
    op.drop_column("ai_provider_config", "batch_price_factor")
    op.drop_column("ai_provider_config", "batch_enabled")
