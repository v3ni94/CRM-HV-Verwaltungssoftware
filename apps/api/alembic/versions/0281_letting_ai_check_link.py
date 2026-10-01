"""Rent increase case: reference to the AI check (M5-08, 6.3 ai_check_id).

Revision ID: 0281
Revises: 0280
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0281"
down_revision: str | None = "0280"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rent_increase_case",
        sa.Column("ai_check_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_rent_increase_case_ai_check_id_ai_proposal"),
        "rent_increase_case",
        "ai_proposal",
        ["ai_check_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_rent_increase_case_ai_check_id_ai_proposal"),
        "rent_increase_case",
        type_="foreignkey",
    )
    op.drop_column("rent_increase_case", "ai_check_id")
