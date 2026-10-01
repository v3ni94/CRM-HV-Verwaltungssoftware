"""Import assistant, Welle 3 (M8-02, M8-03, M8-04, M8-06, M8-07).

* ``import_report_type``: new values ``sepa_overview``, ``chart_of_accounts``,
  ``bank_history``, ``document_index``, ``ticket_history``, ``open_items``.
* ``migrated_bank_link``: historical bank transaction to the migrated journal entry. RLS.
* ``migrated_ticket``: historical tickets of the old system, read only. RLS.
* ``migrated_open_item``: single open items, credits, deposits, reserves, loans and special
  levies of the cut off date with original due date and partial payments. RLS.

Idempotent: tables are created only when missing.

Revision ID: 0277
Revises: 0276
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0277"
down_revision: str | None = "0276"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_REPORT_TYPES = (
    "sepa_overview",
    "chart_of_accounts",
    "bank_history",
    "document_index",
    "ticket_history",
    "open_items",
)
TABLES = ("migrated_open_item", "migrated_ticket", "migrated_bank_link")


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _stamp(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    ref_table = target.split(".")[0]
    return sa.ForeignKeyConstraint(
        [column],
        [target],
        name=op.f(f"fk_{table}_{column}_{ref_table}"),
        ondelete=ondelete,
    )


def _common(table: str) -> list[sa.SchemaItem]:
    return [
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", _uuid(), nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.Column("created_by", _uuid(), nullable=True),
        sa.Column("updated_by", _uuid(), nullable=True),
    ]


def _tail(table: str) -> list[sa.SchemaItem]:
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def _rls(table: str) -> None:
    for statement in tenant_rls_statements(table):
        op.execute(statement)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on older servers: use an
    # autocommit block (same as the other enum extensions of this chain).
    with op.get_context().autocommit_block():
        for value in NEW_REPORT_TYPES:
            op.execute(f"ALTER TYPE import_report_type ADD VALUE IF NOT EXISTS '{value}'")

    if not _has_table("migrated_bank_link"):
        t = "migrated_bank_link"
        op.create_table(
            t,
            *_common(t),
            sa.Column("bank_transaction_id", _uuid(), nullable=False),
            sa.Column("journal_entry_id", _uuid(), nullable=True),
            sa.Column("source_entry_id", sa.String(100), nullable=True),
            sa.Column("source_file_id", _uuid(), nullable=True),
            sa.Column("row_number", sa.Integer(), nullable=True),
            *_tail(t),
            _fk(t, "bank_transaction_id", "bank_transaction.id", "CASCADE"),
            _fk(t, "journal_entry_id", "migrated_journal_entry.id", "SET NULL"),
            _fk(t, "source_file_id", "import_source_file.id", "SET NULL"),
            sa.UniqueConstraint("tenant_id", "bank_transaction_id", name=op.f(f"uq_{t}_tenant_id")),
        )
        _rls(t)

    if not _has_table("migrated_ticket"):
        t = "migrated_ticket"
        op.create_table(
            t,
            *_common(t),
            sa.Column(
                "source", sa.String(40), nullable=False, server_default=sa.text("'immoware24'")
            ),
            sa.Column("source_ticket_id", sa.String(100), nullable=False),
            sa.Column("property_id", _uuid(), nullable=False),
            sa.Column("unit_id", _uuid(), nullable=True),
            sa.Column("contact_id", _uuid(), nullable=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("status_text", sa.String(100), nullable=True),
            sa.Column("created_on", sa.Date(), nullable=False),
            sa.Column("closed_on", sa.Date(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source_file_id", _uuid(), nullable=True),
            sa.Column(
                "raw",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            *_tail(t),
            _fk(t, "property_id", "property.id", "CASCADE"),
            _fk(t, "unit_id", "unit.id", "SET NULL"),
            _fk(t, "contact_id", "contact.id", "SET NULL"),
            _fk(t, "source_file_id", "import_source_file.id", "SET NULL"),
            sa.UniqueConstraint(
                "tenant_id", "source", "source_ticket_id", name=op.f(f"uq_{t}_tenant_id")
            ),
        )
        op.create_index(
            "ix_migrated_ticket_property", t, ["tenant_id", "property_id", "created_on"]
        )
        _rls(t)

    if not _has_table("migrated_open_item"):
        t = "migrated_open_item"
        op.create_table(
            t,
            *_common(t),
            sa.Column("ledger_id", _uuid(), nullable=False),
            sa.Column(
                "source", sa.String(40), nullable=False, server_default=sa.text("'immoware24'")
            ),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("source_item_id", sa.String(100), nullable=False),
            sa.Column("property_id", _uuid(), nullable=False),
            sa.Column("unit_id", _uuid(), nullable=True),
            sa.Column("contact_id", _uuid(), nullable=True),
            sa.Column("original_due_date", sa.Date(), nullable=True),
            sa.Column("original_amount", sa.Numeric(14, 2), nullable=False),
            sa.Column(
                "paid_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("open_amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("resolution_ref", sa.String(200), nullable=True),
            sa.Column("cutoff_date", sa.Date(), nullable=True),
            sa.Column("source_file_id", _uuid(), nullable=True),
            *_tail(t),
            _fk(t, "ledger_id", "ledger.id", "CASCADE"),
            _fk(t, "property_id", "property.id", "CASCADE"),
            _fk(t, "unit_id", "unit.id", "SET NULL"),
            _fk(t, "contact_id", "contact.id", "SET NULL"),
            _fk(t, "source_file_id", "import_source_file.id", "SET NULL"),
            sa.UniqueConstraint(
                "tenant_id",
                "ledger_id",
                "source",
                "kind",
                "source_item_id",
                name=op.f(f"uq_{t}_tenant_id"),
            ),
            sa.CheckConstraint("paid_amount >= 0", name=op.f(f"ck_{t}_paid_non_negative")),
            sa.CheckConstraint(
                "kind IN ('receivable','credit','deposit','reserve','loan','special_levy')",
                name=op.f(f"ck_{t}_kind_values"),
            ),
        )
        op.create_index("ix_migrated_open_item_ledger", t, ["tenant_id", "ledger_id", "kind"])
        _rls(t)


def downgrade() -> None:
    # Enum values of ``import_report_type`` stay (PostgreSQL cannot drop a value).
    for table in TABLES:
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
