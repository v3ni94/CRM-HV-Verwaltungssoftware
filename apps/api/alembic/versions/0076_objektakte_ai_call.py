"""objektakte_ai_call: M35 Stufe 4 (docs/plans/M35-objektakte-uebernahme.md section 4,
docs/rules/M35-03.md). Read-only mirror of the objektakte `ai_calls` protocol (cost evaluation,
masking evidence), filled only by the objektakte importer.

Revision ID: 0076
Revises: 0074
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0076"
down_revision: str | None = "0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ("objektakte_ai_call",)


def upgrade() -> None:
    op.create_table(
        "objektakte_ai_call",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("property_id", postgresql.UUID(as_uuid=True)),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("endpoint", sa.String(length=255)),
        sa.Column("region", sa.String(length=40)),
        sa.Column("page_from", sa.Integer()),
        sa.Column("page_to", sa.Integer()),
        sa.Column("prompt_hash", sa.String(length=64)),
        sa.Column("prompt_chars", sa.Integer()),
        sa.Column("masked_entities_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer()),
        sa.Column("tokens_out", sa.Integer()),
        sa.Column("cost_eur", sa.Numeric(precision=12, scale=6)),
        sa.Column("price_list_version", sa.String(length=24)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("http_status", sa.SmallInteger()),
        sa.Column("error_message", sa.String(length=1000)),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("response_summary", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_document_id", sa.String(length=64)),
        sa.Column("source_object_id", sa.String(length=64)),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_objektakte_ai_call_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_objektakte_ai_call_property_id_property"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_objektakte_ai_call_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objektakte_ai_call")),
        sa.UniqueConstraint(
            "tenant_id",
            "source_system",
            "source_id",
            name=op.f("uq_objektakte_ai_call_tenant_id_source_system_source_id"),
        ),
    )
    op.create_index(
        op.f("ix_objektakte_ai_call_document_id"), "objektakte_ai_call", ["document_id"]
    )
    op.create_index(
        op.f("ix_objektakte_ai_call_property_id"), "objektakte_ai_call", ["property_id"]
    )
    op.create_index(
        "ix_objektakte_ai_call_tenant_requested_at",
        "objektakte_ai_call",
        ["tenant_id", "requested_at"],
    )

    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)

    op.drop_index("ix_objektakte_ai_call_tenant_requested_at", table_name="objektakte_ai_call")
    op.drop_index(op.f("ix_objektakte_ai_call_property_id"), table_name="objektakte_ai_call")
    op.drop_index(op.f("ix_objektakte_ai_call_document_id"), table_name="objektakte_ai_call")
    op.drop_table("objektakte_ai_call")
