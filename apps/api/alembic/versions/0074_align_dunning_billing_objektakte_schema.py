"""align_dunning_billing_objektakte_schema: fixes drift left by 0068-0073 so the DB matches
the models exactly (constraint/index names per the naming convention, missing tenant_id FKs
with ondelete=RESTRICT, extra ad hoc ``ix_<table>_tenant_id`` indexes not defined on the
models). No data or business behaviour changes.

Revision ID: 0074
Revises: 0073
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0074"
down_revision: str | None = "0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # dunning_fee_invoice_draft: drop the ad hoc tenant_id index (not on the model) and add
    # the tenant_id FK with ondelete=RESTRICT (TenantMixin), which 0068 omitted entirely.
    op.drop_index("ix_dunning_fee_invoice_draft_tenant_id", table_name="dunning_fee_invoice_draft")
    op.create_foreign_key(
        "fk_dunning_fee_invoice_draft_tenant_id_tenant",
        "dunning_fee_invoice_draft",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # dunning_mahnbescheid_prep: same tenant_id index/FK fix, plus the unique constraint name
    # to match the naming convention for the model's unnamed UniqueConstraint("tenant_id",
    # "case_id").
    op.drop_index("ix_dunning_mahnbescheid_prep_tenant_id", table_name="dunning_mahnbescheid_prep")
    op.create_foreign_key(
        "fk_dunning_mahnbescheid_prep_tenant_id_tenant",
        "dunning_mahnbescheid_prep",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "ALTER TABLE dunning_mahnbescheid_prep "
        "RENAME CONSTRAINT uq_dunning_mahnbescheid_prep_case "
        "TO uq_dunning_mahnbescheid_prep_tenant_id_case_id"
    )

    # tenant_billing_settings: drop the ad hoc tenant_id index, add ondelete=RESTRICT on the
    # (correctly named) tenant_id FK, which 0069 created without ondelete, and rename the
    # unique constraint.
    op.drop_index("ix_tenant_billing_settings_tenant_id", table_name="tenant_billing_settings")
    op.drop_constraint(
        "fk_tenant_billing_settings_tenant_id_tenant",
        "tenant_billing_settings",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_tenant_billing_settings_tenant_id_tenant",
        "tenant_billing_settings",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "ALTER TABLE tenant_billing_settings "
        "RENAME CONSTRAINT uq_tenant_billing_settings_tenant "
        "TO uq_tenant_billing_settings_tenant_id"
    )

    # invoice_number_counter: same tenant_id index/FK fix and unique constraint rename.
    op.drop_index("ix_invoice_number_counter_tenant_id", table_name="invoice_number_counter")
    op.drop_constraint(
        "fk_invoice_number_counter_tenant_id_tenant",
        "invoice_number_counter",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_invoice_number_counter_tenant_id_tenant",
        "invoice_number_counter",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "ALTER TABLE invoice_number_counter "
        "RENAME CONSTRAINT uq_invoice_number_counter_tenant_prefix_year "
        "TO uq_invoice_number_counter_tenant_id_prefix_year"
    )

    # objektakte_required_document: rename the document_category_id index to match the
    # naming convention (the unique constraint and both FKs already match it, truncated hash
    # and all, since 0073's create_table already applied it).
    op.execute(
        "ALTER INDEX ix_objektakte_required_document_category_id "
        "RENAME TO ix_objektakte_required_document_document_category_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX ix_objektakte_required_document_document_category_id "
        "RENAME TO ix_objektakte_required_document_category_id"
    )

    op.execute(
        "ALTER TABLE invoice_number_counter "
        "RENAME CONSTRAINT uq_invoice_number_counter_tenant_id_prefix_year "
        "TO uq_invoice_number_counter_tenant_prefix_year"
    )
    op.drop_constraint(
        "fk_invoice_number_counter_tenant_id_tenant",
        "invoice_number_counter",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_invoice_number_counter_tenant_id_tenant",
        "invoice_number_counter",
        "tenant",
        ["tenant_id"],
        ["id"],
    )
    op.create_index("ix_invoice_number_counter_tenant_id", "invoice_number_counter", ["tenant_id"])

    op.execute(
        "ALTER TABLE tenant_billing_settings "
        "RENAME CONSTRAINT uq_tenant_billing_settings_tenant_id "
        "TO uq_tenant_billing_settings_tenant"
    )
    op.drop_constraint(
        "fk_tenant_billing_settings_tenant_id_tenant",
        "tenant_billing_settings",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_tenant_billing_settings_tenant_id_tenant",
        "tenant_billing_settings",
        "tenant",
        ["tenant_id"],
        ["id"],
    )
    op.create_index(
        "ix_tenant_billing_settings_tenant_id", "tenant_billing_settings", ["tenant_id"]
    )

    op.execute(
        "ALTER TABLE dunning_mahnbescheid_prep "
        "RENAME CONSTRAINT uq_dunning_mahnbescheid_prep_tenant_id_case_id "
        "TO uq_dunning_mahnbescheid_prep_case"
    )
    op.drop_constraint(
        "fk_dunning_mahnbescheid_prep_tenant_id_tenant",
        "dunning_mahnbescheid_prep",
        type_="foreignkey",
    )
    op.create_index(
        "ix_dunning_mahnbescheid_prep_tenant_id", "dunning_mahnbescheid_prep", ["tenant_id"]
    )

    op.drop_constraint(
        "fk_dunning_fee_invoice_draft_tenant_id_tenant",
        "dunning_fee_invoice_draft",
        type_="foreignkey",
    )
    op.create_index(
        "ix_dunning_fee_invoice_draft_tenant_id", "dunning_fee_invoice_draft", ["tenant_id"]
    )
