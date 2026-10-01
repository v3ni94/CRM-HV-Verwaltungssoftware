"""AE21 / Q15-01: object column on journal lines (ADR 0023).

* ``journal_line.property_id`` (nullable, FK to ``property``, index): object of the line.
* One time fill per tenant (FORCE RLS, ADR 0002): from the line's unit (``unit.property_id``),
  else from the contract of the entry (``contract.property_id``). Nothing else is derived; lines
  without both stay without object.
* The fill writes the new, derived column of posted lines as well. The posted line guard
  ``journal_line_guard`` (B02) is disabled only for these statements inside this migration's
  transaction and enabled again before the constraint and trigger are created; no existing
  value is overwritten (the column is new) and every filled value is recomputable from the
  unchanged line and entry (drift report ``line-property-drift``).
* ``ck_journal_line_property_with_unit``: a line with unit carries an object.
* Trigger ``journal_line_property`` (after ``journal_line_guard`` by name): fills the object of
  a line with unit from the unit and refuses a different object, for every writer.

Revision ID: 0377
Revises: 0376
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0377"
down_revision: str | None = "0376"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FILL_FROM_UNIT = """
UPDATE journal_line l SET property_id = u.property_id
FROM unit u
WHERE u.id = l.unit_id AND l.property_id IS NULL
"""

FILL_FROM_CONTRACT = """
UPDATE journal_line l SET property_id = c.property_id
FROM journal_entry e JOIN contract c ON c.id = e.contract_id
WHERE e.id = l.journal_entry_id AND l.unit_id IS NULL AND l.property_id IS NULL
"""

PROPERTY_FUNCTION = """
CREATE FUNCTION mhvp_journal_line_property() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  unit_property uuid;
BEGIN
  IF NEW.unit_id IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT u.property_id INTO unit_property FROM unit u WHERE u.id = NEW.unit_id;
  IF unit_property IS NULL THEN
    RETURN NEW;  -- unknown unit: the foreign key and the check constraint refuse the row
  END IF;
  IF NEW.property_id IS NULL THEN
    NEW.property_id := unit_property;
  ELSIF NEW.property_id <> unit_property THEN
    RAISE EXCEPTION 'property % of the line differs from the property of unit %',
      NEW.property_id, NEW.unit_id USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$
"""

PROPERTY_TRIGGER = """
CREATE TRIGGER journal_line_property BEFORE INSERT OR UPDATE OF unit_id, property_id
ON journal_line FOR EACH ROW EXECUTE FUNCTION mhvp_journal_line_property()
"""


def _fill_per_tenant() -> None:
    bind = op.get_bind()
    tenants = [str(r[0]) for r in bind.execute(sa.text("SELECT id FROM tenant")).all()]
    if not tenants:
        return
    op.execute("ALTER TABLE journal_line DISABLE TRIGGER journal_line_guard")
    for tenant_id in tenants:
        bind.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        bind.execute(sa.text(FILL_FROM_UNIT))
        bind.execute(sa.text(FILL_FROM_CONTRACT))
    bind.execute(sa.text("SELECT set_config('app.tenant_id', '', true)"))
    op.execute("ALTER TABLE journal_line ENABLE TRIGGER journal_line_guard")


def upgrade() -> None:
    op.add_column("journal_line", sa.Column("property_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_journal_line_property_id_property"),
        "journal_line",
        "property",
        ["property_id"],
        ["id"],
    )
    _fill_per_tenant()
    op.create_index(op.f("ix_journal_line_property_id"), "journal_line", ["property_id"])
    op.create_check_constraint(
        op.f("ck_journal_line_property_with_unit"),
        "journal_line",
        "unit_id IS NULL OR property_id IS NOT NULL",
    )
    op.execute(PROPERTY_FUNCTION)
    op.execute(PROPERTY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS journal_line_property ON journal_line")
    op.execute("DROP FUNCTION IF EXISTS mhvp_journal_line_property()")
    op.drop_constraint(op.f("ck_journal_line_property_with_unit"), "journal_line", type_="check")
    op.drop_index(op.f("ix_journal_line_property_id"), table_name="journal_line")
    op.drop_constraint(
        op.f("fk_journal_line_property_id_property"), "journal_line", type_="foreignkey"
    )
    op.drop_column("journal_line", "property_id")
