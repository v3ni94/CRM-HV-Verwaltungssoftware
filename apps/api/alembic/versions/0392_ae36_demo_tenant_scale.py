"""AE36 (AA15-01, AC09-01): demo tenant flag and scale monitoring of the platform.

* ``tenant.is_demo``: demo tenant with invented data only, excluded from platform billing,
  exports, DATEV and statistics (rule AE36-DEMO). The demo tenant ``demo-muster`` of
  ``make seed-demo`` (package AA15) gets the flag as backfill.
* ``platform_scale_setting``: one row with the operator thresholds for the partitioning
  triggers of ADR 0021 (proposals, decision AC09-01 open). Created on first use, not here.
* ``platform_scale_snapshot``: weekly measurement (row counts, sizes, P95, triggers).

Platform tables without RLS (section 5.3), no tenant data.

Revision ID: 0392
Revises: 0391
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0392"
down_revision: str | None = "0391"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
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
    ]


def upgrade() -> None:
    op.add_column(
        "tenant",
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute("UPDATE tenant SET is_demo = true WHERE slug = 'demo-muster'")
    op.create_table(
        "platform_scale_setting",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rows_threshold", sa.BigInteger(), server_default="20000000", nullable=False),
        sa.Column("size_gb_threshold", sa.Integer(), server_default="50", nullable=False),
        sa.Column("p95_ms_threshold", sa.Integer(), server_default="300", nullable=False),
        sa.Column("p95_deep_ms_threshold", sa.Integer(), server_default="1000", nullable=False),
        sa.Column("p95_weeks", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "restore_seconds_threshold", sa.Integer(), server_default="14400", nullable=False
        ),
        sa.Column("tenants_review_threshold", sa.Integer(), server_default="20", nullable=False),
        sa.Column("alarm_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "rows_threshold > 0 AND size_gb_threshold > 0 AND p95_ms_threshold > 0 "
            "AND p95_deep_ms_threshold > 0 AND p95_weeks BETWEEN 1 AND 52 "
            "AND restore_seconds_threshold > 0 AND tenants_review_threshold > 0",
            name=op.f("ck_platform_scale_setting_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_scale_setting")),
    )
    op.create_table(
        "platform_scale_snapshot",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("iso_week", sa.String(length=8), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "tables",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "latency",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("restore_seconds", sa.Integer(), nullable=True),
        sa.Column("tenants_productive", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tenants_demo", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "triggers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=16), server_default="job", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_scale_snapshot")),
        sa.UniqueConstraint("iso_week", name=op.f("uq_platform_scale_snapshot_iso_week")),
    )


def downgrade() -> None:
    op.drop_table("platform_scale_snapshot")
    op.drop_table("platform_scale_setting")
    op.drop_column("tenant", "is_demo")
