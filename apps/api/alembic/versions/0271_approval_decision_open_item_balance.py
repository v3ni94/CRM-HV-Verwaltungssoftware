"""Central approval decisions and maintained open item remainders (S69-02, S69-03, S69-04).

``approval_decision``: approval of a payment order or invoice bound to a subject hash, with a
persisted ``invalidated`` status and person check warnings. ``open_item_balance``: read copy
of open item remainders per cut-off date, refreshed by a job. Both with RLS.

Revision ID: 0271
Revises: 0270
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0271"
down_revision: str | None = "0270"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uid = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenant.id"], name=op.f(f"fk_{table}_tenant_id_tenant"), ondelete="RESTRICT"
    )


def upgrade() -> None:
    op.create_table(
        "approval_decision",
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", uid, nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("user_id", uid, nullable=False),
        sa.Column("subject_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'valid'")),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason", sa.String(200), nullable=True),
        sa.Column("legacy_ref_id", uid, nullable=True),
        sa.Column(
            "warnings",
            postgresql.ARRAY(sa.String(300)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        _tenant_fk("approval_decision"),
        sa.CheckConstraint(
            "subject_type IN ('payment_order', 'invoice')",
            name=op.f("ck_approval_decision_subject_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('valid', 'invalidated')", name=op.f("ck_approval_decision_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_decision")),
    )
    op.create_index(
        "ix_approval_decision_subject",
        "approval_decision",
        ["tenant_id", "subject_type", "subject_id"],
    )
    for statement in tenant_rls_statements("approval_decision"):
        op.execute(statement)

    op.create_table(
        "open_item_balance",
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("ledger_id", uid, nullable=False),
        sa.Column("open_item_id", uid, nullable=False),
        sa.Column("account_id", uid, nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("remaining", sa.Numeric(14, 2), nullable=False),
        sa.Column("contract_id", uid, nullable=True),
        sa.Column("source", sa.String(8), nullable=False, server_default=sa.text("'job'")),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        _tenant_fk("open_item_balance"),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledger.id"],
            name=op.f("fk_open_item_balance_ledger_id_ledger"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["open_item_id"],
            ["open_item.id"],
            name=op.f("fk_open_item_balance_open_item_id_open_item"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ledger_account.id"],
            name=op.f("fk_open_item_balance_account_id_ledger_account"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("open_item_id", "as_of", name="uq_open_item_balance_item_as_of"),
        sa.CheckConstraint(
            "source IN ('job', 'manual')", name=op.f("ck_open_item_balance_source_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_open_item_balance")),
    )
    op.create_index(
        "ix_open_item_balance_ledger_as_of",
        "open_item_balance",
        ["tenant_id", "ledger_id", "as_of"],
    )
    for statement in tenant_rls_statements("open_item_balance"):
        op.execute(statement)


def downgrade() -> None:
    for table in ("open_item_balance", "approval_decision"):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
