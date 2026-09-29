"""Bookkeeping automation completion (ADR 0014 addendum 2, rules M12-05, M12-06, B05).

* ``journal_entry.auto_review_pending``: an automatic posting whose review item is still
  open; dunning, settlement proposal and direct debit runs exclude the affected debtor
  accounts. The guard trigger of posted entries ignores this flag (it is no financial content).
* ``auto_posting_review.return_transaction_id``: the returned payment (Rücklastschrift) that
  opened a review item of kind ``return``.
* ``posting_decision.anonymised_at`` and ``bank_rule_proposal.anonymised_at``: retention run
  of the learning store (operator decision M12-06, 24 months): payer fingerprints and purpose
  tokens are nulled, the decision outcome stays. The guard trigger of ``posting_decision``
  allows exactly this update once per row and keeps forbidding every delete.
* ``bank_clarification``: clarification status per unposted bank movement (B05), with
  responsible ticket, reason for ``no_document_required`` and document link when resolved. RLS.

Idempotent: every step checks the catalogue first, so a partial run can be repeated.

Revision ID: 0243
Revises: 0242
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0243"
down_revision: str | None = "0242"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOURNAL_ENTRY_GUARD_NEW = """
CREATE OR REPLACE FUNCTION mhvp_journal_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'posted' THEN
      RAISE EXCEPTION 'posted journal entry % is immutable', OLD.id USING ERRCODE = 'P0001';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'posted' THEN
    IF (to_jsonb(NEW) - 'reversed_by_id' - 'updated_at' - 'updated_by' - 'auto_review_pending')
       IS DISTINCT FROM
       (to_jsonb(OLD) - 'reversed_by_id' - 'updated_at' - 'updated_by' - 'auto_review_pending')
       OR (OLD.reversed_by_id IS NOT NULL
           AND NEW.reversed_by_id IS DISTINCT FROM OLD.reversed_by_id)
    THEN
      RAISE EXCEPTION 'posted journal entry % is immutable', OLD.id USING ERRCODE = 'P0001';
    END IF;
  END IF;
  RETURN NEW;
END $$
"""

JOURNAL_ENTRY_GUARD_OLD = """
CREATE OR REPLACE FUNCTION mhvp_journal_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'posted' THEN
      RAISE EXCEPTION 'posted journal entry % is immutable', OLD.id USING ERRCODE = 'P0001';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'posted' THEN
    IF (to_jsonb(NEW) - 'reversed_by_id' - 'updated_at' - 'updated_by')
       IS DISTINCT FROM (to_jsonb(OLD) - 'reversed_by_id' - 'updated_at' - 'updated_by')
       OR (OLD.reversed_by_id IS NOT NULL
           AND NEW.reversed_by_id IS DISTINCT FROM OLD.reversed_by_id)
    THEN
      RAISE EXCEPTION 'posted journal entry % is immutable', OLD.id USING ERRCODE = 'P0001';
    END IF;
  END IF;
  RETURN NEW;
END $$
"""

# Retention anonymisation (M12-06): a closed row may change exactly once, and only the
# columns ``features``, ``proposals`` and ``anonymised_at`` (plus the audit stamps). The
# decision outcome (status, final, diff, reason, journal entry, decided by and at) and every
# delete stay forbidden.
DECISION_GUARD_NEW = """
CREATE OR REPLACE FUNCTION mhvp_posting_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'posting decision % is never deleted', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF OLD.status <> 'pending' THEN
    IF OLD.anonymised_at IS NULL AND NEW.anonymised_at IS NOT NULL
       AND (to_jsonb(NEW) - 'features' - 'proposals' - 'anonymised_at'
            - 'updated_at' - 'updated_by')
           = (to_jsonb(OLD) - 'features' - 'proposals' - 'anonymised_at'
            - 'updated_at' - 'updated_by')
    THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'posting decision % is closed and immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF NEW.status = 'pending' THEN
    RAISE EXCEPTION 'posting decision % stays pending; take a new snapshot instead', OLD.id
      USING ERRCODE = 'P0001';
  END IF;
  IF NEW.anonymised_at IS NOT NULL THEN
    RAISE EXCEPTION 'posting decision % is anonymised only after the retention period', OLD.id
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

DECISION_GUARD_OLD = """
CREATE OR REPLACE FUNCTION mhvp_posting_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

CLARIFICATION_STATUSES = ("open", "in_clarification", "no_document_required", "resolved")


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _add_column(table: str, column: sa.Column[object]) -> None:
    if not _has_column(table, str(column.name)):
        op.add_column(table, column)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _stamp(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    _add_column(
        "journal_entry",
        sa.Column(
            "auto_review_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(JOURNAL_ENTRY_GUARD_NEW)
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_journal_entry_auto_review_pending ON journal_entry "
            "(tenant_id, ledger_id) WHERE auto_review_pending"
        )
    )

    _add_column("auto_posting_review", sa.Column("return_transaction_id", _uuid(), nullable=True))

    _add_column(
        "posting_decision", sa.Column("anonymised_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(DECISION_GUARD_NEW)
    _add_column(
        "bank_rule_proposal",
        sa.Column("anonymised_at", sa.DateTime(timezone=True), nullable=True),
    )

    if not _has_table("bank_clarification"):
        op.create_table(
            "bank_clarification",
            sa.Column("id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column("bank_transaction_id", _uuid(), nullable=False),
            sa.Column("legal_entity_id", _uuid(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
            sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("rule_id", _uuid(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("document_id", _uuid(), nullable=True),
            sa.Column("ticket_id", _uuid(), nullable=True),
            sa.Column("assignee_user_id", _uuid(), nullable=True),
            sa.Column("decided_by", _uuid(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ({})".format(", ".join(f"'{s}'" for s in CLARIFICATION_STATUSES)),
                name=op.f("ck_bank_clarification_status"),
            ),
            sa.ForeignKeyConstraint(
                ["bank_transaction_id"],
                ["bank_transaction.id"],
                name=op.f("fk_bank_clarification_bank_transaction_id_bank_transaction"),
            ),
            sa.ForeignKeyConstraint(
                ["legal_entity_id"],
                ["legal_entity.id"],
                name=op.f("fk_bank_clarification_legal_entity_id_legal_entity"),
            ),
            sa.ForeignKeyConstraint(
                ["document_id"],
                ["document.id"],
                name=op.f("fk_bank_clarification_document_id_document"),
            ),
            sa.ForeignKeyConstraint(
                ["ticket_id"],
                ["ticket.id"],
                name=op.f("fk_bank_clarification_ticket_id_ticket"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_bank_clarification_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_clarification")),
            sa.UniqueConstraint(
                "tenant_id", "bank_transaction_id", name="uq_bank_clarification_transaction"
            ),
        )
        op.create_index(
            "ix_bank_clarification_status",
            "bank_clarification",
            ["tenant_id", "legal_entity_id", "status"],
        )
        for statement in tenant_rls_statements("bank_clarification"):
            op.execute(statement)


def downgrade() -> None:
    if _has_table("bank_clarification"):
        for statement in drop_tenant_rls_statements("bank_clarification"):
            op.execute(statement)
        op.drop_index("ix_bank_clarification_status", table_name="bank_clarification")
        op.drop_table("bank_clarification")
    if _has_column("bank_rule_proposal", "anonymised_at"):
        op.drop_column("bank_rule_proposal", "anonymised_at")
    op.execute(DECISION_GUARD_OLD)
    if _has_column("posting_decision", "anonymised_at"):
        op.drop_column("posting_decision", "anonymised_at")
    if _has_column("auto_posting_review", "return_transaction_id"):
        op.drop_column("auto_posting_review", "return_transaction_id")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_journal_entry_auto_review_pending"))
    op.execute(JOURNAL_ENTRY_GUARD_OLD)
    if _has_column("journal_entry", "auto_review_pending"):
        op.drop_column("journal_entry", "auto_review_pending")
