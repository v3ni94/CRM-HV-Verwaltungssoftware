"""listing_flow_fields: FLOW data contract fields on listing (M28-01 stage 3 preparation,
docs/rules/M28-01.md). No FLOWFACT call; external_uuid/external_ref/flowfact_entity_id are
kept for future idempotent handover only.

Revision ID: 0037
Revises: 0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing",
        sa.Column("object_type", sa.String(length=16), nullable=False, server_default="wohnung"),
    )
    op.add_column(
        "listing",
        sa.Column(
            "address_release",
            sa.String(length=16),
            nullable=False,
            server_default="vollstaendig",
        ),
    )
    op.add_column("listing", sa.Column("heating_type", sa.String(length=32), nullable=True))
    op.add_column("listing", sa.Column("energy_source", sa.String(length=32), nullable=True))
    op.add_column(
        "listing", sa.Column("heating_costs", sa.Numeric(precision=14, scale=2), nullable=True)
    )
    op.add_column(
        "listing",
        sa.Column(
            "heating_in_additional_costs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "listing", sa.Column("warm_rent", sa.Numeric(precision=14, scale=2), nullable=True)
    )
    op.add_column("listing", sa.Column("hoa_fee", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column(
        "listing", sa.Column("parking_price", sa.Numeric(precision=14, scale=2), nullable=True)
    )
    op.add_column(
        "listing",
        sa.Column(
            "energy_status",
            sa.String(length=16),
            nullable=False,
            server_default="in_erstellung",
        ),
    )
    op.add_column("listing", sa.Column("energy_type", sa.String(length=16), nullable=True))
    op.add_column(
        "listing", sa.Column("energy_value", sa.Numeric(precision=8, scale=2), nullable=True)
    )
    op.add_column("listing", sa.Column("energy_class", sa.String(length=4), nullable=True))
    op.add_column("listing", sa.Column("energy_year_of_installation", sa.Integer(), nullable=True))
    op.add_column("listing", sa.Column("energy_valid_until", sa.Date(), nullable=True))
    op.add_column(
        "listing",
        sa.Column(
            "energy_includes_hot_water",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "listing",
        sa.Column(
            "features",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("listing", sa.Column("commission_type", sa.String(length=16), nullable=True))
    op.add_column(
        "listing", sa.Column("external_uuid", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("listing", sa.Column("external_ref", sa.String(length=64), nullable=True))
    op.add_column("listing", sa.Column("flowfact_entity_id", sa.String(length=64), nullable=True))
    op.add_column(
        "listing",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="crm"),
    )
    op.create_index(
        "ux_listing_tenant_external_uuid",
        "listing",
        ["tenant_id", "external_uuid"],
        unique=True,
        postgresql_where=sa.text("external_uuid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_listing_tenant_external_uuid", table_name="listing")
    for column in (
        "source",
        "flowfact_entity_id",
        "external_ref",
        "external_uuid",
        "commission_type",
        "features",
        "energy_includes_hot_water",
        "energy_valid_until",
        "energy_year_of_installation",
        "energy_class",
        "energy_value",
        "energy_type",
        "energy_status",
        "parking_price",
        "hoa_fee",
        "warm_rent",
        "heating_in_additional_costs",
        "heating_costs",
        "energy_source",
        "heating_type",
        "address_release",
        "object_type",
    ):
        op.drop_column("listing", column)
