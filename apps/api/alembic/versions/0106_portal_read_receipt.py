"""portal_read_receipt: retrieval of a document through the portal as an indication (11.3,
D34, A53). Separate from dispatch (delivery evidence) and from any receipt date; no IP
address column on purpose.

Revision ID: 0106
Revises: 0105
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0106"
down_revision: str | None = "0102"  # TODO set to the actual predecessor at completion
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "portal_read_receipt"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.CheckConstraint("kind IN ('opened', 'downloaded')", name="ck_portal_read_receipt_kind"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_portal_read_receipt_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["portal_account.id"],
            name=op.f("fk_portal_read_receipt_account_id_portal_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_portal_read_receipt_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_read_receipt")),
    )
    op.create_index(
        "ix_portal_read_receipt_document", TABLE, ["tenant_id", "document_id", "occurred_at"]
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_portal_read_receipt_document", table_name=TABLE)
    op.drop_table(TABLE)
