"""Tax flags per ledger account (SA-07, S711-05) and rule version register (S711-11).

* ``ledger_account``: ``eur_relevant``, ``ust_relevant`` and ``mixed_use_review`` as plain flags
  set by a person (default false); no tax treatment follows from them.
* ``rule_version``: register of versions of a domain rule with effective date, affected case
  groups and the recorded confirmation of an expert. A register only, RLS.

Idempotent: columns and table are created only when missing.

Revision ID: 0259
Revises: 0258
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0259"
down_revision: str | None = "0258"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FLAGS = ("eur_relevant", "ust_relevant", "mixed_use_review")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _stamp(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("ledger_account")}
    for flag in FLAGS:
        if flag not in existing:
            op.add_column(
                "ledger_account",
                sa.Column(flag, sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
    if inspector.has_table("rule_version"):
        return
    op.create_table(
        "rule_version",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", _uuid(), nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.Column("created_by", _uuid(), nullable=True),
        sa.Column("updated_by", _uuid(), nullable=True),
        sa.Column("rule_id", sa.String(60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "case_groups",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("source_status", sa.String(200), nullable=False),
        sa.Column("change_reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("expert_confirmed_by", sa.String(200), nullable=True),
        sa.Column("expert_confirmed_on", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_rule_version_period"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'withdrawn')",
            name=op.f("ck_rule_version_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_rule_version_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_version")),
        sa.UniqueConstraint(
            "tenant_id",
            "rule_id",
            "version",
            name=op.f("uq_rule_version_tenant_id_rule_id_version"),
        ),
    )
    op.create_index(
        "ix_rule_version_rule_effective",
        "rule_version",
        ["tenant_id", "rule_id", "effective_from"],
    )
    for statement in tenant_rls_statements("rule_version"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("rule_version"):
        op.execute(statement)
    op.drop_table("rule_version")
    for flag in FLAGS:
        op.drop_column("ledger_account", flag)
