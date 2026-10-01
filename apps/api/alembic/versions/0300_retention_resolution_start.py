"""Retention start rule ``resolution`` and the resolution reference of a document (U11-01).

* enum ``retention_start``: new value ``resolution``;
* ``document.retention_resolution_id``: nullable reference to ``resolution.id`` (ON DELETE SET
  NULL, index ``ix_document_retention_resolution_id``). The decision date is copied into
  ``retention_base_on`` by the application. No new table, RLS policies stay untouched.

Revision ID: 0300
Revises: 0299
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0300"
down_revision: str | None = "0299"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE retention_start ADD VALUE IF NOT EXISTS 'resolution'")
    op.add_column(
        "document",
        sa.Column("retention_resolution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "document_retention_resolution_id_fkey",
        "document",
        "resolution",
        ["retention_resolution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_document_retention_resolution_id", "document", ["retention_resolution_id"])


def downgrade() -> None:
    op.drop_index("ix_document_retention_resolution_id", table_name="document")
    op.drop_constraint("document_retention_resolution_id_fkey", "document", type_="foreignkey")
    op.drop_column("document", "retention_resolution_id")
    # PostgreSQL cannot drop an enum value; 'resolution' stays in the type.
