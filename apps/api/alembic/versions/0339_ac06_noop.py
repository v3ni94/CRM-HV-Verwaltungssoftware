"""GA02-06 (AC06): no schema change; consent policy lives in tenant_settings.sources and the
portal terms version in consent.source. Placeholder that keeps the revision chain linear.

Revision ID: 0339
Revises: 0338
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0339"
down_revision: str | None = "0338"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
