"""AF10: Paperless text, central document.created, invoice switch, trash aware import; no schema.

Revision ID: 0404
Revises: 0403
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0404"
down_revision: str | None = "0403"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
