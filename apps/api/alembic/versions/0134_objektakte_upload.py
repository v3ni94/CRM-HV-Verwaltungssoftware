"""objektakte upload (26.09.2026): CRM documents handed to objektakte for filing in Drive (owner and
tenant files) and Paperless. One row per document with the upload state; while a row exists the
CRM's own Paperless and Drive mirrors are not queued for that document. Tenant table with RLS
(ADR 0002).

Revision ID: 0134
Revises: 0133
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0134"
down_revision: str | None = "0133"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "objektakte_upload"


def upgrade() -> None:
    op.create_table(
        _TABLE,
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
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True)),
        sa.Column("object_number", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("hints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("objektakte_document_id", sa.Integer()),
        sa.Column("remote", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_objektakte_upload_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_objektakte_upload_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_objektakte_upload_property_id_property"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'submitted', 'done', 'failed')",
            name=op.f("ck_objektakte_upload_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objektakte_upload")),
        sa.UniqueConstraint("tenant_id", "document_id", name="uq_objektakte_upload_document"),
    )
    op.create_index(op.f("ix_objektakte_upload_next_attempt_at"), _TABLE, ["next_attempt_at"])
    for statement in tenant_rls_statements(_TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(_TABLE):
        op.execute(statement)
    op.drop_index(op.f("ix_objektakte_upload_next_attempt_at"), table_name=_TABLE)
    op.drop_table(_TABLE)
