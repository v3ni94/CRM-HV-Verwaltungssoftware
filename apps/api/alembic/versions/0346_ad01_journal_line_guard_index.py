"""AD01: indexable lookup in the journal line guard, bank transaction date index.

The line guard of 0010 looked the entry up with
``WHERE id = COALESCE(NEW.journal_entry_id, OLD.journal_entry_id)``; measured cost grew
linearly with ``journal_entry`` (ADR 0021). The new body has the same rules (lines of a posted
entry are immutable, a line's account belongs to the entry's ledger; B02, B03) but looks the
entry up per operation with a plain parameter. Downgrade restores the 0010 body verbatim.

Revision ID: 0346
Revises: 0345
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0346"
down_revision: str | None = "0345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same rules as 0010; only the lookup differs: one branch per operation, no COALESCE in the
# WHERE clause. For UPDATE the new entry id is checked, exactly like COALESCE(NEW, OLD) did.
GUARD_NEW = """
CREATE OR REPLACE FUNCTION mhvp_journal_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  entry_id uuid;
  entry_status journal_entry_status;
  entry_ledger uuid;
  account_ledger uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    entry_id := OLD.journal_entry_id;
  ELSE
    entry_id := NEW.journal_entry_id;
  END IF;
  SELECT e.status, e.ledger_id INTO entry_status, entry_ledger
    FROM journal_entry e WHERE e.id = entry_id;
  IF entry_status = 'posted' THEN
    RAISE EXCEPTION 'lines of posted journal entry % are immutable', entry_id
      USING ERRCODE = 'P0001';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  SELECT a.ledger_id INTO account_ledger FROM ledger_account a WHERE a.id = NEW.account_id;
  IF account_ledger IS DISTINCT FROM entry_ledger THEN
    RAISE EXCEPTION 'account % belongs to another ledger', NEW.account_id
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$
"""

# Verbatim body of 0010.
GUARD_OLD = """
CREATE OR REPLACE FUNCTION mhvp_journal_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  entry_row journal_entry%ROWTYPE;
  account_ledger uuid;
BEGIN
  SELECT * INTO entry_row FROM journal_entry
    WHERE id = COALESCE(NEW.journal_entry_id, OLD.journal_entry_id);
  IF entry_row.status = 'posted' THEN
    RAISE EXCEPTION 'lines of posted journal entry % are immutable', entry_row.id
      USING ERRCODE = 'P0001';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  SELECT ledger_id INTO account_ledger FROM ledger_account WHERE id = NEW.account_id;
  IF account_ledger IS DISTINCT FROM entry_row.ledger_id THEN
    RAISE EXCEPTION 'account % belongs to another ledger', NEW.account_id
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$
"""


def upgrade() -> None:
    op.execute(GUARD_NEW)
    op.create_index(
        "ix_bank_transaction_booking_date", "bank_transaction", ["tenant_id", "booking_date"]
    )


def downgrade() -> None:
    # IF EXISTS: databases that ran the earlier, since renumbered AD07 revision 0346 carry the
    # id 0346 without this index (wave 15 numbering clash).
    op.execute("DROP INDEX IF EXISTS ix_bank_transaction_booking_date")
    op.execute(GUARD_OLD)
