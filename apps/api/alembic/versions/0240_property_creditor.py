"""property_creditor: creditors (contacts with role dienstleister) linked to a property for
the tab "Dienstleister/Handwerker" (rule M11-08). Link with trade, since, source (proposal,
manual, backfill) and the bank transaction that led to it. Master data only, RLS per tenant.

Revision ID: 0240
Revises: 0237
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0240"
down_revision: str | None = "0237"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "property_creditor"
ENUM_NAME = "property_creditor_source"
_SOURCE = postgresql.ENUM("proposal", "manual", "backfill", name=ENUM_NAME)


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        return
    _SOURCE.create(op.get_bind(), checkfirst=True)
    op.create_table(
        TABLE,
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
        sa.Column(
            "property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("property.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trade", sa.String(length=100)),
        sa.Column("since", sa.Date()),
        sa.Column(
            "source",
            postgresql.ENUM("proposal", "manual", "backfill", name=ENUM_NAME, create_type=False),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("source_transaction_id", postgresql.UUID(as_uuid=True)),
        sa.UniqueConstraint("tenant_id", "property_id", "contact_id", name="uq_property_creditor"),
    )
    op.create_index(f"ix_{TABLE}_property_id", TABLE, ["property_id"])
    op.create_index(f"ix_{TABLE}_contact_id", TABLE, ["contact_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index(f"ix_{TABLE}_contact_id", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_property_id", table_name=TABLE)
    op.drop_table(TABLE)
    _SOURCE.drop(op.get_bind(), checkfirst=True)
