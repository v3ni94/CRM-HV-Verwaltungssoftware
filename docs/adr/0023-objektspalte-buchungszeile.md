# ADR 0023: Object column on journal lines and one time fill of posted lines (Q15-01)

- Status: Accepted for implementation by the operator's priority list of 01.10.2026 (item 21);
  expert acceptance of the released scope pending (gate G1 stays closed)
- Date: 01.10.2026
- Package: AE21 (wave 16), migration 0377

## Context

Section 6.9 of the master prompt defines `journal_line` with an optional `unit_id` and no object
of its own. M18-06 (VAT overview per object, Q15) therefore derived the object from the line's
unit, and lines without unit appeared as "ohne Objekt". The period lock per object (P06-02,
AE20) derives the object from the unit or the ledger. Q15-01 asked whether a dedicated object
column is needed; the operator put it on the priority list (item 21) to be implemented.

Two constraints apply:

1. Posted lines are immutable (rule 0.1.7, B02). The database guard `journal_line_guard`
   (migrations 0010, 0346) refuses every UPDATE of a line of a posted entry.
2. Tenant tables force row level security for the owner role as well (ADR 0002), so a data
   migration runs once per tenant with the transaction local tenant setting.

## Decision

1. New column `journal_line.property_id` (nullable, FK `fk_journal_line_property_id_property`
   to `property.id`, index `ix_journal_line_property_id`).
2. Derivation when a draft line is written (`mhvp.accounting.line_property.resolve`), in this
   order: explicit value of the line, the unit's object (an explicit value must match it,
   otherwise 422), the object of the entry's contract (`journal_entry.contract_id`). Nothing
   else is derived (no object from the ledger, cost center or text). A reversal copies the
   object of the original line.
3. Database rule for every writer (jobs, imports, integrations): check
   `ck_journal_line_property_with_unit` (`unit_id IS NULL OR property_id IS NOT NULL`) and
   trigger `journal_line_property` (fills the object from the unit when empty, refuses a
   different object). The trigger name sorts after `journal_line_guard`, so the guard decides
   first.
4. One time fill in migration 0377 from the unit, else from the contract of the entry, per
   tenant. For posted lines the guard is disabled only for these two UPDATE statements inside
   the migration's transaction (the migrator owns the table) and enabled again before the
   check and trigger are created. If the migration fails, the transaction rolls back including
   the guard state.
5. Corrections after posting: a posted line keeps its object. A wrong object is corrected by
   reversal and new posting (rule 0.1.7). The drift report
   `GET /accounting/ledgers/{id}/reports/line-property-drift` lists every line whose object
   differs from its sources: `unit_mismatch` is a hard finding (also in
   `GET /ledgers/{id}/checks`), `contract_unfilled`, `contract_mismatch` and `ledger_mismatch`
   are hints. The report changes nothing.

## Why the one time fill of posted lines is acceptable

- No existing value is overwritten: the column is new and empty, the fill only sets values
  where it is `NULL`.
- No financial content changes: amounts, accounts, dates, texts, unit and contract stay as
  posted. The object is a reporting dimension derived from immutable data of the same line and
  entry; every filled value can be recomputed at any time (drift report).
- The runtime guard is unchanged. The application role still cannot change a posted line,
  including its object.

## Alternatives

- Computed object only (view or join on unit and contract): no schema change, but every report
  repeats the derivation and an explicit object for lines without unit is impossible.
- Fill draft lines only: posted history would stay "ohne Objekt" although its unit is known;
  reports per object would differ by posting date.
- Relax the guard permanently for a first fill of `property_id`: opens a runtime write path to
  posted lines; rejected.
- Derive the object from the ledger (`ledger.property_id`, WEG ledgers): deterministic for a
  WEG ledger but not requested; kept as an open option (OPEN_QUESTIONS AE21-01). The drift
  report already shows lines whose object differs from the ledger's object.

## Consequences

- AE20 (`period_lock.property_ids_of_lines`) reads the column already when it exists; the
  unit join there can be replaced by the column (follow up of AE20, no behaviour change because
  lines with unit carry the unit's object).
- VAT overview per object (M18-06) groups by the column; monthly matrix, income statement and
  journal accept a `property_id` filter.
- Rollback: downgrade of 0377 drops trigger, function, check, index, FK and column; no posted
  financial content is touched.
