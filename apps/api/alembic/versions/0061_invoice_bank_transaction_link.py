"""invoice_bank_transaction_link: M11-finapi Stage 3 (docs/plans/M11-finapi.md), operator
decision 25.09.2026. Records an automatic finding that a bank transaction settles a payable
invoice (amount plus invoice number or IBAN in the purpose); never posts anything by itself.

Revision ID: 0061
Revises: 0060

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MATCH_BASIS = postgresql.ENUM(
    "amount_and_number", "amount_and_iban", name="invoice_match_basis", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    _MATCH_BASIS.create(bind, checkfirst=True)

    op.create_table(
        "invoice_bank_transaction_link",
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
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_basis", _MATCH_BASIS, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice.id"]),
        sa.ForeignKeyConstraint(["bank_transaction_id"], ["bank_transaction.id"]),
    )
    op.create_index(
        "uq_invoice_bank_transaction_link",
        "invoice_bank_transaction_link",
        ["tenant_id", "invoice_id", "bank_transaction_id"],
        unique=True,
    )

    for statement in tenant_rls_statements("invoice_bank_transaction_link"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("invoice_bank_transaction_link"):
        op.execute(statement)
    op.drop_table("invoice_bank_transaction_link")
    bind = op.get_bind()
    _MATCH_BASIS.drop(bind, checkfirst=True)
