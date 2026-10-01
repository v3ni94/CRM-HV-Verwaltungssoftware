"""HOA audit and inspection extensions (M25-02, M25-03, M25-05, M25-07, M25-08): risk note and
item history, report confirmation, authorization and data cut-off of the engagement, expiry of
the inspection package.

Revision ID: 0257
Revises: 0256
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0257"
down_revision: str | None = "0256"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT = "audit_item_event"
INSPECTION_EVENT = "hoa_inspection_event"


def upgrade() -> None:
    op.add_column("audit_engagement", sa.Column("authorization_text", sa.Text(), nullable=True))
    op.add_column("audit_engagement", sa.Column("data_as_of", sa.Date(), nullable=True))
    op.add_column("audit_item", sa.Column("risk_note", sa.Text(), nullable=True))
    op.add_column(
        "audit_report", sa.Column("confirmed_by_name", sa.String(length=200), nullable=True)
    )
    op.add_column("audit_report", sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "audit_report", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("audit_report", sa.Column("confirmation_note", sa.Text(), nullable=True))
    op.add_column(
        "hoa_inspection_request",
        sa.Column("package_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(f"ck_{INSPECTION_EVENT}_kind", INSPECTION_EVENT, type_="check")
    op.create_check_constraint(
        f"ck_{INSPECTION_EVENT}_kind",
        INSPECTION_EVENT,
        "kind IN ('status', 'note', 'package', 'retrieval', 'revoked')",
    )
    op.create_table(
        EVENT,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("item_version", sa.Integer(), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{EVENT}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["audit_item.id"],
            name=op.f(f"fk_{EVENT}_item_id_audit_item"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{EVENT}")),
    )
    op.create_index(f"ix_{EVENT}_item", EVENT, ["tenant_id", "item_id"])
    for statement in tenant_rls_statements(EVENT):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(EVENT):
        op.execute(statement)
    op.drop_table(EVENT)
    # RLS is forced on the table, so the migrator sees no rows: lift the force for the delete
    # and restore it afterwards (as in 0139, 0151, 0203 and 0213).
    op.execute("ALTER TABLE hoa_inspection_event NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM hoa_inspection_event WHERE kind = 'revoked'")
    op.execute("ALTER TABLE hoa_inspection_event FORCE ROW LEVEL SECURITY")
    op.drop_constraint(f"ck_{INSPECTION_EVENT}_kind", INSPECTION_EVENT, type_="check")
    op.create_check_constraint(
        f"ck_{INSPECTION_EVENT}_kind",
        INSPECTION_EVENT,
        "kind IN ('status', 'note', 'package', 'retrieval')",
    )
    op.drop_column("hoa_inspection_request", "package_expires_at")
    for col in ("confirmation_note", "confirmed_at", "confirmed_by_user_id", "confirmed_by_name"):
        op.drop_column("audit_report", col)
    op.drop_column("audit_item", "risk_note")
    op.drop_column("audit_engagement", "data_as_of")
    op.drop_column("audit_engagement", "authorization_text")
