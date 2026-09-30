"""WEG statement and plan gaps M24-01 to M24-07 (Lückenliste 30.09.2026).

* ``hoa_reserve``: earmarked reserve per GdWE ledger (W08). ``hoa_reserve_movement``: use of
  funds, taxes, fees and interest per reserve and statement. Tenant tables with RLS via
  ``tenant_rls_statements`` (ADR 0002).
* ``economic_plan``: title, as_of_date, basis_statement_id, basis_plan_id, payment_rhythm,
  due_day, continues_until_new_plan, obsolete_at (M24-04).
* ``economic_plan_item``: basis_amount, reserve_id.
* ``hoa_cost_item``: journal_entry_id, document_id (M24-02), labour_cost_35a (M24-05),
  basis_resolution_id, basis_document_id (M24-06).

Idempotent: every step checks the catalogue first.

Revision ID: 0256
Revises: 0255
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0256"
down_revision: str | None = "0255"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(14, 2)


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return bool(_insp().has_table(name))


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _fk(target: str) -> sa.ForeignKey:
    return sa.ForeignKey(target)


def _tenant() -> sa.Column:
    return sa.Column(
        "tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )


def _columns() -> dict[str, list[sa.Column]]:
    return {
        "economic_plan": [
            sa.Column("title", sa.String(200), nullable=True),
            sa.Column("as_of_date", sa.Date(), nullable=True),
            sa.Column("basis_statement_id", UUID, _fk("hoa_statement.id"), nullable=True),
            sa.Column("basis_plan_id", UUID, _fk("economic_plan.id"), nullable=True),
            sa.Column("payment_rhythm", sa.String(16), nullable=False, server_default="monthly"),
            sa.Column("due_day", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "continues_until_new_plan",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column("obsolete_at", sa.DateTime(timezone=True), nullable=True),
        ],
        "economic_plan_item": [
            sa.Column("basis_amount", MONEY, nullable=True),
            sa.Column("reserve_id", UUID, _fk("hoa_reserve.id"), nullable=True),
        ],
        "hoa_cost_item": [
            sa.Column("journal_entry_id", UUID, _fk("journal_entry.id"), nullable=True),
            sa.Column("document_id", UUID, _fk("document.id"), nullable=True),
            sa.Column("labour_cost_35a", MONEY, nullable=True),
            sa.Column("basis_resolution_id", UUID, _fk("resolution.id"), nullable=True),
            sa.Column("basis_document_id", UUID, _fk("document.id"), nullable=True),
        ],
    }


def upgrade() -> None:
    if not _has_table("hoa_reserve"):
        op.create_table(
            "hoa_reserve",
            sa.Column("id", UUID, primary_key=True),
            _tenant(),
            sa.Column("ledger_id", UUID, _fk("ledger.id"), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("purpose", sa.Text(), nullable=True),
            sa.Column("account_id", UUID, _fk("ledger_account.id"), nullable=True),
            sa.Column("resolution_id", UUID, _fk("resolution.id"), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("created_by", UUID, nullable=True),
            sa.Column("updated_by", UUID, nullable=True),
        )
        op.create_index("ix_hoa_reserve_ledger", "hoa_reserve", ["tenant_id", "ledger_id"])
        for statement in tenant_rls_statements("hoa_reserve"):
            op.execute(statement)
    if not _has_table("hoa_reserve_movement"):
        op.create_table(
            "hoa_reserve_movement",
            sa.Column("id", UUID, primary_key=True),
            _tenant(),
            sa.Column(
                "statement_id",
                UUID,
                sa.ForeignKey("hoa_statement.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("reserve_id", UUID, _fk("hoa_reserve.id"), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("amount", MONEY, nullable=False),
            sa.Column("purpose", sa.Text(), nullable=False),
            sa.Column("document_id", UUID, _fk("document.id"), nullable=True),
            sa.Column("journal_entry_id", UUID, _fk("journal_entry.id"), nullable=True),
            sa.Column("resolution_id", UUID, _fk("resolution.id"), nullable=True),
        )
        op.create_index(
            "ix_hoa_reserve_movement_statement",
            "hoa_reserve_movement",
            ["tenant_id", "statement_id"],
        )
        for statement in tenant_rls_statements("hoa_reserve_movement"):
            op.execute(statement)
    for table, columns in _columns().items():
        for column in columns:
            if not _has_column(table, column.name):
                op.add_column(table, column)


def downgrade() -> None:
    for table, columns in _columns().items():
        for column in reversed(columns):
            if _has_column(table, column.name):
                op.drop_column(table, column.name)
    for table in ("hoa_reserve_movement", "hoa_reserve"):
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
