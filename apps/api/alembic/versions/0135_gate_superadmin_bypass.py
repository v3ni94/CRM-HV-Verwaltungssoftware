"""Superadmin and release gate approval without four eyes (ADR 0011, operator decision
26.09.2026): ``app_user.is_superadmin`` (at most one row, partial unique index),
``release_gate_request.four_eyes`` (false only for a bypass approval) and the platform table
``platform_settings`` with the flag ``gate_superadmin_bypass`` (default false). Platform tables,
no RLS (section 5.3).

Revision ID: 0135
Revises: 0134
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0135"
down_revision: str | None = "0134"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "uq_app_user_superadmin",
        "app_user",
        ["is_superadmin"],
        unique=True,
        postgresql_where=sa.text("is_superadmin"),
    )
    op.add_column(
        "release_gate_request",
        sa.Column("four_eyes", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "platform_settings",
        sa.Column(
            "gate_superadmin_bypass",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_settings")),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_column("release_gate_request", "four_eyes")
    op.drop_index("uq_app_user_superadmin", table_name="app_user")
    op.drop_column("app_user", "is_superadmin")
