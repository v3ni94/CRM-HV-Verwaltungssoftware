"""objektakte_required_document: M35 Stufe 3 part 4 (completeness check,
docs/plans/M35-objektakte-uebernahme.md section 4). A per tenant required document set per
management type (reuses the existing `management_type` enum, no separate vocabulary, see the
model docstring).

Revision ID: 0073
Revises: 0072
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0073"
down_revision: str | None = "0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ("objektakte_required_document",)

_MANAGEMENT_TYPE = postgresql.ENUM(
    "rental", "hoa", "hoa_with_sev", name="management_type", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "objektakte_required_document",
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
        sa.Column("management_type", _MANAGEMENT_TYPE, nullable=False),
        sa.Column("document_category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["document_category_id"], ["document_category.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tenant_id", "management_type", "document_category_id"),
    )
    op.create_index(
        "ix_objektakte_required_document_category_id",
        "objektakte_required_document",
        ["document_category_id"],
    )

    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)

    op.drop_table("objektakte_required_document")
