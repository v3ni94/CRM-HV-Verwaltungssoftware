"""ticket_template_fields: configurable required extra fields per ticket template (e.g. an
IBAN on a deposit ticket) and their values on the ticket.

Revision ID: 0039
Revises: 0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ticket_template",
        sa.Column(
            "required_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "ticket",
        sa.Column(
            "extra_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("ticket", "extra_fields")
    op.drop_column("ticket_template", "required_fields")
