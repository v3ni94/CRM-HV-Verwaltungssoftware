"""objektakte_takeover: M35 Stufe 1 data model and migration scaffold (docs/plans/
M35-objektakte-uebernahme.md section 4, operator decision 25.09.2026). Adds `source_system`/
`source_id` provenance columns (unique per tenant where set) to `document`, `property`, `unit`
and `contact`, and the new objektakte tables: the Google Drive folder tree (`objektakte_drive_
node`), a minimal mirror of the review center (`objektakte_document_review_case`/`_decision`)
and a staging table for owner/tenant unit assignments the importer cannot yet place on an
existing CRM model (`objektakte_party_assignment`).

Revision ID: 0058
Revises: 0057

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TABLES = ("document", "property", "unit", "contact")

_DRIVE_NODE_KIND = postgresql.ENUM(
    "data_root",
    "object_root",
    "main_folder",
    "subfolder",
    "owner_file_folder",
    "owner_file_subfolder",
    "tenant_file_folder",
    "tenant_file_subfolder",
    "list_file",
    "year_folder",
    name="objektakte_drive_node_kind",
    create_type=False,
)
_DRIVE_LIST_TYPE = postgresql.ENUM(
    "owner_list", "tenant_list", name="objektakte_drive_list_type", create_type=False
)
_DRIVE_NODE_STATUS = postgresql.ENUM(
    "active", "missing", "trashed", name="objektakte_drive_node_status", create_type=False
)
_REVIEW_CASE_STATUS = postgresql.ENUM(
    "open",
    "in_progress",
    "resolved",
    "dismissed",
    name="objektakte_review_case_status",
    create_type=False,
)
_ASSIGNMENT_ROLE = postgresql.ENUM(
    "owner", "tenant", name="objektakte_party_assignment_role", create_type=False
)

_NEW_TENANT_TABLES = (
    "objektakte_drive_node",
    "objektakte_document_review_case",
    "objektakte_document_review_decision",
    "objektakte_party_assignment",
)


def upgrade() -> None:
    bind = op.get_bind()
    _DRIVE_NODE_KIND.create(bind, checkfirst=True)
    _DRIVE_LIST_TYPE.create(bind, checkfirst=True)
    _DRIVE_NODE_STATUS.create(bind, checkfirst=True)
    _REVIEW_CASE_STATUS.create(bind, checkfirst=True)
    _ASSIGNMENT_ROLE.create(bind, checkfirst=True)

    for table in _SOURCE_TABLES:
        op.add_column(table, sa.Column("source_system", sa.String(length=32)))
        op.add_column(table, sa.Column("source_id", sa.String(length=64)))
        op.create_index(
            f"uq_{table}_source",
            table,
            ["tenant_id", "source_system", "source_id"],
            unique=True,
            postgresql_where=sa.text("source_system IS NOT NULL AND source_id IS NOT NULL"),
        )

    op.create_table(
        "objektakte_drive_node",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("property_id", postgresql.UUID(as_uuid=True)),
        sa.Column("parent_node_id", postgresql.UUID(as_uuid=True)),
        sa.Column("node_kind", _DRIVE_NODE_KIND, nullable=False),
        sa.Column("list_type", _DRIVE_LIST_TYPE),
        sa.Column("year", sa.SmallInteger()),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("drive_file_id", sa.String(length=128), nullable=False),
        sa.Column("drive_parent_id", sa.String(length=128)),
        sa.Column("status", _DRIVE_NODE_STATUS, nullable=False),
        sa.Column("source_id", sa.String(length=64)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["parent_node_id"], ["objektakte_drive_node.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("tenant_id", "drive_file_id"),
    )
    op.create_index(
        "ix_objektakte_drive_node_property_id", "objektakte_drive_node", ["property_id"]
    )
    op.create_index(
        "ix_objektakte_drive_node_parent_node_id", "objektakte_drive_node", ["parent_node_id"]
    )

    op.create_table(
        "objektakte_document_review_case",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("candidates", postgresql.JSONB()),
        sa.Column("proposed_action", postgresql.JSONB()),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("status", _REVIEW_CASE_STATUS, nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True)),
        sa.Column("source_id", sa.String(length=64)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_objektakte_document_review_case_document_id",
        "objektakte_document_review_case",
        ["document_id"],
    )

    op.create_table(
        "objektakte_document_review_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("review_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("before_state", postgresql.JSONB()),
        sa.Column("after_state", postgresql.JSONB()),
        sa.Column("source_id", sa.String(length=64)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["review_case_id"], ["objektakte_document_review_case.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_objektakte_document_review_decision_review_case_id",
        "objektakte_document_review_decision",
        ["review_case_id"],
    )

    op.create_table(
        "objektakte_party_assignment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True)),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("role", _ASSIGNMENT_ROLE, nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("share", sa.Numeric(9, 6)),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_unit_id", sa.String(length=64)),
        sa.Column("source_contact_id", sa.String(length=64)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["unit.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contact.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "source_system", "source_id"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to",
            name="objektakte_assignment_period",
        ),
    )
    op.create_index(
        "ix_objektakte_party_assignment_unit_id", "objektakte_party_assignment", ["unit_id"]
    )
    op.create_index(
        "ix_objektakte_party_assignment_contact_id", "objektakte_party_assignment", ["contact_id"]
    )

    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)

    op.drop_table("objektakte_party_assignment")
    op.drop_table("objektakte_document_review_decision")
    op.drop_table("objektakte_document_review_case")
    op.drop_table("objektakte_drive_node")

    for table in _SOURCE_TABLES:
        op.drop_index(f"uq_{table}_source", table_name=table)
        op.drop_column(table, "source_id")
        op.drop_column(table, "source_system")

    bind = op.get_bind()
    _ASSIGNMENT_ROLE.drop(bind, checkfirst=True)
    _REVIEW_CASE_STATUS.drop(bind, checkfirst=True)
    _DRIVE_NODE_STATUS.drop(bind, checkfirst=True)
    _DRIVE_LIST_TYPE.drop(bind, checkfirst=True)
    _DRIVE_NODE_KIND.drop(bind, checkfirst=True)
