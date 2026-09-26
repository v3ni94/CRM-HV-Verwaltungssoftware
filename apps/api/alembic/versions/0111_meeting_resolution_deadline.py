"""owners_meeting: resolution deadline of a virtual meeting with its source (M9-07,
deadline list A41). Entered, never computed.

Revision ID: 0111
Revises: 0108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0111"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("owners_meeting", sa.Column("resolution_deadline_at", sa.Date(), nullable=True))
    op.add_column(
        "owners_meeting", sa.Column("resolution_deadline_source", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("owners_meeting", "resolution_deadline_source")
    op.drop_column("owners_meeting", "resolution_deadline_at")
