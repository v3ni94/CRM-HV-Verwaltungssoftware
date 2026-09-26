"""membership.legal_entity_ids: legal entity access scope per membership (A37, M18-02,
docs/rules/M18-04-steuerberaterzugang.md). Platform table, no RLS change. Empty list is the
default; for scoped roles (tax_advisor) it means no access until assigned.

Revision ID: 0102
Revises: 0101
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0102"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "membership",
        sa.Column(
            "legal_entity_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("membership", "legal_entity_ids")
