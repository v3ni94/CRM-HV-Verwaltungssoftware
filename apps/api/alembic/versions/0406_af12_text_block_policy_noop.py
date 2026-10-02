"""AF12: tenant switch require_second_person for text blocks lives in tenant_settings.sources
(key ``text_block_policy``); no schema change. Noop placeholder keeps the chain linear.

Revision ID: 0406
Revises: 0405
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0406"
down_revision: str | None = "0405"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
