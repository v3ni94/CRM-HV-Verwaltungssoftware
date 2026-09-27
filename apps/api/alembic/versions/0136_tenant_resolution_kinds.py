"""tenant_settings.resolution_kinds (rule M19-07, operator decision M19-04 of 26.09.2026):
per tenant configuration of the resolution kinds offered at ticket closure. JSONB document
{"disabled": [builtin codes], "custom": [{"code", "label"}]} validated by
``mhvp.tickets.resolution_kinds.ResolutionKindsConfig``; empty object means all built in kinds
are active. Column only; the table keeps its RLS policies.

Revision ID: 0136
Revises: 0135
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0136"
down_revision: str | None = "0135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "resolution_kinds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "resolution_kinds")
