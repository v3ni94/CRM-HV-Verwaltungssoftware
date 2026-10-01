"""AD10: maintenance windows (GB16-01) and monthly availability figures (GB16-02).

Platform tables without RLS (section 5.3), no tenant data.

Revision ID: 0355
Revises: 0354
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0355"
down_revision: str | None = "0354"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_maintenance_window",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text_de", sa.Text(), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=False),
        sa.Column("notice_hours", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("ends_at > starts_at", name="ck_platform_maintenance_window_period"),
        sa.CheckConstraint(
            "notice_hours IS NULL OR (notice_hours >= 0 AND notice_hours <= 720)",
            name="ck_platform_maintenance_window_notice",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_maintenance_window")),
    )
    op.create_index(
        "ix_platform_maintenance_window_starts_at", "platform_maintenance_window", ["starts_at"]
    )
    op.create_table(
        "platform_availability_measurement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("probe", sa.String(length=20), nullable=False),
        sa.Column("uptime_percent", sa.Numeric(20, 8), nullable=False),
        sa.Column("source_note", sa.String(length=200), nullable=False),
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
            "uptime_percent >= 0 AND uptime_percent <= 100",
            name="ck_platform_availability_measurement_percent",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_availability_measurement")),
        sa.UniqueConstraint(
            "month", "probe", name="uq_platform_availability_measurement_month_probe"
        ),
    )


def downgrade() -> None:
    op.drop_table("platform_availability_measurement")
    op.drop_index(
        "ix_platform_maintenance_window_starts_at", table_name="platform_maintenance_window"
    )
    op.drop_table("platform_maintenance_window")
