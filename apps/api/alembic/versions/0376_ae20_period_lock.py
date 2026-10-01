"""AE20 / P06-02: period lock per property and period, tenant switches (default conservative).

* ``period_lock``: lock of a property for a period (manual or from a closed statement); a
  release keeps the row.
* ``period_lock_setting``: one row per tenant, no row means the defaults.

Revision ID: 0376
Revises: 0375
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0376"
down_revision: str | None = "0375"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("period_lock", "period_lock_setting")


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


def upgrade() -> None:
    op.create_table(
        "period_lock",
        *_common("period_lock"),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("statement_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", sa.Uuid(), nullable=True),
        sa.Column("release_reason", sa.String(500), nullable=True),
        sa.Column("release_requested_by", sa.Uuid(), nullable=True),
        sa.Column("release_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_request_reason", sa.String(500), nullable=True),
        sa.CheckConstraint("period_from <= period_to", name=op.f("ck_period_lock_period")),
        sa.CheckConstraint(
            "source IN ('manual', 'statement', 'owner_statement')",
            name=op.f("ck_period_lock_source"),
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"], ["ledger.id"], name=op.f("fk_period_lock_ledger_id_ledger")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["property.id"], name=op.f("fk_period_lock_property_id_property")
        ),
    )
    op.create_index(
        "ix_period_lock_property", "period_lock", ["tenant_id", "ledger_id", "property_id"]
    )
    op.create_index(
        "uq_period_lock_statement_active",
        "period_lock",
        ["tenant_id", "source", "statement_id"],
        unique=True,
        postgresql_where=sa.text("statement_id IS NOT NULL AND released_at IS NULL"),
    )
    op.create_table(
        "period_lock_setting",
        *_common("period_lock_setting"),
        sa.Column("lock_mode", sa.String(20), nullable=False, server_default="ledger_only"),
        sa.Column("auto_lock_on_close", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reopen_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint(
            "lock_mode IN ('ledger_only', 'object_period')",
            name=op.f("ck_period_lock_setting_lock_mode"),
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_period_lock_setting_tenant_id")),
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
