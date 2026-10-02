"""AJ03 (GAI-209 to GAI-212, 7.1 B03/B04): database guards for booking related tables.

* open_item: only written_off, due_date, notice_received_on and a first contract_id stay
  changeable (open decision AJ03-01 for further fields).
* journal_entry: no posting on or before ``ledger.locked_until`` (period lock in the database).
* payment_order: payment fields frozen after approval stage, delete only as draft.
* deposit_movement: insert only, except setting ``posting_id`` once.
* receivable_item: posted items only change status posted -> reversed (plus message).
* journal_number_counter: last_number never decreases, a used counter is never deleted.

Revision ID: 0444
Revises: 0443
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0444"
down_revision: str | None = "0443"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_META = "'updated_at', 'updated_by'"

OPEN_ITEM_GUARD_NEW = f"""
CREATE OR REPLACE FUNCTION mhvp_open_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'open item % is immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;
  IF (to_jsonb(NEW) - ARRAY['written_off', 'due_date', 'notice_received_on', 'contract_id',
                           {_META}])
     IS DISTINCT FROM
     (to_jsonb(OLD) - ARRAY['written_off', 'due_date', 'notice_received_on', 'contract_id',
                           {_META}])
     OR (OLD.contract_id IS NOT NULL AND NEW.contract_id IS DISTINCT FROM OLD.contract_id)
  THEN
    RAISE EXCEPTION 'open item % is immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$
"""

# Body of 0010, restored on downgrade.
OPEN_ITEM_GUARD_OLD = """
CREATE OR REPLACE FUNCTION mhvp_open_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' OR NEW.amount <> OLD.amount OR NEW.account_id <> OLD.account_id
     OR NEW.journal_entry_id <> OLD.journal_entry_id OR NEW.ledger_id <> OLD.ledger_id THEN
    RAISE EXCEPTION 'open item % is immutable', OLD.id USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$
"""

STATEMENTS = [
    OPEN_ITEM_GUARD_NEW,
    """
    CREATE FUNCTION mhvp_journal_entry_period_lock() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      lock_day date;
    BEGIN
      IF NEW.status = 'posted'
         AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'posted') THEN
        SELECT locked_until INTO lock_day FROM ledger WHERE id = NEW.ledger_id;
        IF lock_day IS NOT NULL AND NEW.booking_date <= lock_day THEN
          RAISE EXCEPTION 'period of ledger % is locked until %', NEW.ledger_id, lock_day
            USING ERRCODE = 'P0001';
        END IF;
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER journal_entry_period_lock BEFORE INSERT OR UPDATE ON journal_entry
    FOR EACH ROW EXECUTE FUNCTION mhvp_journal_entry_period_lock()
    """,
    """
    CREATE FUNCTION mhvp_payment_order_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
          RAISE EXCEPTION 'payment order % is immutable', OLD.id USING ERRCODE = 'P0001';
        END IF;
        RETURN OLD;
      END IF;
      IF OLD.status NOT IN ('draft', 'approved') AND (
           NEW.tenant_id, NEW.ledger_id, NEW.property_bank_account_id, NEW.kind,
           NEW.invoice_id, NEW.open_item_id, NEW.amount, NEW.discount, NEW.counterpart_name,
           NEW.counterpart_iban_fingerprint, NEW.purpose, NEW.end_to_end_id,
           NEW.execution_date, NEW.contact_bank_account_id, NEW.payout_reason
         ) IS DISTINCT FROM (
           OLD.tenant_id, OLD.ledger_id, OLD.property_bank_account_id, OLD.kind,
           OLD.invoice_id, OLD.open_item_id, OLD.amount, OLD.discount, OLD.counterpart_name,
           OLD.counterpart_iban_fingerprint, OLD.purpose, OLD.end_to_end_id,
           OLD.execution_date, OLD.contact_bank_account_id, OLD.payout_reason
         ) THEN
        RAISE EXCEPTION 'payment order % is immutable', OLD.id USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER payment_order_guard BEFORE UPDATE OR DELETE ON payment_order
    FOR EACH ROW EXECUTE FUNCTION mhvp_payment_order_guard()
    """,
    f"""
    CREATE FUNCTION mhvp_deposit_movement_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE'
         OR (to_jsonb(NEW) - ARRAY['posting_id', {_META}])
            IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['posting_id', {_META}])
         OR (OLD.posting_id IS NOT NULL AND NEW.posting_id IS DISTINCT FROM OLD.posting_id)
      THEN
        RAISE EXCEPTION 'deposit movement % is immutable', OLD.id USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER deposit_movement_guard BEFORE UPDATE OR DELETE ON deposit_movement
    FOR EACH ROW EXECUTE FUNCTION mhvp_deposit_movement_guard()
    """,
    f"""
    CREATE FUNCTION mhvp_receivable_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status NOT IN ('posted', 'reversed') THEN
        IF TG_OP = 'DELETE' THEN
          RETURN OLD;
        END IF;
        RETURN NEW;
      END IF;
      IF TG_OP = 'DELETE'
         OR (to_jsonb(NEW) - ARRAY['status', 'message', {_META}])
            IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status', 'message', {_META}])
         OR (NEW.status IS DISTINCT FROM OLD.status
             AND NOT (OLD.status = 'posted' AND NEW.status = 'reversed'))
      THEN
        RAISE EXCEPTION 'receivable item % is immutable', OLD.id USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER receivable_item_guard BEFORE UPDATE OR DELETE ON receivable_item
    FOR EACH ROW EXECUTE FUNCTION mhvp_receivable_item_guard()
    """,
    """
    CREATE FUNCTION mhvp_journal_number_counter_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        IF OLD.last_number > 0 THEN
          RAISE EXCEPTION 'journal number counter is in use' USING ERRCODE = 'P0001';
        END IF;
        RETURN OLD;
      END IF;
      IF NEW.last_number < OLD.last_number OR NEW.ledger_id <> OLD.ledger_id
         OR NEW.fiscal_year <> OLD.fiscal_year OR NEW.tenant_id <> OLD.tenant_id THEN
        RAISE EXCEPTION 'journal number counter never decreases' USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER journal_number_counter_guard BEFORE UPDATE OR DELETE
    ON journal_number_counter FOR EACH ROW EXECUTE FUNCTION mhvp_journal_number_counter_guard()
    """,
]

DROPPED = (
    ("journal_entry_period_lock", "journal_entry", "mhvp_journal_entry_period_lock"),
    ("payment_order_guard", "payment_order", "mhvp_payment_order_guard"),
    ("deposit_movement_guard", "deposit_movement", "mhvp_deposit_movement_guard"),
    ("receivable_item_guard", "receivable_item", "mhvp_receivable_item_guard"),
    (
        "journal_number_counter_guard",
        "journal_number_counter",
        "mhvp_journal_number_counter_guard",
    ),
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Schema only: no rows are changed, so FORCE ROW LEVEL SECURITY stays untouched.
    for trigger, table, function in DROPPED:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    op.execute(OPEN_ITEM_GUARD_OLD)
