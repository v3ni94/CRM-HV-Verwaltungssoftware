"""HNSW index on ai_embedding.embedding (cosine, M7-03 follow-up) and
tenant_settings.ai_learning_examples_retention_months (ADR 0010, M7-04, operator decision
27.09.2026: examples are stored in full per tenant switch and deleted after a retention period,
default 24 months, daily job ``mhvp.ai.examples_retention``).

The index is created CONCURRENTLY in an autocommit block (no table lock on a running system);
the column change runs in the migration transaction before it.

Revision ID: 0154
Revises: 0153
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0154"
down_revision: str | None = "0153"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_ai_embedding_embedding_hnsw"


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "ai_learning_examples_retention_months",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
    )
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} ON ai_embedding "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
    op.drop_column("tenant_settings", "ai_learning_examples_retention_months")
