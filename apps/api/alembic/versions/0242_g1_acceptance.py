"""G1 opening checklist (M12-09): table ``g1_acceptance``.

One row per tenant and checklist item (annex D case id such as ``D04`` or a manual item such
as ``vat_review``) with the operator's result (``open``, ``passed``, ``failed``), date, name
of the confirming person and a note. The table records the operator's acceptance for the
G1 opening page (Einstellungen, Buchhaltung, G1 Öffnung); it opens no gate. RLS.

Revision ID: 0242
Revises: 0241
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0242"
down_revision: str | None = "0241"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "g1_acceptance"


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if _has_table(TABLE):
        return
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
        sa.Column("item_key", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False, server_default="open"),
        sa.Column("confirmed_on", sa.Date(), nullable=True),
        sa.Column("confirmed_by_name", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'passed', 'failed')", name=op.f("ck_g1_acceptance_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_g1_acceptance_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_g1_acceptance")),
        sa.UniqueConstraint("tenant_id", "item_key", name=op.f("uq_g1_acceptance_tenant_id")),
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
