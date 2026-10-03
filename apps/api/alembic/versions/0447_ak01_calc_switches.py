"""AK01 (GAI-202, GAI-214, GAI-204): persistent calculation switches on tenant_settings.

* ``heating_negative_costs_mode``: legacy_warn (default) | distribute
* ``hoa_remainder_mode``: report_only (default) | first_month | last_month
* ``check_amounts_tolerance_cents``: 1 (default) | 0

Defaults keep the previous behaviour; nothing is booked or released.

Revision ID: 0447
Revises: 0446
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0447"
down_revision: str | None = "0446"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "heating_negative_costs_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'legacy_warn'"),
        ),
    )
    op.add_column(
        "tenant_settings",
        sa.Column(
            "hoa_remainder_mode", sa.Text(), nullable=False, server_default=sa.text("'report_only'")
        ),
    )
    op.add_column(
        "tenant_settings",
        sa.Column(
            "check_amounts_tolerance_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_check_constraint(
        "heating_negative_costs_mode_values",
        "tenant_settings",
        "heating_negative_costs_mode IN ('legacy_warn', 'distribute')",
    )
    op.create_check_constraint(
        "hoa_remainder_mode_values",
        "tenant_settings",
        "hoa_remainder_mode IN ('report_only', 'first_month', 'last_month')",
    )
    op.create_check_constraint(
        "check_amounts_tolerance_cents_values",
        "tenant_settings",
        "check_amounts_tolerance_cents IN (0, 1)",
    )


def downgrade() -> None:
    for name in (
        "check_amounts_tolerance_cents_values",
        "hoa_remainder_mode_values",
        "heating_negative_costs_mode_values",
    ):
        op.drop_constraint(op.f(f"ck_tenant_settings_{name}"), "tenant_settings", type_="check")
    op.drop_column("tenant_settings", "check_amounts_tolerance_cents")
    op.drop_column("tenant_settings", "hoa_remainder_mode")
    op.drop_column("tenant_settings", "heating_negative_costs_mode")
