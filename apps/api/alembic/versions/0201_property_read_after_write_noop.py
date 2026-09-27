"""property_read_after_write_noop: the read after write regression test for
``PATCH`` + ``GET /properties/{id}`` (tests/integration/test_property_read_after_write.py)
needs no schema change.

Revision ID: 0201
Revises: 0200
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0201"
down_revision: str | None = "0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
