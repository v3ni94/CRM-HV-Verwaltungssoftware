"""AE05 / P01-01: withholding taxes on credit interest.

* ``ledger_interest_tax_config``: tax accounts per ledger (Kapitalertragsteuer,
  Solidaritätszuschlag, Kirchensteuer), no tax rate.
* ``interest_tax_withholding``: amounts from the bank document per interest entry.

Revision ID: 0361
Revises: 0360
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0361"
down_revision: str | None = "0360"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("ledger_interest_tax_config", "interest_tax_withholding")


def _common(table: str) -> list[sa.SchemaItem]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=op.f(f"fk_{table}_{column}_{target}"), ondelete=ondelete
    )


def _money(name: str) -> sa.Column:
    return sa.Column(name, sa.Numeric(14, 2), server_default="0", nullable=False)


def upgrade() -> None:
    t = "ledger_interest_tax_config"
    op.create_table(
        t,
        *_common(t),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("capital_gains_tax_account_id", sa.Uuid(), nullable=True),
        sa.Column("solidarity_tax_account_id", sa.Uuid(), nullable=True),
        sa.Column("church_tax_account_id", sa.Uuid(), nullable=True),
        _fk(t, "ledger_id", "ledger", "CASCADE"),
        _fk(t, "capital_gains_tax_account_id", "ledger_account", "RESTRICT"),
        _fk(t, "solidarity_tax_account_id", "ledger_account", "RESTRICT"),
        _fk(t, "church_tax_account_id", "ledger_account", "RESTRICT"),
        sa.UniqueConstraint("ledger_id", name=op.f(f"uq_{t}_ledger_id")),
    )
    t = "interest_tax_withholding"
    op.create_table(
        t,
        *_common(t),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        _money("capital_gains_tax"),
        _money("solidarity_tax"),
        _money("church_tax"),
        _fk(t, "journal_entry_id", "journal_entry", "RESTRICT"),
        _fk(t, "ledger_id", "ledger", "RESTRICT"),
        _fk(t, "bank_account_id", "ledger_account", "RESTRICT"),
        sa.UniqueConstraint("journal_entry_id", name=op.f(f"uq_{t}_journal_entry_id")),
        sa.CheckConstraint(
            "capital_gains_tax >= 0 AND solidarity_tax >= 0 AND church_tax >= 0",
            name=op.f(f"ck_{t}_non_negative"),
        ),
        sa.CheckConstraint(
            "capital_gains_tax + solidarity_tax + church_tax < gross_amount",
            name=op.f(f"ck_{t}_below_gross"),
        ),
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
