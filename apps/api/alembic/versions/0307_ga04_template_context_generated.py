"""GA04-07/10/11/12: work order workflow reference, template context, generated documents,
embeddings of learning examples.

* ``work_order.approval_workflow_id``: nullable reference (no FK, no workflow table yet).
* ``document_template``: ``master_template_id``, ``context_types``, ``placeholders_used``.
* ``generated_document``: template, version, context, recipient and dispatch of a produced
  document (RLS per tenant).
* ``ai_embedding_source_kind`` gets ``ai_example``.

Revision ID: 0307
Revises: 0306
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0307"
down_revision: str | None = "0306"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "generated_document"


def upgrade() -> None:
    op.add_column(
        "work_order",
        sa.Column("approval_workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "document_template",
        sa.Column("master_template_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "document_template",
        sa.Column(
            "context_types",
            postgresql.ARRAY(sa.String(length=32)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "document_template",
        sa.Column(
            "placeholders_used",
            postgresql.ARRAY(sa.String(length=100)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        op.f("fk_document_template_master_template_id_document_template"),
        "document_template",
        "document_template",
        ["master_template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_document_template_master_template_id"),
        "document_template",
        ["master_template_id"],
        unique=False,
    )

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("template_code", sa.String(length=63), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("context_type", sa.String(length=32), nullable=True),
        sa.Column("context_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_contact_id", sa.Uuid(), nullable=True),
        sa.Column("dispatch_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_generated_document_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_generated_document_document_id_document"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["document_template.id"],
            name=op.f("fk_generated_document_template_id_document_template"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_contact_id"],
            ["contact.id"],
            name=op.f("fk_generated_document_recipient_contact_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dispatch_id"],
            ["dispatch.id"],
            name=op.f("fk_generated_document_dispatch_id_dispatch"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_document")),
        sa.UniqueConstraint("tenant_id", "document_id", name="uq_generated_document_document"),
    )
    for column in ("document_id", "template_id", "recipient_contact_id", "dispatch_id"):
        op.create_index(op.f(f"ix_{TABLE}_{column}"), TABLE, [column], unique=False)
    op.create_index(
        "ix_generated_document_context", TABLE, ["tenant_id", "context_type", "context_id"]
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE ai_embedding_source_kind ADD VALUE IF NOT EXISTS 'ai_example'")


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
    op.drop_index(op.f("ix_document_template_master_template_id"), table_name="document_template")
    op.drop_constraint(
        op.f("fk_document_template_master_template_id_document_template"),
        "document_template",
        type_="foreignkey",
    )
    op.drop_column("document_template", "placeholders_used")
    op.drop_column("document_template", "context_types")
    op.drop_column("document_template", "master_template_id")
    op.drop_column("work_order", "approval_workflow_id")
    # The enum value ai_example stays (PostgreSQL cannot drop enum values).
