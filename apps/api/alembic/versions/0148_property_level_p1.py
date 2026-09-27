"""properties: P1 additions at property level (Ergänzung CRM section 4.2, AP2).

Owner of a rental property with clearing account, management power of attorney and tax
advisor; bank account with assigned ledger account; statement periods per kind
(``property_billing_period``, non overlapping per property and kind, with the board's online
receipt check flag); sub communities of a Mehrhausanlage (``sub_community``, referenced by
``unit.sub_community_id``); the Objektmappe (``property_portal_document``); provider relation
with customer number, Freistellungsbescheinigung status and creditor account. All account
references point to ``ledger_account`` and are informational, no posting reads them yet.
New tenant tables get RLS (ADR 0002); new columns inherit the RLS of their tables.

Revision ID: 0148
Revises: 0147
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0148"
down_revision: str | None = "0147"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("property_billing_period", "sub_community", "property_portal_document")


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
    billing_period_kind = postgresql.ENUM(
        "hoa",
        "operating_costs",
        "heating_costs",
        "economic_plan",
        "owner_statement",
        name="billing_period_kind",
        create_type=False,
    )
    billing_period_kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "property_billing_period",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("kind", billing_period_kind, nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("board_online_audit", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        postgresql.ExcludeConstraint(
            (sa.column("property_id"), "="),
            (sa.column("kind"), "="),
            (sa.text("daterange(valid_from, valid_to, '[]')"), "&&"),
            using="gist",
            name="ex_property_billing_period",
        ),
        sa.CheckConstraint(
            "valid_to >= valid_from", name=op.f("ck_property_billing_period_period_order")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_billing_period_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_property_billing_period_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_billing_period")),
    )
    op.create_index(
        op.f("ix_property_billing_period_property_id"),
        "property_billing_period",
        ["property_id"],
        unique=False,
    )
    op.create_table(
        "sub_community",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_sub_community_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_sub_community_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sub_community")),
        sa.UniqueConstraint(
            "tenant_id",
            "property_id",
            "code",
            name=op.f("uq_sub_community_tenant_id_property_id_code"),
        ),
    )
    op.create_index(
        op.f("ix_sub_community_property_id"), "sub_community", ["property_id"], unique=False
    )
    op.create_table(
        "property_portal_document",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("visible_for", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_property_portal_document_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_portal_document_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_property_portal_document_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_portal_document")),
        sa.UniqueConstraint(
            "tenant_id",
            "property_id",
            "document_id",
            name=op.f("uq_property_portal_document_tenant_id_property_id_document_id"),
        ),
    )
    op.create_index(
        op.f("ix_property_portal_document_document_id"),
        "property_portal_document",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_portal_document_property_id"),
        "property_portal_document",
        ["property_id"],
        unique=False,
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)

    # property_bank_account: assigned ledger account
    op.add_column("property_bank_account", sa.Column("ledger_account_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_property_bank_account_ledger_account_id"),
        "property_bank_account",
        ["ledger_account_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_property_bank_account_ledger_account_id_ledger_account"),
        "property_bank_account",
        "ledger_account",
        ["ledger_account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # property_owner: clearing account, power of attorney, tax advisor
    op.add_column("property_owner", sa.Column("clearing_account_id", sa.UUID(), nullable=True))
    op.add_column(
        "property_owner", sa.Column("power_of_attorney_document_id", sa.UUID(), nullable=True)
    )
    op.add_column("property_owner", sa.Column("tax_advisor_contact_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_property_owner_clearing_account_id"),
        "property_owner",
        ["clearing_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_owner_power_of_attorney_document_id"),
        "property_owner",
        ["power_of_attorney_document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_owner_tax_advisor_contact_id"),
        "property_owner",
        ["tax_advisor_contact_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_property_owner_power_of_attorney_document_id_document"),
        "property_owner",
        "document",
        ["power_of_attorney_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_property_owner_tax_advisor_contact_id_contact"),
        "property_owner",
        "contact",
        ["tax_advisor_contact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_property_owner_clearing_account_id_ledger_account"),
        "property_owner",
        "ledger_account",
        ["clearing_account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # service_provider_relation: customer number, exemption certificate, creditor account
    exemption = postgresql.ENUM(
        "valid", "none", "invalid", name="exemption_cert_status", create_type=False
    )
    exemption.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "service_provider_relation",
        sa.Column("customer_number", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "service_provider_relation",
        sa.Column("exemption_cert_status", exemption, nullable=True),
    )
    op.add_column(
        "service_provider_relation",
        sa.Column("exemption_cert_valid_until", sa.Date(), nullable=True),
    )
    op.add_column(
        "service_provider_relation", sa.Column("creditor_account_id", sa.UUID(), nullable=True)
    )
    op.create_index(
        op.f("ix_service_provider_relation_creditor_account_id"),
        "service_provider_relation",
        ["creditor_account_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_service_provider_relation_creditor_account_id_ledger_account"),
        "service_provider_relation",
        "ledger_account",
        ["creditor_account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # unit: sub community
    op.add_column("unit", sa.Column("sub_community_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_unit_sub_community_id"), "unit", ["sub_community_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_unit_sub_community_id_sub_community"),
        "unit",
        "sub_community",
        ["sub_community_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_unit_sub_community_id_sub_community"), "unit", type_="foreignkey")
    op.drop_index(op.f("ix_unit_sub_community_id"), table_name="unit")
    op.drop_column("unit", "sub_community_id")
    op.drop_constraint(
        op.f("fk_service_provider_relation_creditor_account_id_ledger_account"),
        "service_provider_relation",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_service_provider_relation_creditor_account_id"),
        table_name="service_provider_relation",
    )
    for column in (
        "creditor_account_id",
        "exemption_cert_valid_until",
        "exemption_cert_status",
        "customer_number",
    ):
        op.drop_column("service_provider_relation", column)
    op.execute("DROP TYPE IF EXISTS exemption_cert_status")
    for name in (
        "fk_property_owner_clearing_account_id_ledger_account",
        "fk_property_owner_tax_advisor_contact_id_contact",
        "fk_property_owner_power_of_attorney_document_id_document",
    ):
        op.drop_constraint(op.f(name), "property_owner", type_="foreignkey")
    for name in (
        "ix_property_owner_tax_advisor_contact_id",
        "ix_property_owner_power_of_attorney_document_id",
        "ix_property_owner_clearing_account_id",
    ):
        op.drop_index(op.f(name), table_name="property_owner")
    for column in (
        "tax_advisor_contact_id",
        "power_of_attorney_document_id",
        "clearing_account_id",
    ):
        op.drop_column("property_owner", column)
    op.drop_constraint(
        op.f("fk_property_bank_account_ledger_account_id_ledger_account"),
        "property_bank_account",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_property_bank_account_ledger_account_id"), table_name="property_bank_account"
    )
    op.drop_column("property_bank_account", "ledger_account_id")
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index(
        op.f("ix_property_portal_document_property_id"), table_name="property_portal_document"
    )
    op.drop_index(
        op.f("ix_property_portal_document_document_id"), table_name="property_portal_document"
    )
    op.drop_table("property_portal_document")
    op.drop_index(op.f("ix_sub_community_property_id"), table_name="sub_community")
    op.drop_table("sub_community")
    op.drop_index(
        op.f("ix_property_billing_period_property_id"), table_name="property_billing_period"
    )
    op.drop_table("property_billing_period")
    op.execute("DROP TYPE IF EXISTS billing_period_kind")
