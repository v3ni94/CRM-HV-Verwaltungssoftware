"""Migration journal and opening balances of the switch from Immoware24 (6.9.10, D11, M8-03).

* ``migrated_journal_entry`` and ``migrated_journal_line``: rows of the Immoware24 journal
  export per ledger with original identifiers, year completeness flag and reconciliation
  marker; never part of the live journal. RLS.
* ``migration_opening_balance`` and ``migration_opening_balance_line``: balances as of the
  cut off date per ledger (draft, released by a second person, posted as one journal entry
  with source ``migration``). RLS.
* ``migration_reconciliation_report``: zero difference check per property with the stored
  PDF document. RLS.
* ``migration_switch_request``: switch of the leading system, decided by a second person,
  only with G1 open. RLS.

Idempotent: every table is created only when missing, so a partial run can be repeated.

Revision ID: 0244
Revises: 0243
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0244"
down_revision: str | None = "0243"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "migration_switch_request",
    "migration_reconciliation_report",
    "migration_opening_balance_line",
    "migration_opening_balance",
    "migrated_journal_line",
    "migrated_journal_entry",
)


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _money(name: str, *, default: str | None = "0") -> sa.Column[object]:
    return sa.Column(
        name,
        sa.Numeric(14, 2),
        nullable=False,
        server_default=sa.text(default) if default is not None else None,
    )


def _jsonb(name: str, default: str) -> sa.Column[object]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text(f"'{default}'::jsonb"),
    )


def _stamp(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenant.id"], name=op.f(f"fk_{table}_tenant_id_tenant"), ondelete="RESTRICT"
    )


def _rls(table: str) -> None:
    for statement in tenant_rls_statements(table):
        op.execute(statement)


def upgrade() -> None:
    if not _has_table("migrated_journal_entry"):
        op.create_table(
            "migrated_journal_entry",
            sa.Column("id", _uuid(), nullable=False),
            sa.Column("tenant_id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("ledger_id", _uuid(), nullable=False),
            sa.Column(
                "source", sa.String(40), nullable=False, server_default=sa.text("'immoware24'")
            ),
            sa.Column("source_entry_id", sa.String(100), nullable=False),
            sa.Column("source_file_id", _uuid(), nullable=True),
            _jsonb("row_numbers", "[]"),
            sa.Column("booking_date", sa.Date(), nullable=False),
            sa.Column("fiscal_year", sa.Integer(), nullable=False),
            sa.Column("text", sa.String(500), nullable=False, server_default=sa.text("''")),
            sa.Column("reference", sa.String(100), nullable=True),
            sa.Column("document_ref", sa.String(200), nullable=True),
            sa.Column(
                "year_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column("reconciled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("reconciled_report_id", _uuid(), nullable=True),
            _money("debit_total"),
            _money("credit_total"),
            _tenant_fk("migrated_journal_entry"),
            sa.ForeignKeyConstraint(
                ["ledger_id"],
                ["ledger.id"],
                name=op.f("fk_migrated_journal_entry_ledger_id_ledger"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_file_id"],
                ["import_source_file.id"],
                name=op.f("fk_migrated_journal_entry_source_file_id_import_source_file"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_migrated_journal_entry")),
            sa.UniqueConstraint(
                "tenant_id",
                "ledger_id",
                "source",
                "source_entry_id",
                name=op.f("uq_migrated_journal_entry_tenant_id"),
            ),
        )
        op.create_index(
            "ix_migrated_journal_entry_ledger_date",
            "migrated_journal_entry",
            ["tenant_id", "ledger_id", "booking_date"],
        )
        _rls("migrated_journal_entry")

    if not _has_table("migrated_journal_line"):
        op.create_table(
            "migrated_journal_line",
            sa.Column("id", _uuid(), nullable=False),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column("entry_id", _uuid(), nullable=False),
            sa.Column("line_no", sa.Integer(), nullable=False),
            sa.Column("account_number", sa.String(20), nullable=False),
            sa.Column("account_id", _uuid(), nullable=True),
            _money("debit"),
            _money("credit"),
            sa.Column("text", sa.String(500), nullable=True),
            _jsonb("raw", "{}"),
            sa.CheckConstraint(
                "debit >= 0 AND credit >= 0", name=op.f("ck_migrated_journal_line_non_negative")
            ),
            _tenant_fk("migrated_journal_line"),
            sa.ForeignKeyConstraint(
                ["entry_id"],
                ["migrated_journal_entry.id"],
                name=op.f("fk_migrated_journal_line_entry_id_migrated_journal_entry"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["account_id"],
                ["ledger_account.id"],
                name=op.f("fk_migrated_journal_line_account_id_ledger_account"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_migrated_journal_line")),
            sa.UniqueConstraint(
                "entry_id", "line_no", name=op.f("uq_migrated_journal_line_entry_id")
            ),
        )
        op.create_index(
            "ix_migrated_journal_line_account",
            "migrated_journal_line",
            ["tenant_id", "account_number"],
        )
        _rls("migrated_journal_line")

    if not _has_table("migration_opening_balance"):
        op.create_table(
            "migration_opening_balance",
            sa.Column("id", _uuid(), nullable=False),
            sa.Column("tenant_id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("ledger_id", _uuid(), nullable=False),
            sa.Column("cutoff_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
            sa.Column(
                "entered_via", sa.String(16), nullable=False, server_default=sa.text("'form'")
            ),
            sa.Column("source_file_id", _uuid(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("released_by", _uuid(), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("release_comment", sa.Text(), nullable=True),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("posted_by", _uuid(), nullable=True),
            sa.Column("journal_entry_id", _uuid(), nullable=True),
            _tenant_fk("migration_opening_balance"),
            sa.ForeignKeyConstraint(
                ["ledger_id"],
                ["ledger.id"],
                name=op.f("fk_migration_opening_balance_ledger_id_ledger"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_file_id"],
                ["import_source_file.id"],
                name=op.f("fk_migration_opening_balance_source_file_id_import_source_file"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["journal_entry_id"],
                ["journal_entry.id"],
                name=op.f("fk_migration_opening_balance_journal_entry_id_journal_entry"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_migration_opening_balance")),
            sa.UniqueConstraint(
                "tenant_id",
                "ledger_id",
                "cutoff_date",
                name=op.f("uq_migration_opening_balance_tenant_id"),
            ),
        )
        _rls("migration_opening_balance")

    if not _has_table("migration_opening_balance_line"):
        op.create_table(
            "migration_opening_balance_line",
            sa.Column("id", _uuid(), nullable=False),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column("opening_balance_id", _uuid(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("account_id", _uuid(), nullable=False),
            _money("amount", default=None),
            sa.Column("text", sa.String(500), nullable=True),
            sa.Column("property_bank_account_id", _uuid(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.CheckConstraint(
                "amount <> 0", name=op.f("ck_migration_opening_balance_line_amount_non_zero")
            ),
            _tenant_fk("migration_opening_balance_line"),
            sa.ForeignKeyConstraint(
                ["opening_balance_id"],
                ["migration_opening_balance.id"],
                name=op.f(
                    "fk_migration_opening_balance_line_opening_balance_id_migration_opening_balance"
                ),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["account_id"],
                ["ledger_account.id"],
                name=op.f("fk_migration_opening_balance_line_account_id_ledger_account"),
            ),
            sa.ForeignKeyConstraint(
                ["property_bank_account_id"],
                ["property_bank_account.id"],
                name=op.f(
                    "fk_migration_opening_balance_line_property_bank_account_id_property_bank_account"
                ),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_migration_opening_balance_line")),
            sa.UniqueConstraint(
                "opening_balance_id",
                "account_id",
                name=op.f("uq_migration_opening_balance_line_opening_balance_id"),
            ),
        )
        _rls("migration_opening_balance_line")

    if not _has_table("migration_reconciliation_report"):
        op.create_table(
            "migration_reconciliation_report",
            sa.Column("id", _uuid(), nullable=False),
            sa.Column("tenant_id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("property_id", _uuid(), nullable=False),
            sa.Column("as_of", sa.Date(), nullable=False),
            sa.Column(
                "zero_difference", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column("compared", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("deviations", sa.Integer(), nullable=False, server_default=sa.text("0")),
            _money("total_difference"),
            _jsonb("lines", "[]"),
            _jsonb("summary", "{}"),
            sa.Column("document_id", _uuid(), nullable=True),
            _tenant_fk("migration_reconciliation_report"),
            sa.ForeignKeyConstraint(
                ["property_id"],
                ["property.id"],
                name=op.f("fk_migration_reconciliation_report_property_id_property"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["document_id"],
                ["document.id"],
                name=op.f("fk_migration_reconciliation_report_document_id_document"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_migration_reconciliation_report")),
        )
        op.create_index(
            "ix_migration_reconciliation_report_property",
            "migration_reconciliation_report",
            ["tenant_id", "property_id"],
        )
        _rls("migration_reconciliation_report")

    if not _has_table("migration_switch_request"):
        op.create_table(
            "migration_switch_request",
            sa.Column("id", _uuid(), nullable=False),
            sa.Column("tenant_id", _uuid(), nullable=False),
            _stamp("created_at"),
            _stamp("updated_at"),
            sa.Column("created_by", _uuid(), nullable=True),
            sa.Column("updated_by", _uuid(), nullable=True),
            sa.Column("ledger_id", _uuid(), nullable=False),
            sa.Column("report_id", _uuid(), nullable=False),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default=sa.text("'requested'")
            ),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("requested_by", _uuid(), nullable=False),
            sa.Column("decided_by", _uuid(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_comment", sa.Text(), nullable=True),
            _tenant_fk("migration_switch_request"),
            sa.ForeignKeyConstraint(
                ["ledger_id"],
                ["ledger.id"],
                name=op.f("fk_migration_switch_request_ledger_id_ledger"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["report_id"],
                ["migration_reconciliation_report.id"],
                name=op.f("fk_migration_switch_request_report_id_migration_reconciliation_report"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_migration_switch_request")),
        )
        op.create_index(
            "uq_migration_switch_request_open",
            "migration_switch_request",
            ["tenant_id", "ledger_id"],
            unique=True,
            postgresql_where=sa.text("status = 'requested'"),
        )
        _rls("migration_switch_request")


def downgrade() -> None:
    for table in TABLES:
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
