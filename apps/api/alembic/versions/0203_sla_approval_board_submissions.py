"""SLA approval per category (M19-01) and board submissions for tickets (M19-02).

``sla_rule``: ``category``, ``approval_status`` (draft/approved), ``approved_at``,
``approved_by``; the unique constraint per (tenant, priority) becomes a unique index per
(tenant, priority, coalesce(category, '')). Existing rules stay ``draft``: they no longer
govern new clocks until the management approves them (docs/rules/M19-01-sla-freigabe.md).

New tables ``ticket_board_policy``, ``ticket_board_submission``, ``ticket_board_vote`` with RLS
(ADR 0002). Idempotent: every column, index and table is checked before it is created.

Downgrade: rules that differ only by ``category`` cannot exist under the old unique
constraint (tenant, priority). The downgrade keeps one rule per (tenant, priority), the
uncategorised one when present, otherwise the oldest, detaches clocks from the removed
rules (``sla_clock.rule_id`` has no cascade) and deletes the surplus rules before the
constraint is recreated.

Revision ID: 0203
Revises: 0202
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0203"
down_revision: str | None = "0202"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("ticket_board_policy", "ticket_board_submission", "ticket_board_vote")
RULE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("category", sa.String(100), nullable=True),
    sa.Column("approval_status", sa.String(16), nullable=False, server_default="draft"),
    sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("approved_by", sa.UUID(), nullable=True),
)
RULE_UNIQUE_INDEX = "uq_sla_rule_tenant_priority_category"


def _audit_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    ]


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"],
        ["tenant.id"],
        name=op.f(f"fk_{table}_tenant_id_tenant"),
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("sla_rule"):
        existing = {c["name"] for c in inspector.get_columns("sla_rule")}
        for column in RULE_COLUMNS:
            if column.name not in existing:
                op.add_column("sla_rule", column)
        constraints = {c["name"] for c in inspector.get_unique_constraints("sla_rule")}
        if "uq_sla_rule_tenant_id_priority" in constraints:
            op.drop_constraint("uq_sla_rule_tenant_id_priority", "sla_rule", type_="unique")
        indexes = {i["name"] for i in inspector.get_indexes("sla_rule")}
        if RULE_UNIQUE_INDEX not in indexes:
            op.execute(
                f"CREATE UNIQUE INDEX {RULE_UNIQUE_INDEX} ON sla_rule "
                "(tenant_id, priority, coalesce(category, ''))"
            )
    if not inspector.has_table("ticket_board_policy"):
        op.create_table(
            "ticket_board_policy",
            *_audit_columns(),
            sa.Column("threshold_amount", sa.Numeric(14, 2), nullable=True),
            sa.Column(
                "categories",
                sa.ARRAY(sa.String(100)),
                nullable=False,
                server_default=sa.text("'{}'::varchar[]"),
            ),
            sa.Column("default_kind", sa.String(16), nullable=False, server_default="info"),
            sa.Column("default_deadline_days", sa.Integer(), nullable=False, server_default="14"),
            _tenant_fk("ticket_board_policy"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_board_policy")),
            sa.UniqueConstraint("tenant_id", name=op.f("uq_ticket_board_policy_tenant_id")),
        )
        for statement in tenant_rls_statements("ticket_board_policy"):
            op.execute(statement)
    if not inspector.has_table("ticket_board_submission"):
        op.create_table(
            "ticket_board_submission",
            *_audit_columns(),
            sa.Column("ticket_id", sa.UUID(), nullable=False),
            sa.Column("work_order_id", sa.UUID(), nullable=True),
            sa.Column("property_id", sa.UUID(), nullable=False),
            sa.Column("legal_entity_id", sa.UUID(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("amount", sa.Numeric(14, 2), nullable=True),
            sa.Column("due_on", sa.Date(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="open"),
            sa.Column(
                "member_contact_ids",
                sa.ARRAY(sa.UUID()),
                nullable=False,
                server_default=sa.text("'{}'::uuid[]"),
            ),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_by", sa.UUID(), nullable=True),
            sa.Column("closing_note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["ticket_id"],
                ["ticket.id"],
                name=op.f("fk_ticket_board_submission_ticket_id"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["work_order_id"],
                ["work_order.id"],
                name=op.f("fk_ticket_board_submission_work_order_id"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["property_id"],
                ["property.id"],
                name=op.f("fk_ticket_board_submission_property_id"),
            ),
            sa.ForeignKeyConstraint(
                ["legal_entity_id"],
                ["legal_entity.id"],
                name=op.f("fk_ticket_board_submission_legal_entity_id"),
            ),
            _tenant_fk("ticket_board_submission"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_board_submission")),
        )
        op.create_index(
            "ix_ticket_board_submission_ticket",
            "ticket_board_submission",
            ["tenant_id", "ticket_id"],
        )
        for statement in tenant_rls_statements("ticket_board_submission"):
            op.execute(statement)
    if not inspector.has_table("ticket_board_vote"):
        op.create_table(
            "ticket_board_vote",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("submission_id", sa.UUID(), nullable=False),
            sa.Column("contact_id", sa.UUID(), nullable=False),
            sa.Column("vote", sa.String(16), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("source", sa.String(16), nullable=False),
            sa.Column("recorded_by", sa.UUID(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["submission_id"],
                ["ticket_board_submission.id"],
                name=op.f("fk_ticket_board_vote_submission_id"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["contact_id"], ["contact.id"], name=op.f("fk_ticket_board_vote_contact_id")
            ),
            _tenant_fk("ticket_board_vote"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_board_vote")),
        )
        op.create_index(
            "ix_ticket_board_vote_submission", "ticket_board_vote", ["tenant_id", "submission_id"]
        )
        for statement in tenant_rls_statements("ticket_board_vote"):
            op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in reversed(TABLES):
        if inspector.has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
    if inspector.has_table("sla_rule"):
        indexes = {i["name"] for i in inspector.get_indexes("sla_rule")}
        if RULE_UNIQUE_INDEX in indexes:
            op.drop_index(RULE_UNIQUE_INDEX, table_name="sla_rule")
        existing = {c["name"] for c in inspector.get_columns("sla_rule")}
        if "category" in existing:
            # Both tables force row level security (ADR 0002); without a tenant context the
            # owner would see no rows, so the force is lifted for the fix and restored after.
            for table in ("sla_rule", "sla_clock", "sla_escalation_step"):
                op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(
                """
                CREATE TEMP TABLE sla_rule_downgrade_surplus ON COMMIT DROP AS
                SELECT id FROM (
                    SELECT id, row_number() OVER (
                        PARTITION BY tenant_id, priority
                        ORDER BY (category IS NOT NULL), created_at, id
                    ) AS rn
                    FROM sla_rule
                ) ranked WHERE rn > 1
                """
            )
            op.execute(
                "UPDATE sla_clock SET rule_id = NULL "
                "WHERE rule_id IN (SELECT id FROM sla_rule_downgrade_surplus)"
            )
            op.execute(
                "DELETE FROM sla_rule WHERE id IN (SELECT id FROM sla_rule_downgrade_surplus)"
            )
            for table in ("sla_rule", "sla_clock", "sla_escalation_step"):
                op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for column in reversed(RULE_COLUMNS):
            if column.name in existing:
                op.drop_column("sla_rule", column.name)
        constraints = {c["name"] for c in inspector.get_unique_constraints("sla_rule")}
        if "uq_sla_rule_tenant_id_priority" not in constraints:
            op.create_unique_constraint(
                "uq_sla_rule_tenant_id_priority", "sla_rule", ["tenant_id", "priority"]
            )
