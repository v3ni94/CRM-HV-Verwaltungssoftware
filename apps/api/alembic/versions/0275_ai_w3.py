"""ai_task value ``rent_increase_check`` (M26-01, package Q06): AI plausibility hints of a rent
increase case, linked through the existing ``rent_increase_case.ai_check_id``.

Revision ID: 0275
Revises: 0274
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0275"
down_revision: str | None = "0274"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'rent_increase_check'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value; runs of the task stay readable (no data loss).
    pass
