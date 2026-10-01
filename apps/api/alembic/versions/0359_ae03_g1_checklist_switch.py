"""AE03 (M12-09, BK2-03): G1 checklist responsibility and evidence, four eyes switch requests.

``g1_acceptance`` gains ``responsible_user_id`` (person responsible for the item),
``evidence_document_id`` (linked DMS document) and ``evidence_ref`` (free reference such as a
docs path). New table ``auto_posting_switch_request``: switching the tenant automation on needs
an open gate G1, a request by one person and an approval by another (switching off stays
immediate). RLS. Opens no gate.

Revision ID: 0359
Revises: 0358
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0359"
down_revision: str | None = "0358"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "auto_posting_switch_request"


def upgrade() -> None:
    op.add_column(
        "g1_acceptance",
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "g1_acceptance",
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("g1_acceptance", sa.Column("evidence_ref", sa.String(length=500), nullable=True))
    op.create_foreign_key(
        "fk_g1_acceptance_responsible_user_id_app_user",
        "g1_acceptance",
        "app_user",
        ["responsible_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_g1_acceptance_evidence_document_id_document",
        "g1_acceptance",
        "document",
        ["evidence_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="requested"),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected')",
            name=op.f("ck_auto_posting_switch_request_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_auto_posting_switch_request_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auto_posting_switch_request")),
    )
    op.create_index(
        "ix_auto_posting_switch_request_status", TABLE, ["tenant_id", "status"], unique=False
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_auto_posting_switch_request_status", table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_constraint(
        "fk_g1_acceptance_evidence_document_id_document", "g1_acceptance", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_g1_acceptance_responsible_user_id_app_user", "g1_acceptance", type_="foreignkey"
    )
    op.drop_column("g1_acceptance", "evidence_ref")
    op.drop_column("g1_acceptance", "evidence_document_id")
    op.drop_column("g1_acceptance", "responsible_user_id")
