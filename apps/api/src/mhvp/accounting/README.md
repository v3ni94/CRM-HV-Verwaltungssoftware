# mhvp.accounting

Ledger per legal entity, accounts, journal, open items (MASTER-PROMPT 6.4, 6.9, 7.1 to 7.3).

* `models.py`: chart template, ledger, ledger_account, journal_entry/line, number counter,
  open_item, open_item_settlement. Migration 0010 adds immutability and balance triggers.
* `services.py`: drafts, posting (gapless numbers, ADR 0007), reversal, locking, reports,
  consistency checks.
* `routers.py`: `/api/v1/accounting/...`.
* `dunning.py`: dunning runs (7.5, M16). Settings per tenant with field level object
  overrides (`settings_for` returns `EffectiveSettings`, NULL on an object row inherits the
  tenant default, migration 0078, `docs/rules/M16-02.md`). Fees and interest only from
  configured values (`docs/rules/M16-01.md`).
* `dunning_letters.py`: dunning letter as PDF draft on the tenant letterhead
  (`mhvp.documents.letters`, DIN 5008). `POST /dunning-cases/{id}/letter-preview` (PDF, not
  filed), `POST /dunning-cases/{id}/letter` (filed, linked to the case), `POST
  /dunning-cases/{id}/letter/send` always refuses (G1 closed; dispatch not released, M16-02).
* Gate: declaring the platform as leading system requires G1. Until then ledgers run in
  parallel to Immoware24 and are not the leading bookkeeping.
* Rules: `docs/rules/B01.md` to `B09.md`. Plan: `docs/plans/M10.md`.
