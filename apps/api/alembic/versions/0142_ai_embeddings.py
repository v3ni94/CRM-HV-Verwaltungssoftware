"""ai_embedding: pgvector chunks per tenant for the similarity search (M7-03, operator decision
26.09.2026) and the task value ``embed`` for the budget accounting of embedding calls.

Revision ID: 0142
Revises: 0141
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.ai.vector import Vector
from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0142"
down_revision: str | None = "0141"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'embed'")
    op.create_table(
        "ai_embedding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.Column(
            "source_kind",
            postgresql.ENUM("document", "knowledge_entry", name="ai_embedding_source_kind"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_ai_embedding_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_embedding")),
        sa.UniqueConstraint(
            "tenant_id",
            "source_kind",
            "source_id",
            "chunk_index",
            name=op.f("uq_ai_embedding_tenant_id_source_kind_source_id_chunk_index"),
        ),
    )
    op.create_index(
        "ix_ai_embedding_tenant_source",
        "ai_embedding",
        ["tenant_id", "source_kind", "source_id"],
        unique=False,
    )
    for statement in tenant_rls_statements("ai_embedding"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("ai_embedding"):
        op.execute(statement)
    op.drop_index("ix_ai_embedding_tenant_source", table_name="ai_embedding")
    op.drop_table("ai_embedding")
    op.execute("DROP TYPE IF EXISTS ai_embedding_source_kind")
    # The enum value "embed" stays (PostgreSQL cannot drop a single value).
