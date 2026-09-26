"""retention_profile: months, permanent flag, review note and the start rule ``purpose_end``
(operator decision M6-04 of 26.09.2026). The standard profiles are seeded by the application
(``mhvp.documents.defaults``) as drafts; no profile is released here, deletion stays locked
until an operator releases a profile. Columns only; the table keeps its RLS policies.

Revision ID: 0139
Revises: 0138
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0139"
down_revision: str | None = "0138"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE retention_start ADD VALUE IF NOT EXISTS 'purpose_end'")
    op.add_column(
        "retention_profile",
        sa.Column("retention_months", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "retention_profile",
        sa.Column("permanent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("retention_profile", sa.Column("review_note", sa.String(200), nullable=True))
    op.drop_constraint("years_positive", "retention_profile", type_="check")
    op.create_check_constraint(
        "period_non_negative",
        "retention_profile",
        "retention_years >= 0 AND retention_months >= 0 AND retention_months < 12",
    )
    op.create_check_constraint(
        "period_defined",
        "retention_profile",
        "permanent OR retention_years > 0 OR retention_months > 0",
    )


def downgrade() -> None:
    # Rows with a period below one year or permanent rows would violate the old constraint;
    # they are the seeded drafts (nothing references a draft that was never released).
    # Documents referencing them are detached first. The delete runs directly before the
    # constraint so that a tenant seeded by a parallel session cannot slip in between.
    op.drop_constraint("period_defined", "retention_profile", type_="check")
    op.drop_constraint("period_non_negative", "retention_profile", type_="check")
    op.drop_column("retention_profile", "review_note")
    # Both tables force row level security (ADR 0002); without a tenant context the owner
    # would delete no rows and the old constraint would fail. Lift the force for the fix.
    op.execute("ALTER TABLE document NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE retention_profile NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE document SET retention_profile_id = NULL WHERE retention_profile_id IN "
        "(SELECT id FROM retention_profile WHERE permanent OR retention_years = 0)"
    )
    op.execute("DELETE FROM retention_profile WHERE permanent OR retention_years = 0")
    op.create_check_constraint("years_positive", "retention_profile", "retention_years > 0")
    op.execute("ALTER TABLE retention_profile FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document FORCE ROW LEVEL SECURITY")
    op.drop_column("retention_profile", "permanent")
    op.drop_column("retention_profile", "retention_months")
    # The enum value purpose_end stays (PostgreSQL cannot drop enum values); rows using it
    # were removed above only if they had no full-year period.
