"""properties: P1 additions for building and unit (Ergänzung CRM sections 4.3 and 4.4, AP2).

Building: address addition, full energy certificate (law, type, final energy heat and
electricity, hot water included, heating type, energy sources, class, construction year,
issue date, validity) and ``version`` for ETag updates. The energy certificate lives only on
the building (operator decision 26.09.2026): existing property level values are copied into
the buildings of the property (every building of the property receives them when the
property has several, because the source data does not say which building the certificate
belongs to; the operator corrects this per building) and the property columns are removed.
``building.energy_certificate_value`` is renamed to ``energy_final_heat_kwh``.

Unit: ``version``, commission with note, deposit amount (informational, no posting), VAT
option for vacancy periods; tables ``unit_vacancy_allocation_value`` (key values during
vacancy with history) and ``meter_change`` (final reading of the old device, initial reading
of the new one). New tenant tables get RLS (ADR 0002).

Revision ID: 0149
Revises: 0148
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0149"
down_revision: str | None = "0148"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("unit_vacancy_allocation_value", "meter_change")

PROPERTY_ENERGY_COLUMNS = (
    "energy_certificate_type",
    "energy_certificate_value",
    "energy_certificate_source",
    "energy_certificate_construction_year",
    "energy_certificate_issued_on",
    "energy_certificate_valid_until",
    "energy_certificate_class",
)

# Property values fill only empty building values; a certificate already entered on a
# building wins.
MIGRATE_ENERGY_SQL = """
UPDATE building b SET
    energy_certificate_type = COALESCE(b.energy_certificate_type, p.energy_certificate_type),
    energy_final_heat_kwh = COALESCE(b.energy_final_heat_kwh, p.energy_certificate_value),
    energy_sources = CASE
        WHEN cardinality(b.energy_sources) = 0 AND p.energy_certificate_source IS NOT NULL
        THEN ARRAY[p.energy_certificate_source] ELSE b.energy_sources END,
    energy_certificate_construction_year = COALESCE(
        b.energy_certificate_construction_year, p.energy_certificate_construction_year),
    energy_certificate_issued_on = COALESCE(
        b.energy_certificate_issued_on, p.energy_certificate_issued_on),
    energy_certificate_valid_until = COALESCE(
        b.energy_certificate_valid_until, p.energy_certificate_valid_until),
    energy_certificate_class = COALESCE(b.energy_certificate_class, p.energy_certificate_class)
FROM property p
WHERE p.id = b.property_id AND (
    p.energy_certificate_type IS NOT NULL OR p.energy_certificate_value IS NOT NULL
    OR p.energy_certificate_source IS NOT NULL
    OR p.energy_certificate_construction_year IS NOT NULL
    OR p.energy_certificate_issued_on IS NOT NULL
    OR p.energy_certificate_valid_until IS NOT NULL
    OR p.energy_certificate_class IS NOT NULL)
"""


def _audit_columns() -> list[sa.Column[Any]]:
    return [
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
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    ]


def upgrade() -> None:
    # building
    op.add_column("building", sa.Column("address_addition", sa.String(length=200), nullable=True))
    op.add_column(
        "building", sa.Column("energy_certificate_law", sa.String(length=16), nullable=True)
    )
    op.alter_column("building", "energy_certificate_value", new_column_name="energy_final_heat_kwh")
    op.add_column(
        "building",
        sa.Column(
            "energy_hot_water_included", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "building",
        sa.Column("energy_final_electricity_kwh", sa.Numeric(precision=20, scale=8), nullable=True),
    )
    op.add_column("building", sa.Column("heating_type_code", sa.String(length=32), nullable=True))
    op.add_column(
        "building",
        sa.Column(
            "energy_sources",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "building", sa.Column("energy_certificate_class", sa.String(length=4), nullable=True)
    )
    op.add_column(
        "building", sa.Column("energy_certificate_construction_year", sa.Integer(), nullable=True)
    )
    op.add_column("building", sa.Column("energy_certificate_issued_on", sa.Date(), nullable=True))
    op.add_column(
        "building", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    for column in ("energy_hot_water_included", "energy_sources", "version"):
        op.alter_column("building", column, server_default=None)
    op.execute(MIGRATE_ENERGY_SQL)
    for column in PROPERTY_ENERGY_COLUMNS:
        op.drop_column("property", column)

    # unit
    op.add_column("unit", sa.Column("commission", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column("unit", sa.Column("commission_note", sa.Text(), nullable=True))
    op.add_column(
        "unit", sa.Column("deposit_amount", sa.Numeric(precision=14, scale=2), nullable=True)
    )
    op.add_column(
        "unit",
        sa.Column(
            "vacancy_vat_option",
            postgresql.ENUM(name="vat_option", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("unit", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("unit", "version", server_default=None)

    op.create_table(
        "unit_vacancy_allocation_value",
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("allocation_key_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        *_audit_columns(),
        postgresql.ExcludeConstraint(
            (sa.column("unit_id"), "="),
            (sa.column("allocation_key_id"), "="),
            (sa.text("daterange(valid_from, valid_to, '[]')"), "&&"),
            using="gist",
            name="ex_unit_vacancy_allocation_value_period",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_unit_vacancy_allocation_value_period_order"),
        ),
        sa.ForeignKeyConstraint(
            ["allocation_key_id"],
            ["allocation_key.id"],
            name=op.f("fk_unit_vacancy_allocation_value_allocation_key_id_allocation_key"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_unit_vacancy_allocation_value_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["unit.id"],
            name=op.f("fk_unit_vacancy_allocation_value_unit_id_unit"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_vacancy_allocation_value")),
    )
    op.create_index(
        op.f("ix_unit_vacancy_allocation_value_allocation_key_id"),
        "unit_vacancy_allocation_value",
        ["allocation_key_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_unit_vacancy_allocation_value_unit_id"),
        "unit_vacancy_allocation_value",
        ["unit_id"],
        unique=False,
    )
    op.create_table(
        "meter_change",
        sa.Column("meter_id", sa.UUID(), nullable=False),
        sa.Column("changed_on", sa.Date(), nullable=False),
        sa.Column("old_number", sa.String(length=100), nullable=False),
        sa.Column("new_number", sa.String(length=100), nullable=True),
        sa.Column("old_final_value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("new_initial_value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["meter_id"],
            ["meter.id"],
            name=op.f("fk_meter_change_meter_id_meter"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_meter_change_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meter_change")),
    )
    op.create_index(op.f("ix_meter_change_meter_id"), "meter_change", ["meter_id"], unique=False)
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index(op.f("ix_meter_change_meter_id"), table_name="meter_change")
    op.drop_table("meter_change")
    op.drop_index(
        op.f("ix_unit_vacancy_allocation_value_unit_id"), table_name="unit_vacancy_allocation_value"
    )
    op.drop_index(
        op.f("ix_unit_vacancy_allocation_value_allocation_key_id"),
        table_name="unit_vacancy_allocation_value",
    )
    op.drop_table("unit_vacancy_allocation_value")
    for column in (
        "version",
        "vacancy_vat_option",
        "deposit_amount",
        "commission_note",
        "commission",
    ):
        op.drop_column("unit", column)
    # property level certificate columns return empty: the building keeps the values.
    op.add_column(
        "property", sa.Column("energy_certificate_value", sa.Numeric(8, 2), nullable=True)
    )
    op.add_column(
        "property", sa.Column("energy_certificate_construction_year", sa.Integer(), nullable=True)
    )
    op.add_column(
        "property", sa.Column("energy_certificate_source", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "property", sa.Column("energy_certificate_class", sa.String(length=4), nullable=True)
    )
    op.add_column(
        "property", sa.Column("energy_certificate_type", sa.String(length=16), nullable=True)
    )
    op.add_column("property", sa.Column("energy_certificate_valid_until", sa.Date(), nullable=True))
    op.add_column("property", sa.Column("energy_certificate_issued_on", sa.Date(), nullable=True))
    for column in (
        "version",
        "energy_certificate_issued_on",
        "energy_certificate_construction_year",
        "energy_certificate_class",
        "energy_sources",
        "heating_type_code",
        "energy_final_electricity_kwh",
        "energy_hot_water_included",
        "energy_certificate_law",
        "address_addition",
    ):
        op.drop_column("building", column)
    op.alter_column("building", "energy_final_heat_kwh", new_column_name="energy_certificate_value")
