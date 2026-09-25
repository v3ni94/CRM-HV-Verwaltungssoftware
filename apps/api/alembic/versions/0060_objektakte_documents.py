"""objektakte_documents: M35 Stufe 2 (docs/plans/M35-objektakte-uebernahme.md section 4),
operator decision 25.09.2026. Adds the document takeover columns Stufe 1 could not yet add
without the document importer that uses them: `document.duplicate_of_id` (a duplicate found by
objektakte's own pipeline, kept as a link, rule 0.1.7), `document.source_meta` (objektakte
status, subfolder/type names, ocr_cache_key and the row hash used for idempotent re-import, no
fitting column exists for any of these), `document_category.source_system`/`source_id` (the
category catalog takeover key, docs/rules/M35-01.md pattern reused) and the new
`objektakte_document_class` table (the objektakte subfolder/document_type level, which the flat
CRM category catalog cannot hold, docs/rules/M35-01.md).

Revision ID: 0060
Revises: 0059

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ("objektakte_document_class",)


def upgrade() -> None:
    op.add_column("document", sa.Column("duplicate_of_id", postgresql.UUID(as_uuid=True)))
    op.add_column("document", sa.Column("source_meta", postgresql.JSONB()))
    op.create_foreign_key(
        "fk_document_duplicate_of_id_document",
        "document",
        "document",
        ["duplicate_of_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_document_duplicate_of_id", "document", ["duplicate_of_id"])

    op.add_column("document_category", sa.Column("source_system", sa.String(length=32)))
    op.add_column("document_category", sa.Column("source_id", sa.String(length=64)))
    op.create_index(
        "uq_document_category_source",
        "document_category",
        ["tenant_id", "source_system", "source_id"],
        unique=True,
        postgresql_where=sa.text("source_system IS NOT NULL AND source_id IS NOT NULL"),
    )

    op.create_table(
        "objektakte_document_class",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("category_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subfolder_source_id", sa.String(length=64)),
        sa.Column("subfolder_name", sa.String(length=200)),
        sa.Column("type_code", sa.String(length=64)),
        sa.Column("type_name", sa.String(length=200)),
        sa.Column("requires_period", sa.Boolean(), nullable=False),
        sa.Column("requires_owner", sa.Boolean(), nullable=False),
        sa.Column("requires_tenant", sa.Boolean(), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["document_category.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "source_system", "source_id"),
    )
    op.create_index(
        "ix_objektakte_document_class_category_id", "objektakte_document_class", ["category_id"]
    )

    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)

    op.drop_table("objektakte_document_class")

    op.drop_index("uq_document_category_source", table_name="document_category")
    op.drop_column("document_category", "source_id")
    op.drop_column("document_category", "source_system")

    op.drop_index("ix_document_duplicate_of_id", table_name="document")
    op.drop_constraint("fk_document_duplicate_of_id_document", "document", type_="foreignkey")
    op.drop_column("document", "source_meta")
    op.drop_column("document", "duplicate_of_id")
