"""hoa_inspection_request and hoa_inspection_event: inspection requests outside the portal
(A61, M25-04, section 14 phase boundary) with a trail per status change, note, package and
retrieval. Tenant tables with RLS (ADR 0002).

Revision ID: 0117
Revises: 0116
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0117"
down_revision: str | None = "0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REQUEST = "hoa_inspection_request"
EVENT = "hoa_inspection_event"


def upgrade() -> None:
    op.create_table(
        REQUEST,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("applicant_contact_id", sa.Uuid(), nullable=False),
        sa.Column("requested_on", sa.Date(), nullable=False),
        sa.Column("scope_text", sa.Text(), nullable=True),
        sa.Column("scope_kinds", postgresql.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("released_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_kind", sa.String(length=16), nullable=True),
        sa.Column("package_document_id", sa.Uuid(), nullable=True),
        sa.Column("package_sha256", sa.String(length=64), nullable=True),
        sa.Column("package_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{REQUEST}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entity.id"],
            name=op.f(f"fk_{REQUEST}_legal_entity_id_legal_entity"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["property.id"], name=op.f(f"fk_{REQUEST}_property_id_property")
        ),
        sa.ForeignKeyConstraint(
            ["applicant_contact_id"],
            ["contact.id"],
            name=op.f(f"fk_{REQUEST}_applicant_contact_id_contact"),
        ),
        sa.ForeignKeyConstraint(
            ["package_document_id"],
            ["document.id"],
            name=op.f(f"fk_{REQUEST}_package_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'released', 'provided', 'retrieved', 'closed', 'rejected')",
            name=f"ck_{REQUEST}_status",
        ),
        sa.CheckConstraint(
            "delivery_kind IS NULL OR delivery_kind IN ('portal', 'data_medium', 'on_site')",
            name=f"ck_{REQUEST}_delivery_kind",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{REQUEST}")),
    )
    op.create_index(f"ix_{REQUEST}_entity", REQUEST, ["tenant_id", "legal_entity_id"])
    op.create_index(f"ix_{REQUEST}_property", REQUEST, ["tenant_id", "property_id"])
    op.create_table(
        EVENT,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{EVENT}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            [f"{REQUEST}.id"],
            name=op.f(f"fk_{EVENT}_request_id_{REQUEST}"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('status', 'note', 'package', 'retrieval')", name=f"ck_{EVENT}_kind"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{EVENT}")),
    )
    op.create_index(f"ix_{EVENT}_request", EVENT, ["tenant_id", "request_id"])
    for table in (REQUEST, EVENT):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in (EVENT, REQUEST):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index(f"ix_{EVENT}_request", table_name=EVENT)
    op.drop_table(EVENT)
    op.drop_index(f"ix_{REQUEST}_property", table_name=REQUEST)
    op.drop_index(f"ix_{REQUEST}_entity", table_name=REQUEST)
    op.drop_table(REQUEST)
