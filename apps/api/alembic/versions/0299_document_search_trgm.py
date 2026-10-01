"""Trigram indexes for the portal receipt search (M25-06).

* ``ix_document_lower_title_trgm`` and ``ix_document_lower_filename_trgm``: GIN indexes with
  ``gin_trgm_ops`` on ``lower(title)`` and ``lower(filename)``. The portal search compares
  ``lower(column)`` with a substring pattern, which the plain index ``ix_document_title_trgm``
  on ``title`` cannot serve. ``pg_trgm`` is a trusted extension of the baseline (0001).

Revision ID: 0299
Revises: 0298
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0299"
down_revision: str | None = "0298"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_document_lower_title_trgm ON document "
        "USING gin (lower(title) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_document_lower_filename_trgm ON document "
        "USING gin (lower(filename) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_lower_filename_trgm")
    op.execute("DROP INDEX IF EXISTS ix_document_lower_title_trgm")
