"""S69-01: uniform status model of the statement objects (6.9.3, E03).

``owner_statement_status`` gets board_reviewed, resolved, issued, due, posted and locked;
``owner_statement`` gets ``status_log`` and ``posted_entry_ids``. New table
``reserve_statement`` (Rücklagenabrechnung per GdWE ledger and year) with the shared
``statement_status`` enum and RLS.

Revision ID: 0295
Revises: 0294
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0295"
down_revision: str | None = "0294"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "reserve_statement"
NEW_VALUES = ("board_reviewed", "resolved", "issued", "due", "posted", "locked")


def _json_list(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for value in NEW_VALUES:
            op.execute(f"ALTER TYPE owner_statement_status ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column("owner_statement", _json_list("status_log"))
    op.add_column("owner_statement", _json_list("posted_entry_ids"))

    status = postgresql.ENUM(name="statement_status", create_type=False)
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("hoa_statement_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("resolution_id", sa.Uuid(), nullable=True),
        _json_list("posted_entry_ids"),
        _json_list("status_log"),
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
            name=op.f("fk_reserve_statement_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"], ["ledger.id"], name=op.f("fk_reserve_statement_ledger_id_ledger")
        ),
        sa.ForeignKeyConstraint(
            ["hoa_statement_id"],
            ["hoa_statement.id"],
            name=op.f("fk_reserve_statement_hoa_statement_id_hoa_statement"),
        ),
        sa.ForeignKeyConstraint(
            ["resolution_id"],
            ["resolution.id"],
            name=op.f("fk_reserve_statement_resolution_id_resolution"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reserve_statement")),
    )
    op.create_index(
        "ix_reserve_statement_ledger", TABLE, ["tenant_id", "ledger_id", "year"], unique=False
    )
    op.create_index(
        "ix_reserve_statement_hoa_statement_id", TABLE, ["hoa_statement_id"], unique=False
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_reserve_statement_hoa_statement_id", table_name=TABLE)
    op.drop_index("ix_reserve_statement_ledger", table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_column("owner_statement", "posted_entry_ids")
    op.drop_column("owner_statement", "status_log")
    # The added enum values stay (PostgreSQL cannot drop enum values); rows using them must be
    # handled before a downgrade.
