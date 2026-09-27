"""Receivable rules M13-01 to M13-03 (7.5 Sollstellung): pro rata rule per contract, payment
mode and amount basis per schedule, tenant rule switch (default off), calculation path per
run, net and tax part and covered period per item.

Revision ID: 0177
Revises: 0176
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0177"
down_revision: str | None = "0176"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(14, 2)

COLUMNS: dict[str, list[sa.Column[Any]]] = {
    "contract": [sa.Column("proration_method", sa.String(length=16), nullable=True)],
    "payment_schedule": [
        sa.Column("payment_mode", sa.String(length=16), nullable=False, server_default="advance"),
        sa.Column("amount_basis", sa.String(length=16), nullable=False, server_default="per_month"),
    ],
    "tenant_settings": [
        sa.Column(
            "receivable_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        )
    ],
    "receivable_run": [
        sa.Column(
            "calculation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        )
    ],
    "receivable_item": [
        sa.Column("net_amount", MONEY, nullable=True),
        sa.Column("vat_amount", MONEY, nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
    ],
}

CHECKS = {
    "contract": (
        "ck_contract_proration_method",
        "proration_method IS NULL OR "
        "proration_method IN ('calendar_days', 'thirty_360', 'full_month')",
    ),
    "payment_schedule": (
        "ck_payment_schedule_mode_basis",
        "payment_mode IN ('advance', 'arrears') AND "
        "amount_basis IN ('per_month', 'per_instalment')",
    ),
}


def _existing_columns(name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(name)}


def _existing_checks(name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(c["name"]) for c in inspector.get_check_constraints(name) if c.get("name")}


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        existing = _existing_columns(table)
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    for table, (name, expression) in CHECKS.items():
        existing = _existing_checks(table)
        # The naming convention prefixes "ck_<table>_" again; accept both spellings so the
        # migration stays idempotent on databases that already carry the constraint.
        if name not in existing and f"ck_{table}_{name}" not in existing:
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression})")


def downgrade() -> None:
    for table, (name, _) in CHECKS.items():
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{name}")
    for table, columns in COLUMNS.items():
        existing = _existing_columns(table)
        for column in columns:
            if column.name in existing:
                op.drop_column(table, column.name)
