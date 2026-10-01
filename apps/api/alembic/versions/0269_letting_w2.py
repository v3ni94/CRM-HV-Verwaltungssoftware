"""Letting wave 2 (M26-02, M26-03, M26-04, M26-06) and calendar feed token (M23-06).

Revision ID: 0269
Revises: 0268
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0269"
down_revision: str | None = "0268"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uid = postgresql.UUID(as_uuid=True)


def _base() -> list[sa.Column[object]]:
    stamp = sa.text("now()")
    return [
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("created_by", uid, nullable=True),
        sa.Column("updated_by", uid, nullable=True),
    ]


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"],
        ["tenant.id"],
        name=op.f(f"fk_{table}_tenant_id_tenant"),
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.add_column(
        "rent_increase_case",
        sa.Column(
            "basis_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("prospect", sa.Column("listing_id", uid, nullable=True))
    op.add_column(
        "prospect",
        sa.Column(
            "search_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_foreign_key(
        op.f("fk_prospect_listing_id_listing"),
        "prospect",
        "listing",
        ["listing_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "rent_index_entry",
        *_base(),
        sa.Column("municipality", sa.String(120), nullable=False),
        sa.Column("index_name", sa.String(300), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("year_built_from", sa.Integer(), nullable=True),
        sa.Column("year_built_to", sa.Integer(), nullable=True),
        sa.Column("area_from_sqm", sa.Numeric(10, 2), nullable=True),
        sa.Column("area_to_sqm", sa.Numeric(10, 2), nullable=True),
        sa.Column("equipment", sa.String(120), nullable=True),
        sa.Column("rent_min", sa.Numeric(20, 8), nullable=False),
        sa.Column("rent_mid", sa.Numeric(20, 8), nullable=True),
        sa.Column("rent_max", sa.Numeric(20, 8), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        _tenant_fk("rent_index_entry"),
        sa.CheckConstraint("rent_min <= rent_max", name="rent_index_entry_range"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rent_index_entry")),
    )
    op.create_index(
        "ix_rent_index_entry_lookup",
        "rent_index_entry",
        ["tenant_id", "municipality", "valid_from"],
    )

    op.create_table(
        "vacancy_case",
        *_base(),
        sa.Column("unit_id", uid, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'open'")),
        sa.Column("responsible_user_id", uid, nullable=True),
        sa.Column("follow_up_on", sa.Date(), nullable=True),
        sa.Column("target_rent", sa.Numeric(14, 2), nullable=True),
        sa.Column("monthly_costs", sa.Numeric(14, 2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _tenant_fk("vacancy_case"),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["unit.id"],
            name=op.f("fk_vacancy_case_unit_id_unit"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_case")),
    )
    op.create_index("ux_vacancy_case_unit", "vacancy_case", ["tenant_id", "unit_id"], unique=True)

    op.create_table(
        "calendar_feed_token",
        *_base(),
        sa.Column("user_id", uid, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "include_contracts", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "include_properties", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        _tenant_fk("calendar_feed_token"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_feed_token")),
    )
    op.create_index(
        "ux_calendar_feed_token_hash", "calendar_feed_token", ["token_hash"], unique=True
    )
    op.create_index("ix_calendar_feed_token_user", "calendar_feed_token", ["tenant_id", "user_id"])
    for table in ("rent_index_entry", "vacancy_case", "calendar_feed_token"):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in ("calendar_feed_token", "vacancy_case", "rent_index_entry"):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
    op.drop_constraint(op.f("fk_prospect_listing_id_listing"), "prospect", type_="foreignkey")
    op.drop_column("prospect", "search_profile")
    op.drop_column("prospect", "listing_id")
    op.drop_column("rent_increase_case", "basis_data")
