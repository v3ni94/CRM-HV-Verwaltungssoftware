"""AE17 / M17-01: allocation agreements per tenancy and cost position, report switch.

* ``allocation_agreement``: clause reference, proof document and validity per contract and
  BetrKV catalogue type; no overlapping periods per contract and type.
* ``tenant_settings.allocation_basis_block``: the report of missing bases blocks the output of
  a rental statement (default on).

Revision ID: 0373
Revises: 0372
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ExcludeConstraint

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0373"
down_revision: str | None = "0372"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "allocation_agreement"


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "allocation_basis_block", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("operating_cost_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("clause_reference", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_allocation_agreement_period_order"),
        ),
        sa.CheckConstraint(
            "status IN ('agreed', 'excluded')", name=op.f("ck_allocation_agreement_status_values")
        ),
        sa.CheckConstraint(
            "status = 'excluded' OR (clause_reference IS NOT NULL AND clause_reference <> '')",
            name=op.f("ck_allocation_agreement_clause_required"),
        ),
        ExcludeConstraint(
            ("contract_id", "="),
            ("operating_cost_type", "="),
            (sa.text("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_allocation_agreement_period",
            using="gist",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_allocation_agreement_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name=op.f("fk_allocation_agreement_contract_id_contract"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_allocation_agreement_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allocation_agreement")),
    )
    op.create_index(op.f("ix_allocation_agreement_contract_id"), TABLE, ["contract_id"])
    op.create_index(op.f("ix_allocation_agreement_document_id"), TABLE, ["document_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
    op.drop_column("tenant_settings", "allocation_basis_block")
