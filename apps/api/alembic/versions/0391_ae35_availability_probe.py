"""AE35: own availability measurement (GB16-02, open question AD10-02).

Minute measuring points and monthly evaluation per measuring point (platform tables without RLS,
no tenant data, no personal data) and the platform switch ``maintenance_counts_as_downtime``
(default false: checks inside announced maintenance windows are left out of the rated figure).

Revision ID: 0391
Revises: 0390
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0391"
down_revision: str | None = "0390"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_settings",
        sa.Column(
            "maintenance_counts_as_downtime",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_table(
        "platform_availability_probe_point",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("probe", sa.String(length=20), nullable=False),
        sa.Column("slot", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_class", sa.String(length=40), nullable=True),
        sa.CheckConstraint(
            "probe IN ('api', 'crm', 'portal')", name="ck_platform_availability_probe_point_probe"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_availability_probe_point")),
        sa.UniqueConstraint(
            "probe", "slot", name="uq_platform_availability_probe_point_probe_slot"
        ),
    )
    op.create_index(
        "ix_platform_availability_probe_point_slot", "platform_availability_probe_point", ["slot"]
    )
    op.create_table(
        "platform_availability_month",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("probe", sa.String(length=20), nullable=False),
        sa.Column("checks_total", sa.Integer(), nullable=False),
        sa.Column("checks_ok", sa.Integer(), nullable=False),
        sa.Column("checks_maintenance", sa.Integer(), nullable=False),
        sa.Column("checks_ok_maintenance", sa.Integer(), nullable=False),
        sa.Column("expected_checks", sa.Integer(), nullable=False),
        sa.Column("uptime_gross", sa.Numeric(20, 8), nullable=False),
        sa.Column("uptime_net", sa.Numeric(20, 8), nullable=True),
        sa.Column("final", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "probe IN ('api', 'crm', 'portal')", name="ck_platform_availability_month_probe"
        ),
        sa.CheckConstraint(
            "checks_ok >= 0 AND checks_ok <= checks_total AND checks_maintenance >= 0"
            " AND checks_maintenance <= checks_total"
            " AND checks_ok_maintenance >= 0 AND checks_ok_maintenance <= checks_maintenance"
            " AND checks_ok_maintenance <= checks_ok AND expected_checks >= 0",
            name="ck_platform_availability_month_counts",
        ),
        sa.CheckConstraint(
            "uptime_gross >= 0 AND uptime_gross <= 100"
            " AND (uptime_net IS NULL OR (uptime_net >= 0 AND uptime_net <= 100))",
            name="ck_platform_availability_month_percent",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_availability_month")),
        sa.UniqueConstraint("month", "probe", name="uq_platform_availability_month_month_probe"),
    )


def downgrade() -> None:
    op.drop_table("platform_availability_month")
    op.drop_index(
        "ix_platform_availability_probe_point_slot", table_name="platform_availability_probe_point"
    )
    op.drop_table("platform_availability_probe_point")
    op.drop_column("platform_settings", "maintenance_counts_as_downtime")
