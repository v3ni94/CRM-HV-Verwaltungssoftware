"""Documents wave 3: hold kind and WEG permanent record flag (S711-06), redacted copies with
protocol (M25-01).

Revision ID: 0272
Revises: 0271
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0272"
down_revision: str | None = "0271"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uid = postgresql.UUID(as_uuid=True)
TABLE = "document_redaction"
_HOLD_KINDS = "('litigation', 'tax_procedure', 'evidence', 'legal_matter', 'other')"


def upgrade() -> None:
    op.add_column("document", sa.Column("retention_hold_kind", sa.String(32)))
    op.add_column(
        "document",
        sa.Column(
            "permanent_record", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_check_constraint(
        op.f("ck_document_retention_hold_kind"),
        "document",
        f"retention_hold_kind IS NULL OR retention_hold_kind IN {_HOLD_KINDS}",
    )
    stamp = sa.text("now()")
    op.create_table(
        TABLE,
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("created_by", uid),
        sa.Column("updated_by", uid),
        sa.Column("original_document_id", uid, nullable=False),
        sa.Column("copy_document_id", uid, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("released_by", uid),
        sa.Column("released_visibility", postgresql.ARRAY(sa.String(16))),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_document_redaction_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["original_document_id"],
            ["document.id"],
            name=op.f("fk_document_redaction_original_document_id_document"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["copy_document_id"],
            ["document.id"],
            name=op.f("fk_document_redaction_copy_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("copy_document_id", name="uq_document_redaction_copy"),
    )
    op.create_index(
        op.f("ix_document_redaction_original_document_id"), TABLE, ["original_document_id"]
    )
    op.create_index(op.f("ix_document_redaction_copy_document_id"), TABLE, ["copy_document_id"])
    op.create_index("ix_document_redaction_original", TABLE, ["tenant_id", "original_document_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
    op.drop_constraint(op.f("ck_document_retention_hold_kind"), "document", type_="check")
    op.drop_column("document", "permanent_record")
    op.drop_column("document", "retention_hold_kind")
