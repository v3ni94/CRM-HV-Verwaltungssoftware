"""Messdienstleister module, stage 1 (master prompt Messdienstleister, sections 3 to 11):
provider connections per tenant with encrypted secrets, external billing units, property and
unit assignments with validity and versions, sync jobs, clearing items, consumption values and
imported billing results (reviewable data only, no postings). Tenant tables with RLS
(ADR 0002) plus the per tenant module switch ``tenant_settings.metering_module_enabled``
(default off).

Revision ID: 0145
Revises: 0144
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0145"
down_revision: str | None = "0144"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "metering_connection",
    "metering_external_billing_unit",
    "metering_property_assignment",
    "metering_sync_job",
    "metering_unit_assignment",
    "metering_billing_result",
    "metering_clearing_item",
    "metering_consumption_value",
)


def upgrade() -> None:
    op.create_table(
        "metering_connection",
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("provider_code", sa.String(length=32), nullable=False),
        sa.Column("contracting_company", sa.String(length=200), nullable=True),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("customer_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("secrets", sa.LargeBinary(), nullable=True),
        sa.Column("secret_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_test_status", sa.String(length=32), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_detail", sa.Text(), nullable=True),
        sa.Column("test_stale", sa.Boolean(), nullable=False),
        sa.Column("scheduled_sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("write_sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_sync", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "environment IN ('test', 'production')", name=op.f("ck_metering_connection_environment")
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused')", name=op.f("ck_metering_connection_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_connection_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_connection")),
    )
    op.create_index(
        "ix_metering_connection_tenant_id_provider_code",
        "metering_connection",
        ["tenant_id", "provider_code"],
        unique=False,
    )
    op.create_table(
        "metering_external_billing_unit",
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("external_number", sa.String(length=64), nullable=False),
        sa.Column("external_name", sa.String(length=200), nullable=True),
        sa.Column("external_address", sa.String(length=400), nullable=True),
        sa.Column("expected_unit_count", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.UUID(), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("remote_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.CheckConstraint(
            "length(external_number) > 0",
            name=op.f("ck_metering_external_billing_unit_external_number_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["metering_connection.id"],
            name=op.f("fk_metering_external_billing_unit_connection_id_metering_connection"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_external_billing_unit_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_external_billing_unit")),
        sa.UniqueConstraint(
            "tenant_id",
            "connection_id",
            "external_number",
            name=op.f("uq_metering_external_billing_unit_tenant_id_connection_id_external_number"),
        ),
    )
    op.create_table(
        "metering_property_assignment",
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("external_billing_unit_id", sa.UUID(), nullable=False),
        sa.Column("service_scope", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by", sa.UUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_basis", sa.Text(), nullable=True),
        sa.Column("remote_confirmed", sa.Boolean(), nullable=False),
        sa.Column("remote_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("group_id", sa.UUID(), nullable=True),
        sa.Column("unit_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column("error_hint", sa.Text(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "origin IN ('manual', 'import', 'provider')",
            name=op.f("ck_metering_property_assignment_origin"),
        ),
        sa.CheckConstraint(
            "service_scope IN ('heating', 'hot_water', 'cold_water', 'smoke_detectors', 'other')",
            name=op.f("ck_metering_property_assignment_service_scope"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'proposed', 'confirmed', 'conflict', 'archived')",
            name=op.f("ck_metering_property_assignment_status"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_metering_property_assignment_valid_range"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["metering_connection.id"],
            name=op.f("fk_metering_property_assignment_connection_id_metering_connection"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["external_billing_unit_id"],
            ["metering_external_billing_unit.id"],
            name=op.f(
                "fk_metering_property_assignment_external_billing_unit_id_metering_external_billing_unit"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_metering_property_assignment_property_id_property"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_property_assignment_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_property_assignment")),
    )
    op.create_index(
        "ix_metering_property_assignment_tenant_id_property_id",
        "metering_property_assignment",
        ["tenant_id", "property_id"],
        unique=False,
    )
    op.create_table(
        "metering_sync_job",
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("property_assignment_id", sa.UUID(), nullable=True),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_kind", sa.String(length=32), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("assignment_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("parts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "data_kind IN ('documents', 'consumption', 'billing_result', 'billing_unit_data')",
            name=op.f("ck_metering_sync_job_data_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'waiting_provider', 'succeeded', 'partial', "
            "'failed', 'unclear')",
            name=op.f("ck_metering_sync_job_status"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["metering_connection.id"],
            name=op.f("fk_metering_sync_job_connection_id_metering_connection"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_assignment_id"],
            ["metering_property_assignment.id"],
            name=op.f("fk_metering_sync_job_property_assignment_id_metering_property_assignment"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_sync_job_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_sync_job")),
    )
    op.create_index(
        "ix_metering_sync_job_tenant_id_connection_id",
        "metering_sync_job",
        ["tenant_id", "connection_id"],
        unique=False,
    )
    op.create_table(
        "metering_unit_assignment",
        sa.Column("property_assignment_id", sa.UUID(), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("external_unit_number", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("billing_recipient_contact_id", sa.UUID(), nullable=True),
        sa.Column("consumption_info_recipient_contact_id", sa.UUID(), nullable=True),
        sa.Column("occupancy_status", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("external_partner_ref", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "occupancy_status IN ('occupied', 'vacant', 'owner_use', 'unclear')",
            name=op.f("ck_metering_unit_assignment_occupancy_status"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'proposed', 'confirmed', 'conflict', 'archived')",
            name=op.f("ck_metering_unit_assignment_status"),
        ),
        sa.CheckConstraint(
            "length(external_unit_number) > 0",
            name=op.f("ck_metering_unit_assignment_external_unit_number_not_empty"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_metering_unit_assignment_valid_range"),
        ),
        sa.ForeignKeyConstraint(
            ["billing_recipient_contact_id"],
            ["contact.id"],
            name=op.f("fk_metering_unit_assignment_billing_recipient_contact_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consumption_info_recipient_contact_id"],
            ["contact.id"],
            name=op.f("fk_metering_unit_assignment_consumption_info_recipient_contact_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_assignment_id"],
            ["metering_property_assignment.id"],
            name=op.f(
                "fk_metering_unit_assignment_property_assignment_id_metering_property_assignment"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_unit_assignment_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["unit.id"],
            name=op.f("fk_metering_unit_assignment_unit_id_unit"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_unit_assignment")),
    )
    op.create_index(
        "ix_metering_unit_assignment_tenant_id_unit_id",
        "metering_unit_assignment",
        ["tenant_id", "unit_id"],
        unique=False,
    )
    op.create_table(
        "metering_billing_result",
        sa.Column("property_assignment_id", sa.UUID(), nullable=False),
        sa.Column("unit_assignment_id", sa.UUID(), nullable=True),
        sa.Column("sync_job_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("external_document_ref", sa.String(length=128), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.CheckConstraint(
            "review_status IN ('imported', 'reviewed', 'rejected')",
            name=op.f("ck_metering_billing_result_review_status"),
        ),
        sa.CheckConstraint(
            "period_to >= period_from", name=op.f("ck_metering_billing_result_period_range")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_metering_billing_result_document_id_document"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_assignment_id"],
            ["metering_property_assignment.id"],
            name=op.f(
                "fk_metering_billing_result_property_assignment_id_metering_property_assignment"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sync_job_id"],
            ["metering_sync_job.id"],
            name=op.f("fk_metering_billing_result_sync_job_id_metering_sync_job"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_billing_result_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_assignment_id"],
            ["metering_unit_assignment.id"],
            name=op.f("fk_metering_billing_result_unit_assignment_id_metering_unit_assignment"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_billing_result")),
        sa.UniqueConstraint(
            "tenant_id",
            "property_assignment_id",
            "unit_assignment_id",
            "period_from",
            "period_to",
            "external_document_ref",
            "version",
            name=op.f(
                "uq_metering_billing_result_tenant_id_property_assignment_id_unit_assignment_id_period_from_period_to_external_document_ref_version"
            ),
        ),
    )
    op.create_table(
        "metering_clearing_item",
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("sync_job_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("external_identifier", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("property_assignment_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name=op.f("ck_metering_clearing_item_status"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["metering_connection.id"],
            name=op.f("fk_metering_clearing_item_connection_id_metering_connection"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_assignment_id"],
            ["metering_property_assignment.id"],
            name=op.f(
                "fk_metering_clearing_item_property_assignment_id_metering_property_assignment"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sync_job_id"],
            ["metering_sync_job.id"],
            name=op.f("fk_metering_clearing_item_sync_job_id_metering_sync_job"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_clearing_item_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_clearing_item")),
    )
    op.create_index(
        "ix_metering_clearing_item_tenant_id_status",
        "metering_clearing_item",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_table(
        "metering_consumption_value",
        sa.Column("property_assignment_id", sa.UUID(), nullable=False),
        sa.Column("unit_assignment_id", sa.UUID(), nullable=True),
        sa.Column("sync_job_id", sa.UUID(), nullable=True),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("unit_of_measure", sa.String(length=16), nullable=False),
        sa.Column("reading_type", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("value_kind", sa.String(length=16), nullable=False),
        sa.Column("external_ref", sa.String(length=128), nullable=True),
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
        sa.CheckConstraint(
            "(value_kind = 'missing' AND value IS NULL) "
            "OR (value_kind <> 'missing' AND value IS NOT NULL)",
            name=op.f("ck_metering_consumption_value_value_matches_kind"),
        ),
        sa.CheckConstraint(
            "reading_type IN ('period_consumption', 'meter_reading')",
            name=op.f("ck_metering_consumption_value_reading_type"),
        ),
        sa.CheckConstraint(
            "value_kind IN ('actual', 'estimated', 'missing', 'corrected')",
            name=op.f("ck_metering_consumption_value_value_kind"),
        ),
        sa.CheckConstraint(
            "period_to >= period_from", name=op.f("ck_metering_consumption_value_period_range")
        ),
        sa.ForeignKeyConstraint(
            ["property_assignment_id"],
            ["metering_property_assignment.id"],
            name=op.f(
                "fk_metering_consumption_value_property_assignment_id_metering_property_assignment"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sync_job_id"],
            ["metering_sync_job.id"],
            name=op.f("fk_metering_consumption_value_sync_job_id_metering_sync_job"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_consumption_value_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_assignment_id"],
            ["metering_unit_assignment.id"],
            name=op.f("fk_metering_consumption_value_unit_assignment_id_metering_unit_assignment"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_consumption_value")),
        sa.UniqueConstraint(
            "tenant_id",
            "property_assignment_id",
            "unit_assignment_id",
            "period_from",
            "period_to",
            "kind",
            "reading_type",
            "source",
            "version",
            name=op.f(
                "uq_metering_consumption_value_tenant_id_property_assignment_id_unit_assignment_id_period_from_period_to_kind_reading_type_source_version"
            ),
        ),
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)
    op.add_column(
        "tenant_settings",
        sa.Column("metering_module_enabled", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_column("tenant_settings", "metering_module_enabled")
    op.drop_table("metering_consumption_value")
    op.drop_index("ix_metering_clearing_item_tenant_id_status", table_name="metering_clearing_item")
    op.drop_table("metering_clearing_item")
    op.drop_table("metering_billing_result")
    op.drop_index(
        "ix_metering_unit_assignment_tenant_id_unit_id", table_name="metering_unit_assignment"
    )
    op.drop_table("metering_unit_assignment")
    op.drop_index("ix_metering_sync_job_tenant_id_connection_id", table_name="metering_sync_job")
    op.drop_table("metering_sync_job")
    op.drop_index(
        "ix_metering_property_assignment_tenant_id_property_id",
        table_name="metering_property_assignment",
    )
    op.drop_table("metering_property_assignment")
    op.drop_table("metering_external_billing_unit")
    op.drop_index(
        "ix_metering_connection_tenant_id_provider_code", table_name="metering_connection"
    )
    op.drop_table("metering_connection")
