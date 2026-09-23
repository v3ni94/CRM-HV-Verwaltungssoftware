# mhvp.accounting

Ledger per legal entity, accounts, journal, open items (MASTER-PROMPT 6.4, 6.9, 7.1 to 7.3).

* `models.py`: chart template, ledger, ledger_account, journal_entry/line, number counter,
  open_item, open_item_settlement. Migration 0010 adds immutability and balance triggers.
* `services.py`: drafts, posting (gapless numbers, ADR 0007), reversal, locking, reports,
  consistency checks.
* `routers.py`: `/api/v1/accounting/...`.
* Gate: declaring the platform as leading system requires G1. Until then ledgers run in
  parallel to Immoware24 and are not the leading bookkeeping.
* Rules: `docs/rules/B01.md` to `B09.md`. Plan: `docs/plans/M10.md`.
