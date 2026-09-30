"""Bank sync hour per tenant and weekly L3 digest (M11-05, plan M12 S10, M12-02).

* ``bank_sync_setting``: local hour of the daily bank sync per tenant (default 6). RLS.
* ``auto_posting_digest``: weekly digest of level L3 per legal entity with confirmation and
  B09 reconciliation result. RLS.

Revision ID: 0258
Revises: 0257
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0258"
down_revision: str | None = "0257"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "bank_sync_setting",
        *_audit_columns(),
        sa.Column("sync_hour", sa.Integer(), server_default=sa.text("6"), nullable=False),
        sa.CheckConstraint(
            "sync_hour BETWEEN 0 AND 23", name=op.f("ck_bank_sync_setting_bank_sync_setting_hour")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_bank_sync_setting_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_sync_setting")),
        sa.UniqueConstraint("tenant_id", name="uq_bank_sync_setting_tenant"),
    )
    for statement in tenant_rls_statements("bank_sync_setting"):
        op.execute(statement)

    op.create_table(
        "auto_posting_digest",
        *_audit_columns(),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("auto_posted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sampled", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reviews_open", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("findings", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "reconciliation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_ok", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_auto_posting_digest_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entity.id"],
            name=op.f("fk_auto_posting_digest_legal_entity_id_legal_entity"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auto_posting_digest")),
        sa.UniqueConstraint(
            "tenant_id", "legal_entity_id", "week_start", name="uq_auto_posting_digest_week"
        ),
    )
    for statement in tenant_rls_statements("auto_posting_digest"):
        op.execute(statement)


def downgrade() -> None:
    for table in ("auto_posting_digest", "bank_sync_setting"):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
