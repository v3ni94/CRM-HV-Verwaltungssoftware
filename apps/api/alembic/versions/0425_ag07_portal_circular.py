"""AG07 (GAF-32): portal circular resolution switch and vote evidence columns.

Revision ID: 0425
Revises: 0424
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0425"
down_revision = "0424"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hoa_online_meeting_setting",
        sa.Column(
            "portal_circular_resolution_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "meeting_vote", sa.Column("portal_user_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("meeting_vote", sa.Column("wording_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("meeting_vote", "wording_sha256")
    op.drop_column("meeting_vote", "portal_user_id")
    op.drop_column("hoa_online_meeting_setting", "portal_circular_resolution_enabled")
