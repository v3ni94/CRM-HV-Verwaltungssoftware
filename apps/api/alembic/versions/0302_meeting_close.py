"""Closing of the owners' meeting minutes with four eyes (R07-01).

* ``owners_meeting.close_requested_by`` / ``close_requested_at``: first person, request with
  the signed minutes document (``minutes_document_id``, existing column).
* ``owners_meeting.closed_by`` / ``closed_at``: second person, confirmation; status ``closed``.

Revision ID: 0302
Revises: 0301
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0302"
down_revision: str | None = "0301"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "owners_meeting",
        sa.Column("close_requested_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "owners_meeting",
        sa.Column("close_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "owners_meeting", sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "owners_meeting", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("owners_meeting", "closed_at")
    op.drop_column("owners_meeting", "closed_by")
    op.drop_column("owners_meeting", "close_requested_at")
    op.drop_column("owners_meeting", "close_requested_by")
