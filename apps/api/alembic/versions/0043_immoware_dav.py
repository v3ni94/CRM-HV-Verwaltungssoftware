"""immoware_dav: Lesezugriff auf Immoware24 per WebDAV, CardDAV und CalDAV als Spiegel (M32,
Uebernahme aus dem Immoware Hub, docs/immoware/07-sync-strategy.md).

Revision ID: 0043
Revises: 0042

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "immoware_connection",
    "immoware_dav_document",
    "immoware_dav_contact",
    "immoware_dav_event",
    "immoware_sync_run",
)
ENUMS = ("immoware_sync_kind", "immoware_sync_status")


def upgrade() -> None:
    op.create_table(
        "immoware_connection",
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("carddav_url", sa.String(length=500), nullable=True),
        sa.Column("caldav_url", sa.String(length=500), nullable=True),
        sa.Column("username", sa.String(length=200), nullable=True),
        sa.Column("password", sa.LargeBinary(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("verify_tls", sa.Boolean(), nullable=False),
        sa.Column("poll_minutes", sa.Integer(), nullable=False),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_ok", sa.Boolean(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_immoware_connection_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_immoware_connection")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_immoware_connection_tenant_id")),
    )

    def _mirror_columns() -> list[sa.Column]:
        return [
            sa.Column("source_system", sa.String(length=32), nullable=False),
            sa.Column("external_id", sa.String(length=1000), nullable=False),
            sa.Column("external_parent_id", sa.String(length=1000), nullable=True),
            sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("first_synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("checksum", sa.String(length=64), nullable=True),
            sa.Column("sync_version", sa.Integer(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
            ),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("updated_by", sa.UUID(), nullable=True),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
        ]

    op.create_table(
        "immoware_dav_document",
        sa.Column("href", sa.String(length=1000), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=200), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("etag", sa.String(length=300), nullable=True),
        sa.Column("last_modified", sa.String(length=100), nullable=True),
        sa.Column("is_collection", sa.Boolean(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("object_number_guess", sa.String(length=3), nullable=True),
        *_mirror_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_immoware_dav_document_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_immoware_dav_document")),
        sa.UniqueConstraint(
            "tenant_id", "external_id", name=op.f("uq_immoware_dav_document_tenant_id_external_id")
        ),
    )
    op.create_table(
        "immoware_dav_contact",
        sa.Column("href", sa.String(length=1000), nullable=False),
        sa.Column("etag", sa.String(length=300), nullable=True),
        sa.Column("uid", sa.String(length=300), nullable=True),
        sa.Column("vcard_raw", sa.Text(), nullable=True),
        sa.Column("fn", sa.String(length=300), nullable=True),
        sa.Column("org", sa.String(length=300), nullable=True),
        sa.Column("emails", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("phones", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("matched_contact_id", sa.UUID(), nullable=True),
        *_mirror_columns(),
        sa.ForeignKeyConstraint(
            ["matched_contact_id"],
            ["contact.id"],
            name=op.f("fk_immoware_dav_contact_matched_contact_id_contact"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_immoware_dav_contact_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_immoware_dav_contact")),
        sa.UniqueConstraint(
            "tenant_id", "external_id", name=op.f("uq_immoware_dav_contact_tenant_id_external_id")
        ),
    )
    op.create_table(
        "immoware_dav_event",
        sa.Column("href", sa.String(length=1000), nullable=False),
        sa.Column("etag", sa.String(length=300), nullable=True),
        sa.Column("uid", sa.String(length=300), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("dtstart", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dtend", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ical_raw", sa.Text(), nullable=True),
        *_mirror_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_immoware_dav_event_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_immoware_dav_event")),
        sa.UniqueConstraint(
            "tenant_id", "external_id", name=op.f("uq_immoware_dav_event_tenant_id_external_id")
        ),
    )
    op.create_table(
        "immoware_sync_run",
        sa.Column("kind", sa.Enum("webdav", "carddav", "caldav", name="immoware_sync_kind"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("running", "ok", "failed", name="immoware_sync_status"),
            nullable=False,
        ),
        sa.Column("seen", sa.Integer(), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("changed", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_immoware_sync_run_tenant_id_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_immoware_sync_run")),
    )

    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_table("immoware_sync_run")
    op.drop_table("immoware_dav_event")
    op.drop_table("immoware_dav_contact")
    op.drop_table("immoware_dav_document")
    op.drop_table("immoware_connection")
    for enum in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
