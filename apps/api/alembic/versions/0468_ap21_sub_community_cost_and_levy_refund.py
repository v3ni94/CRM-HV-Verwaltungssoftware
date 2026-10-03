"""AP21 / GAM-109, GAM-110: sub community per WEG cost position, special levy refund proposals.

* ``hoa_cost_item.sub_community_id`` (sub_community, SET NULL): cost position of a sub
  community of a Mehrhausanlage.
* ``hoa_levy_cost_setting`` (one row per tenant, no row means defaults): switches
  ``sub_community_basis_lock`` (default off: hint only, open question AP21-01) and
  ``levy_refund_proposals`` (default off: no refund proposals, open question AP21-02).
* ``hoa_special_levy_refund``: refund of a special levy as a proposal with resolution and
  reason; never paid or posted here (payout via payment run stays behind G2 and G4).

Revision ID: 0468
Revises: 0467
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0468"
down_revision: str | None = "0467"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTING = "hoa_levy_cost_setting"
REFUND = "hoa_special_levy_refund"


def _base(table: str) -> list[sa.SchemaItem]:
    return [
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.add_column("hoa_cost_item", sa.Column("sub_community_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_hoa_cost_item_sub_community_id_sub_community"),
        "hoa_cost_item",
        "sub_community",
        ["sub_community_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        SETTING,
        *_base(SETTING),
        sa.Column(
            "sub_community_basis_lock", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("levy_refund_proposals", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.UniqueConstraint("tenant_id", name=op.f(f"uq_{SETTING}_tenant_id")),
    )
    op.create_table(
        REFUND,
        *_base(REFUND),
        sa.Column("levy_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), server_default="proposed", nullable=False),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("amount > 0", name=op.f(f"ck_{REFUND}_amount_positive")),
        sa.CheckConstraint("status IN ('proposed', 'withdrawn')", name=op.f(f"ck_{REFUND}_status")),
        sa.ForeignKeyConstraint(
            ["levy_id"],
            ["special_levy.id"],
            name=op.f(f"fk_{REFUND}_levy_id_special_levy"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"], ["unit.id"], name=op.f(f"fk_{REFUND}_unit_id_unit"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["resolution_id"],
            ["resolution.id"],
            name=op.f(f"fk_{REFUND}_resolution_id_resolution"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index(op.f(f"ix_{REFUND}_levy_id"), REFUND, ["levy_id"])
    op.create_index(op.f(f"ix_{REFUND}_tenant_id_levy_id"), REFUND, ["tenant_id", "levy_id"])
    for table in (SETTING, REFUND):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in (REFUND, SETTING):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index(op.f(f"ix_{REFUND}_tenant_id_levy_id"), table_name=REFUND)
    op.drop_index(op.f(f"ix_{REFUND}_levy_id"), table_name=REFUND)
    op.drop_table(REFUND)
    op.drop_table(SETTING)
    op.drop_constraint(
        op.f("fk_hoa_cost_item_sub_community_id_sub_community"), "hoa_cost_item", type_="foreignkey"
    )
    op.drop_column("hoa_cost_item", "sub_community_id")
