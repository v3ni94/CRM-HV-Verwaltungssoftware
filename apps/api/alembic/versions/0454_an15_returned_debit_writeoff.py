"""AN15: return debit evidence (GAK-101) and write off procedure of open items (GAK-104).

direct_debit_order gets return transaction, return date, fee and fee voucher; open_item gets
date, time, reason and author of a write off; new table open_item_write_off with RLS; two
tenant switches (default off). Nothing is posted.

Revision ID: 0454
Revises: 0453
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import tenant_rls_statements

revision: str = "0454"
down_revision: str | None = "0453"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_META = "'updated_at', 'updated_by'"
_FREE = "'written_off', 'due_date', 'notice_received_on', 'contract_id'"
_WO = "'written_off_on', 'written_off_at', 'written_off_reason', 'written_off_by'"


def _guard(extra: str) -> str:
    """Body of mhvp_open_item_guard (0444); with ``extra`` the write off fields may be set
    once while no approved write off is recorded (``written_off_at`` still NULL)."""
    once = (
        """
  IF OLD.written_off_at IS NOT NULL AND ROW(NEW.written_off, NEW.written_off_on,
     NEW.written_off_at, NEW.written_off_reason, NEW.written_off_by) IS DISTINCT FROM
     ROW(OLD.written_off, OLD.written_off_on, OLD.written_off_at, OLD.written_off_reason,
     OLD.written_off_by) THEN
    RAISE EXCEPTION 'write off of open item % is final', OLD.id USING ERRCODE = 'P0001';
  END IF;"""
        if extra
        else ""
    )
    keys = f"{_FREE}, {extra + ', ' if extra else ''}{_META}"
    return f"""
CREATE OR REPLACE FUNCTION mhvp_open_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'open item % is immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF (to_jsonb(NEW) - ARRAY[{keys}])
     IS DISTINCT FROM
     (to_jsonb(OLD) - ARRAY[{keys}])
     OR (OLD.contract_id IS NOT NULL AND NEW.contract_id IS DISTINCT FROM OLD.contract_id)
  THEN
    RAISE EXCEPTION 'open item % is immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;{once}
  RETURN NEW;
END $$
"""


def _uuid() -> postgresql.UUID:  # type: ignore[type-arg]
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "direct_debit_order",
        sa.Column("return_transaction_id", _uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_direct_debit_order_return_transaction_id_bank_transaction",
        "direct_debit_order",
        "bank_transaction",
        ["return_transaction_id"],
        ["id"],
    )
    op.add_column("direct_debit_order", sa.Column("returned_on", sa.Date(), nullable=True))
    op.add_column(
        "direct_debit_order", sa.Column("return_fee_amount", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column(
        "direct_debit_order",
        sa.Column("return_fee_document_id", _uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_direct_debit_order_return_fee_document_id_document",
        "direct_debit_order",
        "document",
        ["return_fee_document_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_direct_debit_order_return_fee",
        "direct_debit_order",
        "return_fee_amount IS NULL OR return_fee_amount >= 0",
    )
    op.add_column("open_item", sa.Column("written_off_on", sa.Date(), nullable=True))
    op.add_column(
        "open_item", sa.Column("written_off_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("open_item", sa.Column("written_off_reason", sa.String(500), nullable=True))
    op.add_column("open_item", sa.Column("written_off_by", _uuid(), nullable=True))
    op.execute(_guard(_WO))
    for name in ("return_fee_pass_on_enabled", "write_off_approval_enabled"):
        op.add_column(
            "accounting_tax_settings",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    op.create_table(
        "open_item_write_off",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", _uuid(), nullable=False),
        sa.Column("open_item_id", _uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("document_id", _uuid(), nullable=True),
        sa.Column("proposed_by", _uuid(), nullable=True),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_by", _uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')", name="ck_open_item_write_off_status"
        ),
        sa.CheckConstraint("amount > 0", name="ck_open_item_write_off_amount"),
        sa.PrimaryKeyConstraint("id", name="pk_open_item_write_off"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_open_item_write_off_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["open_item_id"], ["open_item.id"], name="fk_open_item_write_off_open_item_id_open_item"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name="fk_open_item_write_off_document_id_document"
        ),
    )
    op.create_index(
        "ix_open_item_write_off_item", "open_item_write_off", ["tenant_id", "open_item_id"]
    )
    op.create_index(
        "uq_open_item_write_off_active",
        "open_item_write_off",
        ["open_item_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('proposed', 'approved')"),
    )
    for statement in tenant_rls_statements("open_item_write_off"):
        op.execute(statement)


def downgrade() -> None:
    # Development tool only: production restores from backup (runbook). The write off history
    # and the return evidence are dropped with their columns.
    op.drop_index("uq_open_item_write_off_active", table_name="open_item_write_off")
    op.drop_index("ix_open_item_write_off_item", table_name="open_item_write_off")
    op.drop_table("open_item_write_off")
    for name in ("write_off_approval_enabled", "return_fee_pass_on_enabled"):
        op.drop_column("accounting_tax_settings", name)
    op.execute(_guard(""))
    for name in ("written_off_by", "written_off_reason", "written_off_at", "written_off_on"):
        op.drop_column("open_item", name)
    op.drop_constraint("ck_direct_debit_order_return_fee", "direct_debit_order", type_="check")
    op.drop_constraint(
        "fk_direct_debit_order_return_fee_document_id_document",
        "direct_debit_order",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_direct_debit_order_return_transaction_id_bank_transaction",
        "direct_debit_order",
        type_="foreignkey",
    )
    for name in (
        "return_fee_document_id",
        "return_fee_amount",
        "returned_on",
        "return_transaction_id",
    ):
        op.drop_column("direct_debit_order", name)
