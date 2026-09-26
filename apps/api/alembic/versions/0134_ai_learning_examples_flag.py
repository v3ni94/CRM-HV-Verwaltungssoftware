"""tenant_settings.ai_learning_examples_enabled (ADR 0010, M7-04, rule M19-07): per tenant
switch for storing learning examples (``ai_example``, task ``ticket_resolution``) at ticket
closure. Default false (rule 0.1.3: the data protection rule for the examples is still open),
the operator enables it per tenant. Column only; the table keeps its RLS policies.

Revision ID: 0134
Revises: 0133
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0134"
down_revision: str | None = "0133"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "ai_learning_examples_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "ai_learning_examples_enabled")
