"""datev_account_mapping: operator maintained assignment of CRM ledger account numbers to
DATEV Sachkonten per tenant, optionally per ledger and valid from a date (task A36, M18-01,
rule M18-04). No chart of accounts is preloaded.

Revision ID: 0099
Revises: 0098
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0099"
down_revision: str | None = "0098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "datev_account_mapping"


def upgrade() -> None:
    op.create_table(
        _TABLE,
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
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("account_code", sa.String(32), nullable=False),
        sa.Column("datev_account", sa.String(16), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ledger_id"], ["ledger.id"], ondelete="CASCADE"),
        sa.CheckConstraint("account_code <> ''", name="ck_datev_account_mapping_account_code"),
        sa.CheckConstraint("datev_account <> ''", name="ck_datev_account_mapping_datev_account"),
    )
    op.create_index("ix_datev_account_mapping_tenant_id", _TABLE, ["tenant_id"])
    op.create_index("ix_datev_account_mapping_ledger_id", _TABLE, ["ledger_id"])
    # One row per tenant, ledger (or tenant wide), CRM account and validity start; NULL is a
    # value here, therefore an expression index instead of a plain unique constraint.
    op.execute(
        "CREATE UNIQUE INDEX ux_datev_account_mapping_key ON datev_account_mapping "
        "(tenant_id, COALESCE(ledger_id, '00000000-0000-0000-0000-000000000000'::uuid), "
        "account_code, COALESCE(valid_from, DATE '0001-01-01'))"
    )
    for statement in tenant_rls_statements(_TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(_TABLE):
        op.execute(statement)
    op.drop_index("ux_datev_account_mapping_key", table_name=_TABLE)
    op.drop_index("ix_datev_account_mapping_ledger_id", table_name=_TABLE)
    op.drop_index("ix_datev_account_mapping_tenant_id", table_name=_TABLE)
    op.drop_table(_TABLE)
