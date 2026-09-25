"""handover: Übergabeprotokolle im Bereich Makler (M30, docs/plans/M30-uebergabeprotokoll.md).

Revision ID: 0041
Revises: 0040

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "handover_protocol",
    "handover_participant",
    "handover_meter",
    "handover_room",
    "handover_defect",
    "handover_key",
    "handover_item",
    "handover_note",
    "handover_signature",
)


def upgrade() -> None:
    op.create_table(
        "handover_protocol",
        sa.Column("number", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_step", sa.String(length=20), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=True),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("listing_id", sa.UUID(), nullable=True),
        sa.Column("street", sa.String(length=200), nullable=True),
        sa.Column("house_number", sa.String(length=20), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("object_label", sa.String(length=200), nullable=True),
        sa.Column("building", sa.String(length=100), nullable=True),
        sa.Column("floor", sa.String(length=20), nullable=True),
        sa.Column("unit_number", sa.String(length=50), nullable=True),
        sa.Column("unit_label", sa.String(length=100), nullable=True),
        sa.Column("unit_position", sa.String(length=100), nullable=True),
        sa.Column("handover_date", sa.Date(), nullable=True),
        sa.Column("handover_start", sa.Time(), nullable=True),
        sa.Column("handover_end", sa.Time(), nullable=True),
        sa.Column(
            "hide_time_information", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("handover_location", sa.String(length=200), nullable=True),
        sa.Column("ticket_number", sa.String(length=50), nullable=True),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("management_number", sa.String(length=100), nullable=True),
        sa.Column("rental_contract_number", sa.String(length=100), nullable=True),
        sa.Column("internal_contact", sa.String(length=200), nullable=True),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column("general_note", sa.Text(), nullable=True),
        sa.Column("deposit_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("deposit_account_holder", sa.String(length=200), nullable=True),
        sa.Column("deposit_iban", sa.String(length=34), nullable=True),
        sa.Column("deposit_bic", sa.String(length=11), nullable=True),
        sa.Column("deposit_bank_name", sa.String(length=200), nullable=True),
        sa.Column("deposit_note", sa.Text(), nullable=True),
        sa.Column(
            "deposit_iban_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "deposit_separate_statement",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", sa.UUID(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_document_id", sa.UUID(), nullable=True),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name=op.f("fk_handover_protocol_contract_id_contract"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listing.id"],
            name=op.f("fk_handover_protocol_listing_id_listing"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_protocol_parent_id_handover_protocol"),
        ),
        sa.ForeignKeyConstraint(
            ["pdf_document_id"],
            ["document.id"],
            name=op.f("fk_handover_protocol_pdf_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_handover_protocol_property_id_property"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_protocol_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["unit.id"],
            name=op.f("fk_handover_protocol_unit_id_unit"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_protocol")),
        sa.UniqueConstraint("tenant_id", "number", "version", name="uq_handover_number_version"),
    )
    op.create_index(
        "ix_handover_protocol_tenant_status",
        "handover_protocol",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_table(
        "handover_item",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("item_type", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("condition", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_item_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_item_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_item")),
    )
    op.create_index(
        op.f("ix_handover_item_protocol_id"), "handover_item", ["protocol_id"], unique=False
    )
    op.create_table(
        "handover_key",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("key_type", sa.String(length=100), nullable=True),
        sa.Column("custom_name", sa.String(length=200), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("key_number", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_key_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_key_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_key")),
    )
    op.create_index(
        op.f("ix_handover_key_protocol_id"), "handover_key", ["protocol_id"], unique=False
    )
    op.create_table(
        "handover_meter",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("meter_id", sa.UUID(), nullable=True),
        sa.Column("meter_type", sa.String(length=63), nullable=True),
        sa.Column("custom_type", sa.String(length=100), nullable=True),
        sa.Column("number", sa.String(length=100), nullable=True),
        sa.Column("value", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("read_on", sa.Date(), nullable=True),
        sa.Column("read_at", sa.Time(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["meter_id"],
            ["meter.id"],
            name=op.f("fk_handover_meter_meter_id_meter"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_meter_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_meter_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_meter")),
    )
    op.create_index(
        op.f("ix_handover_meter_protocol_id"), "handover_meter", ["protocol_id"], unique=False
    )
    op.create_table(
        "handover_note",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("responsible_party", sa.String(length=200), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_note_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_note_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_note")),
    )
    op.create_index(
        op.f("ix_handover_note_protocol_id"), "handover_note", ["protocol_id"], unique=False
    )
    op.create_table(
        "handover_participant",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("salutation", sa.String(length=50), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("street", sa.String(length=200), nullable=True),
        sa.Column("house_number", sa.String(length=20), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contact.id"],
            name=op.f("fk_handover_participant_contact_id_contact"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_participant_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_participant_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_participant")),
    )
    op.create_index(
        op.f("ix_handover_participant_protocol_id"),
        "handover_participant",
        ["protocol_id"],
        unique=False,
    )
    op.create_table(
        "handover_room",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("room_type", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("condition", sa.String(length=20), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_room_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_room_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_room")),
    )
    op.create_index(
        op.f("ix_handover_room_protocol_id"), "handover_room", ["protocol_id"], unique=False
    )
    op.create_table(
        "handover_defect",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("room_id", sa.UUID(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("priority", sa.String(length=10), nullable=True),
        sa.Column("responsibility", sa.String(length=100), nullable=True),
        sa.Column("defect_status", sa.String(length=20), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_defect_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["handover_room.id"],
            name=op.f("fk_handover_defect_room_id_handover_room"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_defect_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_defect")),
    )
    op.create_index(
        op.f("ix_handover_defect_protocol_id"), "handover_defect", ["protocol_id"], unique=False
    )
    op.create_table(
        "handover_signature",
        sa.Column("protocol_id", sa.UUID(), nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=True),
        sa.Column("signer_name", sa.String(length=200), nullable=True),
        sa.Column("signer_role", sa.String(length=20), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signed_location", sa.String(length=200), nullable=True),
        sa.Column("comment", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_handover_signature_document_id_document"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["handover_participant.id"],
            name=op.f("fk_handover_signature_participant_id_handover_participant"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["handover_protocol.id"],
            name=op.f("fk_handover_signature_protocol_id_handover_protocol"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_handover_signature_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_handover_signature")),
    )
    op.create_index(
        op.f("ix_handover_signature_protocol_id"),
        "handover_signature",
        ["protocol_id"],
        unique=False,
    )
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index(op.f("ix_handover_signature_protocol_id"), table_name="handover_signature")
    op.drop_table("handover_signature")
    op.drop_index(op.f("ix_handover_defect_protocol_id"), table_name="handover_defect")
    op.drop_table("handover_defect")
    op.drop_index(op.f("ix_handover_room_protocol_id"), table_name="handover_room")
    op.drop_table("handover_room")
    op.drop_index(op.f("ix_handover_participant_protocol_id"), table_name="handover_participant")
    op.drop_table("handover_participant")
    op.drop_index(op.f("ix_handover_note_protocol_id"), table_name="handover_note")
    op.drop_table("handover_note")
    op.drop_index(op.f("ix_handover_meter_protocol_id"), table_name="handover_meter")
    op.drop_table("handover_meter")
    op.drop_index(op.f("ix_handover_key_protocol_id"), table_name="handover_key")
    op.drop_table("handover_key")
    op.drop_index(op.f("ix_handover_item_protocol_id"), table_name="handover_item")
    op.drop_table("handover_item")
    op.drop_index("ix_handover_protocol_tenant_status", table_name="handover_protocol")
    op.drop_table("handover_protocol")
