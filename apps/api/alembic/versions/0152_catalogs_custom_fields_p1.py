"""Catalogues and custom fields (P1 AP4, spec 4.11 and annex B).

``catalog_entry.is_system`` marks the annex B system entries that are seeded per tenant
(idempotent on tenant, catalogue, code); tenants may add own entries and deactivate system
entries but never delete them. Existing default entries (meter types, provider contract
types, contact categories, payment types) become system entries. ``custom_field_definition``
receives the attributes of 4.11: group, validity per management type and contract kind,
uniqueness, visibility in the main view, minimum, maximum, default value, choice options,
description and sort order. Code enums that mirror an annex B list stay in place (operator
decision 27.09.2026); catalogues serve new fields.

Both tables force row level security (ADR 0002); the seed runs as the migrator without a
tenant context, so the force is lifted for the seed and restored afterwards.

Revision ID: 0152
Revises: 0151
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.properties.catalogs import ANNEX_B_CATALOGS

revision: str = "0152"
down_revision: str | None = "0151"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATALOG = "catalog_entry"
FIELDS = "custom_field_definition"
# Catalogues seeded before this revision by ``ensure_tenant_defaults`` (M4 defaults).
LEGACY_CATALOGS = (
    "meter_type",
    "provider_contract_type",
    "property_contact_category",
    "payment_type",
)


def _seed_system_entries() -> None:
    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id FROM tenant")).scalars().all()
    existing = {
        (row.tenant_id, row.catalog, row.code)
        for row in conn.execute(sa.text("SELECT tenant_id, catalog, code FROM catalog_entry"))
    }
    insert = sa.text(
        "INSERT INTO catalog_entry (id, tenant_id, catalog, code, label, sort_order, active,"
        " is_system, created_at, updated_at) VALUES (:id, :tenant_id, :catalog, :code, :label,"
        " :sort_order, true, true, now(), now())"
    )
    for tenant_id in tenants:
        rows = [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "catalog": catalog,
                "code": code,
                "label": label,
                "sort_order": order,
            }
            for catalog, entries in ANNEX_B_CATALOGS.items()
            for order, (code, label) in enumerate(entries)
            if (tenant_id, catalog, code) not in existing
        ]
        if rows:
            conn.execute(insert, rows)


def upgrade() -> None:
    op.add_column(
        CATALOG,
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(FIELDS, sa.Column("group", sa.String(length=100), nullable=True))
    op.add_column(
        FIELDS,
        sa.Column(
            "valid_for_management_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        FIELDS,
        sa.Column(
            "valid_for_contract_kinds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        FIELDS,
        sa.Column(
            "uniqueness", sa.String(length=16), nullable=False, server_default=sa.text("'none'")
        ),
    )
    op.add_column(
        FIELDS,
        sa.Column("visible_in_main", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(FIELDS, sa.Column("min_value", sa.Numeric(precision=20, scale=8), nullable=True))
    op.add_column(FIELDS, sa.Column("max_value", sa.Numeric(precision=20, scale=8), nullable=True))
    op.add_column(
        FIELDS,
        sa.Column("default_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        FIELDS,
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(FIELDS, sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        FIELDS,
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.execute(f"ALTER TABLE {CATALOG} NO FORCE ROW LEVEL SECURITY")
    op.get_bind().execute(
        sa.text("UPDATE catalog_entry SET is_system = true WHERE catalog = ANY(:names)"),
        {"names": list(LEGACY_CATALOGS)},
    )
    _seed_system_entries()
    op.execute(f"ALTER TABLE {CATALOG} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {CATALOG} NO FORCE ROW LEVEL SECURITY")
    # Entries of the annex B catalogues introduced here are removed; the legacy catalogues
    # and property_type keep their rows (they existed before and may be referenced by
    # properties and meters).
    kept = (*LEGACY_CATALOGS, "property_type")
    op.get_bind().execute(
        sa.text("DELETE FROM catalog_entry WHERE is_system AND catalog = ANY(:names)"),
        {"names": [c for c in ANNEX_B_CATALOGS if c not in kept]},
    )
    op.execute(f"ALTER TABLE {CATALOG} FORCE ROW LEVEL SECURITY")
    for column in (
        "sort_order",
        "description",
        "options",
        "default_value",
        "max_value",
        "min_value",
        "visible_in_main",
        "uniqueness",
        "valid_for_contract_kinds",
        "valid_for_management_types",
        "group",
    ):
        op.drop_column(FIELDS, column)
    op.drop_column(CATALOG, "is_system")
