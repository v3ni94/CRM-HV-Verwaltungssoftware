"""M17-01, M17-03: BetrKV catalogue mapping per cost account and advance proposals.

``ledger_account.operating_cost_type`` holds the code of the system catalogue of operating
cost types (``mhvp.billing.betrkv``, § 2 BetrKV numbers 1 to 17 plus ``V`` administration and
``I`` maintenance as non allocable). ``statement_advance_rule`` keeps the optional safety
surcharge per tenant (percent, default 0). ``statement_advance_proposal`` stores proposals
for new monthly advances derived from a statement snapshot (result divided by twelve) with a
confirmation step; nothing changes contract payments (§ 560 BGB stays a separate step, G3).

Revision ID: 0170
Revises: 0169
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import tenant_rls_statements

revision: str = "0170"
down_revision: str | None = "0169"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(name)}


def _ensure_tenant_fk(table: str) -> None:
    """Add the tenant FK (RESTRICT, as ``TenantMixin``) when the table predates it."""
    name = f"fk_{table}_tenant_id_tenant"
    exists = (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"), {"name": name})
        .scalar()
    )
    if not exists:
        op.create_foreign_key(name, table, "tenant", ["tenant_id"], ["id"], ondelete="RESTRICT")


def upgrade() -> None:
    if "operating_cost_type" not in _columns("ledger_account"):
        op.add_column(
            "ledger_account", sa.Column("operating_cost_type", sa.String(length=4), nullable=True)
        )
    tables = _tables()
    if "statement_advance_rule" not in tables:
        op.create_table(
            "statement_advance_rule",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("surcharge_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name="fk_statement_advance_rule_tenant_id_tenant",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint("tenant_id", name="uq_statement_advance_rule_tenant"),
        )
        for statement in tenant_rls_statements("statement_advance_rule"):
            op.execute(statement)
    if "statement_advance_proposal" not in tables:
        op.create_table(
            "statement_advance_proposal",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "statement_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("statement.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
            sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("unit_number", sa.String(length=32), nullable=False),
            sa.Column("previous_costs", sa.Numeric(14, 2), nullable=False),
            sa.Column("months", sa.Integer(), nullable=False, server_default="12"),
            sa.Column("surcharge_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("proposed_amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("letter_text", sa.Text(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name="fk_statement_advance_proposal_tenant_id_tenant",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "ix_statement_advance_proposal_statement",
            "statement_advance_proposal",
            ["tenant_id", "statement_id"],
        )
        for statement in tenant_rls_statements("statement_advance_proposal"):
            op.execute(statement)
    for table in ("statement_advance_rule", "statement_advance_proposal"):
        _ensure_tenant_fk(table)


def downgrade() -> None:
    tables = _tables()
    if "statement_advance_proposal" in tables:
        op.drop_table("statement_advance_proposal")
    if "statement_advance_rule" in tables:
        op.drop_table("statement_advance_rule")
    if "operating_cost_type" in _columns("ledger_account"):
        op.drop_column("ledger_account", "operating_cost_type")
