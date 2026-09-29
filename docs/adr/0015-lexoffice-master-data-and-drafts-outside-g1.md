# ADR 0015: Lexware Office master data sync, invoice copies and drafts outside release gate G1

- Status: Proposed (operator decision pending, docs/OPEN_QUESTIONS.md LEXO-06)
- Date: 2026-09-29

## Context

Release gate G1 (productive bookkeeping, master prompt section 18.0) locks the existing
Lexware Office export of invoices and contacts (`/export/*`, `finalize=true`). The operator
asked on 28.09.2026 for three functions that touch Lexware Office but not the ledger: one way
sync of person applied contact master data, fetching copies of already issued invoices for a
reply draft, and invoice drafts created from the CRM without finalisation. Rule 0.1.1 keeps
money locked; rule 0.1.3 lists data protection and evidence as lock reasons; rule 0.1.6 forbids
autonomous AI actions.

## Decision

The three functions are implemented outside G1 as a Produktschutz decision, each behind its
own per config switch (`sync_contacts`, `invoice_copies`, `invoice_drafts`, default off) that
additionally needs a recorded AVV date and a successful connection test. They never post,
never finalise an invoice and never send bank data. Until the operator approves this ADR the
switches stay off in production. The contact export under G1 additionally writes the contact
link table so contacts have one truth going forward.

## Consequences

- Contact sync: outbound queue, read before write, conflicts never overwritten, forbidden
  field guard, audit events with field names only (rule INT-LEXO-01).
- Invoice copies: recipient verified through the link table, reply draft with locked recipient
  and forced second approval; the draft is a mail, not a bookkeeping record.
- Invoice drafts: `POST /v1/invoices` without `finalize`; completion happens in Lexware
  Office where the tax treatment is reviewed (LEXO-08).
- Tests: `apps/api/tests/integration/test_lexoffice_ext.py`; acceptance run against a trial
  account still open (LEXO-13).

## Alternatives considered

- Keep everything behind G1: blocks harmless master data hygiene until productive bookkeeping
  is released, although no money moves.
- No switches, enabled by config presence: rejected, rule 0.1.1 wants explicit per tenant
  activation with default off.

## References

- `docs/MASTER-PROMPT.md` sections 0.1, 13.3, 18.0
- `docs/rules/INT-LEXO-01-lexware-office.md`, `docs/integrations/lexoffice.md`
