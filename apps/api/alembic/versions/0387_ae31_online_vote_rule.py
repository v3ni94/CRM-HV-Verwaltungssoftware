"""AE31 (AD06-01 to AD06-03): rule for a proxy vote against the owner's own vote.

* ``hoa_online_meeting_setting.proxy_conflict_mode``: tenant rule (flag, first_vote,
  proxy_priority, own_priority), default ``flag`` (mark for review, discard no vote).
* ``meeting_vote.proxy_id`` / ``meeting_vote.cast_source``: proxy and source (own, proxy) of a
  vote; null on votes recorded before this migration (treated as own).
* ``meeting_vote_conflict``: second vote of a unit cast by the other source, with both
  choices, the rule at the time and the decision of the meeting chair (RLS).

Revision ID: 0387
Revises: 0386
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0387"
down_revision: str | None = "0386"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "meeting_vote_conflict"


def upgrade() -> None:
    op.add_column(
        "hoa_online_meeting_setting",
        sa.Column("proxy_conflict_mode", sa.String(16), server_default="flag", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_hoa_online_meeting_setting_proxy_conflict_mode"),
        "hoa_online_meeting_setting",
        "proxy_conflict_mode IN ('flag', 'first_vote', 'proxy_priority', 'own_priority')",
    )
    op.add_column("meeting_vote", sa.Column("proxy_id", sa.Uuid(), nullable=True))
    op.add_column("meeting_vote", sa.Column("cast_source", sa.String(8), nullable=True))
    op.create_foreign_key(
        op.f("fk_meeting_vote_proxy_id_meeting_proxy"),
        "meeting_vote",
        "meeting_proxy",
        ["proxy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_meeting_vote_cast_source"),
        "meeting_vote",
        "cast_source IS NULL OR cast_source IN ('own', 'proxy')",
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
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("agenda_item_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("vote_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("first_source", sa.String(8), nullable=False),
        sa.Column("first_choice", sa.String(8), nullable=False),
        sa.Column("second_source", sa.String(8), nullable=False),
        sa.Column("second_choice", sa.String(8), nullable=False),
        sa.Column("second_proxy_id", sa.Uuid(), nullable=True),
        sa.Column("second_channel", sa.String(16), nullable=False),
        sa.Column("attempted_by", sa.Uuid(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("resolution", sa.String(16), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("status IN ('open', 'resolved')", name=op.f(f"ck_{TABLE}_status")),
        sa.CheckConstraint(
            "first_source IN ('own', 'proxy')", name=op.f(f"ck_{TABLE}_first_source")
        ),
        sa.CheckConstraint(
            "second_source IN ('own', 'proxy')", name=op.f(f"ck_{TABLE}_second_source")
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN ('keep_first', 'apply_second', 'rule_second')",
            name=op.f(f"ck_{TABLE}_resolution"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["owners_meeting.id"],
            name=op.f(f"fk_{TABLE}_meeting_id_owners_meeting"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agenda_item_id"],
            ["meeting_agenda_item.id"],
            name=op.f(f"fk_{TABLE}_agenda_item_id_meeting_agenda_item"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name=op.f(f"fk_{TABLE}_contract_id_contract")
        ),
        sa.ForeignKeyConstraint(
            ["vote_id"],
            ["meeting_vote.id"],
            name=op.f(f"fk_{TABLE}_vote_id_meeting_vote"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["second_proxy_id"],
            ["meeting_proxy.id"],
            name=op.f(f"fk_{TABLE}_second_proxy_id_meeting_proxy"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
    )
    op.create_index(f"ix_{TABLE}_item", TABLE, ["tenant_id", "agenda_item_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
    op.drop_constraint(op.f("ck_meeting_vote_cast_source"), "meeting_vote", type_="check")
    op.drop_constraint(
        op.f("fk_meeting_vote_proxy_id_meeting_proxy"), "meeting_vote", type_="foreignkey"
    )
    op.drop_column("meeting_vote", "cast_source")
    op.drop_column("meeting_vote", "proxy_id")
    op.drop_constraint(
        op.f("ck_hoa_online_meeting_setting_proxy_conflict_mode"),
        "hoa_online_meeting_setting",
        type_="check",
    )
    op.drop_column("hoa_online_meeting_setting", "proxy_conflict_mode")
