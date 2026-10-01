"""Admin fee setting fields and recurring plan auto post flag (GA03-06, GA03-07).

* ``admin_fee_setting``: ``manager_contact_id``, ``termination_date``, ``due_day_rule``,
  ``due_day``, ``account_id`` (revenue account), ``sev_fee_amount`` (NUMERIC(14,2)).
* ``recurring_invoice_plan.auto_post`` (default false).

Revision ID: 0312
Revises: 0311
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0312"
down_revision: str | None = "0311"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_fee_setting",
        sa.Column("manager_contact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_admin_fee_setting_manager_contact_id_contact",
        "admin_fee_setting",
        "contact",
        ["manager_contact_id"],
        ["id"],
    )
    op.add_column("admin_fee_setting", sa.Column("termination_date", sa.Date(), nullable=True))
    op.add_column("admin_fee_setting", sa.Column("due_day_rule", sa.String(16), nullable=True))
    op.add_column("admin_fee_setting", sa.Column("due_day", sa.Integer(), nullable=True))
    op.add_column(
        "admin_fee_setting",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_admin_fee_setting_account_id_ledger_account",
        "admin_fee_setting",
        "ledger_account",
        ["account_id"],
        ["id"],
    )
    op.add_column(
        "admin_fee_setting", sa.Column("sev_fee_amount", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column(
        "recurring_invoice_plan",
        sa.Column("auto_post", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("recurring_invoice_plan", "auto_post")
    op.drop_column("admin_fee_setting", "sev_fee_amount")
    op.drop_constraint(
        "fk_admin_fee_setting_account_id_ledger_account", "admin_fee_setting", type_="foreignkey"
    )
    op.drop_column("admin_fee_setting", "account_id")
    op.drop_column("admin_fee_setting", "due_day")
    op.drop_column("admin_fee_setting", "due_day_rule")
    op.drop_column("admin_fee_setting", "termination_date")
    op.drop_constraint(
        "fk_admin_fee_setting_manager_contact_id_contact", "admin_fee_setting", type_="foreignkey"
    )
    op.drop_column("admin_fee_setting", "manager_contact_id")
