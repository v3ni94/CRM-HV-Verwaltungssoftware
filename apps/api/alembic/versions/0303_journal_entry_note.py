"""Versioned notes on posted journal entries (GA05-02, B03 sentence 3).

* table ``journal_entry_note``: append only (statement trigger ``forbid_mutation``), RLS,
  version chain per ``note_key`` with ``supersedes_id`` (one successor per version).

Revision ID: 0303
Revises: 0302
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0303"
down_revision: str | None = "0302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "journal_entry_note"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("note_key", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("version >= 1", name=op.f("ck_journal_entry_note_version_positive")),
        sa.CheckConstraint(
            "(version = 1 AND supersedes_id IS NULL) OR (version > 1 AND supersedes_id IS NOT "
            "NULL)",
            name=op.f("ck_journal_entry_note_version_chain"),
        ),
        sa.CheckConstraint(
            "length(body) BETWEEN 1 AND 4000", name=op.f("ck_journal_entry_note_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_journal_entry_note_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_journal_entry_note_journal_entry_id_journal_entry"),
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["journal_entry_note.id"],
            name=op.f("fk_journal_entry_note_supersedes_id_journal_entry_note"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entry_note")),
        sa.UniqueConstraint(
            "tenant_id",
            "note_key",
            "version",
            name=op.f("uq_journal_entry_note_tenant_id_note_key_version"),
        ),
        sa.UniqueConstraint("supersedes_id", name=op.f("uq_journal_entry_note_supersedes_id")),
    )
    op.create_index(
        "ix_journal_entry_note_tenant_id_journal_entry_id",
        TABLE,
        ["tenant_id", "journal_entry_id"],
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)
    op.execute(
        f"CREATE TRIGGER {TABLE}_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON {TABLE} "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_append_only ON {TABLE}")
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_journal_entry_note_tenant_id_journal_entry_id", table_name=TABLE)
    op.drop_table(TABLE)
