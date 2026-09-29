"""Learning bookkeeper, steps S4 to S6 (ADR 0014 addendum, rules M12-05 and M12-06).

* ``tenant_settings``: ``bookkeeping_automation`` (level per case class, default all L0),
  ``bank_rule_proposal_threshold`` (5), ``bank_rule_recurring_threshold`` (3),
  ``auto_posting_outgoing_enabled`` (false).
* ``bookkeeping_level_request``: raising a class level, requested by one person and decided
  by another (pattern ``release_gate_request``). RLS.
* ``bank_rule_proposal``: learned rule proposals from repeated identical decisions with
  evidence and derived match; at most one open proposal per pattern key. RLS.
* ``bank_rule``: ``learned_from_proposal_id``, ``contradiction_count``, ``superseded_by_id``.
* ``auto_posting_review``: review queue of automatic postings with due date. RLS.
* ``posting_decision``: ``verifier_fingerprint`` and ``review_due_on`` (auto_posted rows).

Idempotent: every step checks the catalogue first, so a partial run can be repeated.

Revision ID: 0241
Revises: 0240
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0241"
down_revision: str | None = "0240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "tenant_settings",
        sa.Column(
            "bookkeeping_automation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    _add_column(
        "tenant_settings",
        sa.Column(
            "bank_rule_proposal_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )
    _add_column(
        "tenant_settings",
        sa.Column(
            "bank_rule_recurring_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
    )
    _add_column(
        "tenant_settings",
        sa.Column(
            "auto_posting_outgoing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    if not _has_table("bookkeeping_level_request"):
        op.create_table(
            "bookkeeping_level_request",
            sa.Column("id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column("case_kind", sa.String(length=24), nullable=False),
            sa.Column("level_from", sa.String(length=4), nullable=False),
            sa.Column("level_to", sa.String(length=4), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column(
                "evidence",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="requested"),
            sa.Column("requested_by", _uuid(), nullable=False),
            sa.Column("decided_by", _uuid(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_comment", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "status IN ('requested', 'approved', 'rejected')",
                name=op.f("ck_bookkeeping_level_request_status"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_bookkeeping_level_request_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_bookkeeping_level_request")),
        )
        op.create_index(
            "ix_bookkeeping_level_request_class",
            "bookkeeping_level_request",
            ["tenant_id", "case_kind", "status"],
        )
        for statement in tenant_rls_statements("bookkeeping_level_request"):
            op.execute(statement)

    if not _has_table("bank_rule_proposal"):
        op.create_table(
            "bank_rule_proposal",
            sa.Column("id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column("legal_entity_id", _uuid(), nullable=False),
            sa.Column("pattern_key", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
            sa.Column("direction", sa.String(length=6), nullable=False),
            sa.Column("case_kind", sa.String(length=24), nullable=False),
            sa.Column("counterpart_iban_fingerprint", sa.String(length=64), nullable=True),
            sa.Column("creditor_id", sa.String(length=64), nullable=True),
            sa.Column("account_number", sa.String(length=6), nullable=False),
            sa.Column("account_id", _uuid(), nullable=True),
            sa.Column("action_kind", sa.String(length=16), nullable=False),
            sa.Column("amount_min", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("amount_max", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column(
                "purpose_tokens",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("recurring", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("threshold", sa.Integer(), nullable=False),
            sa.Column(
                "evidence",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("evidence_count", sa.Numeric(precision=6, scale=1), nullable=False),
            sa.Column("rejected_evidence_count", sa.Numeric(precision=6, scale=1), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("rule_id", _uuid(), nullable=True),
            sa.Column("decided_by", _uuid(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('proposed', 'withdrawn', 'accepted', 'rejected', 'superseded')",
                name=op.f("ck_bank_rule_proposal_status"),
            ),
            sa.CheckConstraint(
                "direction IN ('credit', 'debit')", name=op.f("ck_bank_rule_proposal_direction")
            ),
            sa.ForeignKeyConstraint(
                ["legal_entity_id"],
                ["legal_entity.id"],
                name=op.f("fk_bank_rule_proposal_legal_entity_id_legal_entity"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_bank_rule_proposal_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_rule_proposal")),
        )
        op.create_index(
            "uq_bank_rule_proposal_open",
            "bank_rule_proposal",
            ["tenant_id", "pattern_key"],
            unique=True,
            postgresql_where=sa.text("status = 'proposed'"),
        )
        op.create_index(
            "ix_bank_rule_proposal_key", "bank_rule_proposal", ["tenant_id", "pattern_key"]
        )
        for statement in tenant_rls_statements("bank_rule_proposal"):
            op.execute(statement)

    _add_column("bank_rule", sa.Column("learned_from_proposal_id", _uuid(), nullable=True))
    if not any(
        fk["name"] == "fk_bank_rule_learned_from_proposal_id_bank_rule_proposal"
        for fk in sa.inspect(op.get_bind()).get_foreign_keys("bank_rule")
    ):
        op.create_foreign_key(
            "fk_bank_rule_learned_from_proposal_id_bank_rule_proposal",
            "bank_rule",
            "bank_rule_proposal",
            ["learned_from_proposal_id"],
            ["id"],
        )
    _add_column(
        "bank_rule",
        sa.Column("contradiction_count", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_column("bank_rule", sa.Column("superseded_by_id", _uuid(), nullable=True))

    _add_column(
        "posting_decision", sa.Column("verifier_fingerprint", sa.String(length=64), nullable=True)
    )
    _add_column("posting_decision", sa.Column("review_due_on", sa.Date(), nullable=True))

    if not _has_table("auto_posting_review"):
        op.create_table(
            "auto_posting_review",
            sa.Column("id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column("posting_decision_id", _uuid(), nullable=False),
            sa.Column("bank_transaction_id", _uuid(), nullable=False),
            sa.Column("legal_entity_id", _uuid(), nullable=False),
            sa.Column("journal_entry_id", _uuid(), nullable=True),
            sa.Column("rule_id", _uuid(), nullable=True),
            sa.Column("case_kind", sa.String(length=24), nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False, server_default="daily"),
            sa.Column("due_on", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=12), nullable=False, server_default="open"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("reviewed_by", _uuid(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('open', 'ok', 'corrected', 'cancelled')",
                name=op.f("ck_auto_posting_review_status"),
            ),
            sa.CheckConstraint(
                "kind IN ('daily', 'sample', 'return')", name=op.f("ck_auto_posting_review_kind")
            ),
            sa.ForeignKeyConstraint(
                ["posting_decision_id"],
                ["posting_decision.id"],
                name=op.f("fk_auto_posting_review_posting_decision_id_posting_decision"),
            ),
            sa.ForeignKeyConstraint(
                ["bank_transaction_id"],
                ["bank_transaction.id"],
                name=op.f("fk_auto_posting_review_bank_transaction_id_bank_transaction"),
            ),
            sa.ForeignKeyConstraint(
                ["legal_entity_id"],
                ["legal_entity.id"],
                name=op.f("fk_auto_posting_review_legal_entity_id_legal_entity"),
            ),
            sa.ForeignKeyConstraint(
                ["journal_entry_id"],
                ["journal_entry.id"],
                name=op.f("fk_auto_posting_review_journal_entry_id_journal_entry"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_auto_posting_review_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_auto_posting_review")),
        )
        op.create_index(
            "ix_auto_posting_review_open", "auto_posting_review", ["tenant_id", "status", "due_on"]
        )
        op.create_index(
            "ix_auto_posting_review_decision",
            "auto_posting_review",
            ["tenant_id", "posting_decision_id"],
        )
        for statement in tenant_rls_statements("auto_posting_review"):
            op.execute(statement)


def downgrade() -> None:
    if _has_table("auto_posting_review"):
        for statement in drop_tenant_rls_statements("auto_posting_review"):
            op.execute(statement)
        op.drop_index("ix_auto_posting_review_decision", table_name="auto_posting_review")
        op.drop_index("ix_auto_posting_review_open", table_name="auto_posting_review")
        op.drop_table("auto_posting_review")
    for column in ("review_due_on", "verifier_fingerprint"):
        if _has_column("posting_decision", column):
            op.drop_column("posting_decision", column)
    if _has_column("bank_rule", "learned_from_proposal_id"):
        op.drop_constraint(
            "fk_bank_rule_learned_from_proposal_id_bank_rule_proposal",
            "bank_rule",
            type_="foreignkey",
        )
    for column in ("superseded_by_id", "contradiction_count", "learned_from_proposal_id"):
        if _has_column("bank_rule", column):
            op.drop_column("bank_rule", column)
    if _has_table("bank_rule_proposal"):
        for statement in drop_tenant_rls_statements("bank_rule_proposal"):
            op.execute(statement)
        op.drop_index("ix_bank_rule_proposal_key", table_name="bank_rule_proposal")
        op.drop_index("uq_bank_rule_proposal_open", table_name="bank_rule_proposal")
        op.drop_table("bank_rule_proposal")
    if _has_table("bookkeeping_level_request"):
        for statement in drop_tenant_rls_statements("bookkeeping_level_request"):
            op.execute(statement)
        op.drop_index("ix_bookkeeping_level_request_class", table_name="bookkeeping_level_request")
        op.drop_table("bookkeeping_level_request")
    for column in (
        "auto_posting_outgoing_enabled",
        "bank_rule_recurring_threshold",
        "bank_rule_proposal_threshold",
        "bookkeeping_automation",
    ):
        if _has_column("tenant_settings", column):
            op.drop_column("tenant_settings", column)
