"""Learning bookkeeper, steps S0 and S1 (ADR 0013, rule M12-04, plan M12).

* ``journal_entry.reversal_reason_code``: reason code of a reversal (B03, ``ReversalReason``),
  free text stays mandatory.
* ``ix_journal_entry_bank_transaction``: postings per bank transaction (history, reversal
  lookup of the consumer).
* ``tenant_settings.learning_bookkeeper_enabled``: tenant switch, default off (data protection
  review of the decision store is an open operator decision, OPEN_QUESTIONS M12-06).
* ``posting_decision``: proposal and decision log per bank transaction and round. RLS; append
  only in the sense of B03 through the trigger ``mhvp_posting_decision_guard``: a ``pending``
  row may be closed once (decision columns filled, snapshot columns immutable), closed rows
  are immutable, nothing is ever deleted. At most one pending row per transaction.
* ``banking_event_watermark``: position of the banking event consumer (pattern
  ``automation_watermark``). RLS.
* ``receipt_draft.account_proposal_decision`` (step S7): cost account proposals from the
  creditor's history and the reviewer's decision per line at confirmation (JSONB, nullable).

Revision ID: 0232
Revises: 0223
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0232"
down_revision: str | None = "0223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = (
    "pending",
    "accepted_unchanged",
    "modified",
    "rejected",
    "ignored",
    "auto_posted",
    "expired",
    "reversed",
)

GUARD_FUNCTION = """
CREATE FUNCTION mhvp_posting_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'posting decision % is never deleted', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF OLD.status <> 'pending' THEN
    RAISE EXCEPTION 'posting decision % is closed and immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF NEW.status = 'pending' THEN
    RAISE EXCEPTION 'posting decision % stays pending; take a new snapshot instead', OLD.id
      USING ERRCODE = 'P0001';
  END IF;
  IF NEW.tenant_id <> OLD.tenant_id OR NEW.bank_transaction_id <> OLD.bank_transaction_id
     OR NEW.legal_entity_id <> OLD.legal_entity_id OR NEW.round <> OLD.round
     OR NEW.engine_version <> OLD.engine_version OR NEW.rule_version <> OLD.rule_version
     OR NEW.features_hash <> OLD.features_hash OR NEW.features <> OLD.features
     OR NEW.proposals <> OLD.proposals OR NEW.case_kind <> OLD.case_kind
     OR NEW.computed_at <> OLD.computed_at OR NEW.created_at <> OLD.created_at
     OR NEW.sync_run_id IS DISTINCT FROM OLD.sync_run_id
     OR NEW.supersedes_id IS DISTINCT FROM OLD.supersedes_id THEN
    RAISE EXCEPTION 'posting decision % snapshot is immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$
"""

GUARD_TRIGGER = """
CREATE TRIGGER posting_decision_guard BEFORE UPDATE OR DELETE ON posting_decision
FOR EACH ROW EXECUTE FUNCTION mhvp_posting_decision_guard()
"""


def upgrade() -> None:
    op.add_column(
        "journal_entry", sa.Column("reversal_reason_code", sa.String(length=32), nullable=True)
    )
    op.create_index(
        "ix_journal_entry_bank_transaction",
        "journal_entry",
        ["tenant_id", "bank_transaction_id"],
        unique=False,
        postgresql_where=sa.text("bank_transaction_id IS NOT NULL"),
    )
    op.add_column(
        "tenant_settings",
        sa.Column(
            "learning_bookkeeper_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "posting_decision",
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
        sa.Column("bank_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("bulk", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.Column("features_hash", sa.String(length=64), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("proposals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("case_kind", sa.String(length=24), nullable=False),
        sa.Column("level", sa.String(length=4), nullable=False),
        sa.Column("best_source", sa.String(length=16), nullable=True),
        sa.Column("best_confidence", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("chosen_index", sa.Integer(), nullable=True),
        sa.Column("final", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ai_proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in STATUSES)),
            name=op.f("ck_posting_decision_posting_decision_status"),
        ),
        sa.CheckConstraint("round >= 1", name=op.f("ck_posting_decision_posting_decision_round")),
        sa.ForeignKeyConstraint(
            ["ai_proposal_id"],
            ["ai_proposal.id"],
            name=op.f("fk_posting_decision_ai_proposal_id_ai_proposal"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_transaction_id"],
            ["bank_transaction.id"],
            name=op.f("fk_posting_decision_bank_transaction_id_bank_transaction"),
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_posting_decision_journal_entry_id_journal_entry"),
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entity.id"],
            name=op.f("fk_posting_decision_legal_entity_id_legal_entity"),
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["posting_decision.id"],
            name=op.f("fk_posting_decision_supersedes_id_posting_decision"),
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["bank_sync_run.id"],
            name=op.f("fk_posting_decision_sync_run_id_bank_sync_run"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_posting_decision_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posting_decision")),
    )
    op.create_index(
        "uq_posting_decision_pending",
        "posting_decision",
        ["tenant_id", "bank_transaction_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_posting_decision_transaction",
        "posting_decision",
        ["tenant_id", "bank_transaction_id", "round"],
        unique=False,
    )
    op.create_index(
        "ix_posting_decision_journal_entry",
        "posting_decision",
        ["tenant_id", "journal_entry_id"],
        unique=False,
        postgresql_where=sa.text("journal_entry_id IS NOT NULL"),
    )
    op.create_index(
        "ix_posting_decision_entity_status",
        "posting_decision",
        ["tenant_id", "legal_entity_id", "status"],
        unique=False,
    )
    for statement in tenant_rls_statements("posting_decision"):
        op.execute(statement)
    op.execute(GUARD_FUNCTION)
    op.execute(GUARD_TRIGGER)

    op.create_table(
        "banking_event_watermark",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_banking_event_watermark_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_banking_event_watermark")),
        sa.UniqueConstraint("tenant_id", name="uq_banking_event_watermark_tenant"),
    )
    for statement in tenant_rls_statements("banking_event_watermark"):
        op.execute(statement)

    op.add_column(
        "receipt_draft",
        sa.Column(
            "account_proposal_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("receipt_draft", "account_proposal_decision")
    for statement in drop_tenant_rls_statements("banking_event_watermark"):
        op.execute(statement)
    op.drop_table("banking_event_watermark")
    op.execute("DROP TRIGGER IF EXISTS posting_decision_guard ON posting_decision")
    op.execute("DROP FUNCTION IF EXISTS mhvp_posting_decision_guard()")
    for statement in drop_tenant_rls_statements("posting_decision"):
        op.execute(statement)
    op.drop_index("ix_posting_decision_entity_status", table_name="posting_decision")
    op.drop_index("ix_posting_decision_journal_entry", table_name="posting_decision")
    op.drop_index("ix_posting_decision_transaction", table_name="posting_decision")
    op.drop_index("uq_posting_decision_pending", table_name="posting_decision")
    op.drop_table("posting_decision")
    op.drop_column("tenant_settings", "learning_bookkeeper_enabled")
    op.drop_index("ix_journal_entry_bank_transaction", table_name="journal_entry")
    op.drop_column("journal_entry", "reversal_reason_code")
