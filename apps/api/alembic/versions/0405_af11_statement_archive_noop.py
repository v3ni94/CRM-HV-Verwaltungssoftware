"""Placeholder for package AF11 (GAB-06): no schema change, keeps the chain linear.

Filed hoa statement PDFs are found through ``document_link`` (entity_type "hoa_statement").

Revision ID: 0405
Revises: 0404
"""

from collections.abc import Sequence

revision: str = "0405"
down_revision: str | None = "0404"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
