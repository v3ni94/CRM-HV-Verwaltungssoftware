"""WEG asset report per reporting date (M24-02, W11) and loans in the annual statement
(M24-03): table ``hoa_asset_report`` with RLS and the column ``hoa_statement.loan_allocation``
(manager entered loan display configuration with legal basis, information only).

Revision ID: 0171
Revises: 0170
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0171"
down_revision: str | None = "0170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "hoa_asset_report"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(name)}


def upgrade() -> None:
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.UUID(), nullable=False),
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
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("updated_by", sa.UUID(), nullable=True),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("legal_entity_id", sa.UUID(), nullable=False),
            sa.Column("ledger_id", sa.UUID(), nullable=False),
            sa.Column("as_of", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("reserve_opening", sa.Numeric(14, 2), nullable=False),
            sa.Column("reserve_withdrawals", sa.Numeric(14, 2), nullable=False),
            sa.Column("reserve_interest", sa.Numeric(14, 2), nullable=False),
            sa.Column(
                "manual_items",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
            sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["legal_entity_id"],
                ["legal_entity.id"],
                name=op.f(f"fk_{TABLE}_legal_entity_id_legal_entity"),
            ),
            sa.ForeignKeyConstraint(
                ["ledger_id"], ["ledger.id"], name=op.f(f"fk_{TABLE}_ledger_id_ledger")
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        )
        op.create_index(op.f(f"ix_{TABLE}_tenant_id"), TABLE, ["tenant_id"], unique=False)
        op.create_index(f"ix_{TABLE}_ledger_as_of", TABLE, ["ledger_id", "as_of"], unique=False)
        for statement in tenant_rls_statements(TABLE):
            op.execute(statement)
    if "loan_allocation" not in _columns("hoa_statement"):
        op.add_column(
            "hoa_statement",
            sa.Column(
                "loan_allocation",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    if "loan_allocation" in _columns("hoa_statement"):
        op.drop_column("hoa_statement", "loan_allocation")
    if _has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
