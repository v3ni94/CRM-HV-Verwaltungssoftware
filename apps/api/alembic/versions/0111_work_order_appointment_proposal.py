"""work_order_appointment_proposal: Terminvorschläge eines Dienstleisters zum Arbeitsauftrag
(14, M22, A58) with acceptance by the affected resident in the portal. Tenant table with RLS
(ADR 0002).

Revision ID: 0111
Revises: 0110
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0111"
down_revision: str | None = "0110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "work_order_appointment_proposal"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column("proposed_by_contact_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_contact_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_order.id"],
            name=op.f(f"fk_{TABLE}_work_order_id_work_order"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_by_contact_id"],
            ["contact.id"],
            name=op.f(f"fk_{TABLE}_proposed_by_contact_id_contact"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_contact_id"],
            ["contact.id"],
            name=op.f(f"fk_{TABLE}_decided_by_contact_id_contact"),
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'declined', 'superseded')",
            name=f"ck_{TABLE}_status",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
    )
    op.create_index(f"ix_{TABLE}_order", TABLE, ["tenant_id", "work_order_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index(f"ix_{TABLE}_order", table_name=TABLE)
    op.drop_table(TABLE)
