"""admin_fee_invoice: tenant foreign key with ON DELETE RESTRICT like every other tenant table
(TenantMixin, ADR 0002). Migration 0094 created the key without the delete rule, which the
autogenerate drift check reports.

Revision ID: 0108
Revises: 0107
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0108"
down_revision: str | None = "0107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "admin_fee_invoice"
FK = "fk_admin_fee_invoice_tenant_id_tenant"


def upgrade() -> None:
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.create_foreign_key(FK, TABLE, "tenant", ["tenant_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.create_foreign_key(FK, TABLE, "tenant", ["tenant_id"], ["id"])
