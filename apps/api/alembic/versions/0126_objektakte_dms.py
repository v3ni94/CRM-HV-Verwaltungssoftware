"""objektakte service connection (M29 Stufe 4): webhook receipts (idempotency of
``document.filed`` / ``object.taken_over``) and owner/tenant list import proposals. Tenant
tables with RLS (ADR 0002). Filed documents themselves use the existing ``document`` table (M6).

Revision ID: 0126
Revises: 0125
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0126"
down_revision: str | None = "0125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("objektakte_webhook_receipt", "objektakte_person_proposal")


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
    ]


def upgrade() -> None:
    op.create_table(
        "objektakte_webhook_receipt",
        *_base_columns(),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("object_number", sa.String(length=16), nullable=False),
        sa.Column("source_document_id", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("property_id", postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_objektakte_webhook_receipt_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_objektakte_webhook_receipt_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_objektakte_webhook_receipt_property_id_property"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "outcome IN ('created', 'linked', 'updated', 'unchanged', 'recorded', 'ignored')",
            name=op.f("ck_objektakte_webhook_receipt_outcome"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objektakte_webhook_receipt")),
        sa.UniqueConstraint(
            "tenant_id",
            "event",
            "object_number",
            "source_document_id",
            name="uq_objektakte_webhook_receipt_key",
        ),
    )
    op.create_table(
        "objektakte_person_proposal",
        *_base_columns(),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_number", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("decision_note", sa.Text()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_objektakte_person_proposal_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_objektakte_person_proposal_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('owners', 'tenants')", name=op.f("ck_objektakte_person_proposal_kind")
        ),
        sa.CheckConstraint(
            "status IN ('tested', 'approved', 'rejected')",
            name=op.f("ck_objektakte_person_proposal_status"),
        ),
        sa.CheckConstraint(
            "(status = 'tested') = (decided_at IS NULL)",
            name=op.f("ck_objektakte_person_proposal_decision"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objektakte_person_proposal")),
    )
    op.create_index(
        op.f("ix_objektakte_person_proposal_property_id"),
        "objektakte_person_proposal",
        ["property_id"],
    )
    for table in _TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index(
        op.f("ix_objektakte_person_proposal_property_id"), table_name="objektakte_person_proposal"
    )
    op.drop_table("objektakte_person_proposal")
    op.drop_table("objektakte_webhook_receipt")
