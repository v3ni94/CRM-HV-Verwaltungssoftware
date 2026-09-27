"""contact_relation.delivery_mode (operator decision 26.09.2026, M8-04 addendum): an
authorised representative (relation kind ``representative``) carries a delivery rule that
the recipient resolution for mails, letters and WEG invitations reads: ``both`` (default,
represented contact and representative receive everything), ``representative_only`` or
``owner_only``. Column only; the table keeps its RLS policies (migration 0003).

Revision ID: 0140
Revises: 0139
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0140"
down_revision: str | None = "0139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contact_relation",
        sa.Column("delivery_mode", sa.String(20), nullable=False, server_default="both"),
    )
    op.create_check_constraint(
        "ck_contact_relation_delivery_mode",
        "contact_relation",
        "delivery_mode IN ('both', 'representative_only', 'owner_only')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contact_relation_delivery_mode", "contact_relation", type_="check")
    op.drop_column("contact_relation", "delivery_mode")
