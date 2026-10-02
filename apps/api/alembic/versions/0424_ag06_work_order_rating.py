"""AG06 (GAF-35, AE30-02): ratings of completed work orders per party, display mode all.

* ``work_order_rating``: one rating per work order and party (staff, resident), RLS.
* ``portal_feature_setting.provider_rating_display`` additionally allows ``all``.

Revision ID: 0424
Revises: 0423
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0424"
down_revision: str | None = "0423"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "work_order_rating"
SETTING = "portal_feature_setting"
DROP_CHECK = sa.text(
    "DO $$ DECLARE c text; BEGIN "
    "SELECT conname INTO c FROM pg_constraint WHERE conrelid = 'portal_feature_setting'::regclass "
    "AND contype = 'c' AND pg_get_constraintdef(oid) LIKE '%provider_rating_display%'; "
    "IF c IS NOT NULL THEN EXECUTE format('ALTER TABLE portal_feature_setting "
    "DROP CONSTRAINT %I', c); END IF; END $$"
)


def upgrade() -> None:
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
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("party", sa.String(16), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("rated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("rated_by_contact_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("party IN ('staff', 'resident')", name=op.f(f"ck_{TABLE}_party")),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name=op.f(f"ck_{TABLE}_stars")),
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
            ["rated_by_contact_id"],
            ["contact.id"],
            name=op.f(f"fk_{TABLE}_rated_by_contact_id_contact"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint(
            "tenant_id", "work_order_id", "party", name=op.f("uq_work_order_rating_party")
        ),
    )
    op.create_index("ix_work_order_rating_order", TABLE, ["tenant_id", "work_order_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)
    op.execute(DROP_CHECK)
    op.create_check_constraint(
        "provider_rating_display",
        SETTING,
        "provider_rating_display IN ('off', 'staff', 'all')",
    )


def downgrade() -> None:
    # Rows with mode all fall back to staff (no financial data); ratings are kept as evidence
    # unless the table is dropped, which is the inverse of this migration only.
    bind = op.get_bind()
    bind.execute(sa.text(f"ALTER TABLE {SETTING} NO FORCE ROW LEVEL SECURITY"))
    try:
        bind.execute(
            sa.text(
                f"UPDATE {SETTING} SET provider_rating_display = 'staff' "  # noqa: S608
                "WHERE provider_rating_display = 'all'"
            )
        )
    finally:
        bind.execute(sa.text(f"ALTER TABLE {SETTING} FORCE ROW LEVEL SECURITY"))
    op.execute(DROP_CHECK)
    op.create_check_constraint(
        "provider_rating_display", SETTING, "provider_rating_display IN ('off', 'staff')"
    )
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_work_order_rating_order", table_name=TABLE)
    op.drop_table(TABLE)
