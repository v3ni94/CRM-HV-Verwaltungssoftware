"""Lern-Workflow (rule M9-11, operator 27.09.2026): table ``automation_rule_proposal`` for
rule proposals from repeated manual decisions, the tenant threshold
``tenant_settings.rule_proposal_threshold`` (default 5) and an index on ``domain_event`` for the
evidence lookup by event type. A proposal never acts by itself; an accepted proposal creates an
ordinary ``automation_rule``. Idempotent, RLS like every tenant table (ADR 0002).

Revision ID: 0218
Revises: 0217
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0218"
down_revision: str | None = "0217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "automation_rule_proposal"
EVENT_INDEX = "ix_domain_event_tenant_id_type_occurred_at"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    settings_columns = {c["name"] for c in inspector.get_columns("tenant_settings")}
    if "rule_proposal_threshold" not in settings_columns:
        op.add_column(
            "tenant_settings",
            sa.Column(
                "rule_proposal_threshold",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("5"),
            ),
        )
    event_indexes = {i["name"] for i in inspector.get_indexes("domain_event")}
    if EVENT_INDEX not in event_indexes:
        op.create_index(
            EVENT_INDEX, "domain_event", ["tenant_id", "type", "occurred_at"], unique=False
        )
    if inspector.has_table(TABLE):
        return
    op.create_table(
        TABLE,
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
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("field", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("sender_key", sa.String(320), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("value_label", sa.String(300), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'proposed'")),
        sa.Column(
            "evidence",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("rejected_evidence_count", sa.Integer(), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("rule_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["automation_rule.id"],
            name=op.f(f"fk_{TABLE}_rule_id_automation_rule"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint(
            "tenant_id",
            "entity_type",
            "field",
            "scope",
            "sender_key",
            "value",
            name="uq_automation_rule_proposal_pattern",
        ),
    )
    op.create_index(
        "ix_automation_rule_proposal_tenant_status", TABLE, ["tenant_id", "status"], unique=False
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
    if EVENT_INDEX in {i["name"] for i in inspector.get_indexes("domain_event")}:
        op.drop_index(EVENT_INDEX, table_name="domain_event")
    if "rule_proposal_threshold" in {c["name"] for c in inspector.get_columns("tenant_settings")}:
        op.drop_column("tenant_settings", "rule_proposal_threshold")
