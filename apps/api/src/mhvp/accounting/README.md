# mhvp.accounting

Legal entity ledgers, accounts, journal, open items, receivable runs, dunning, payment runs, exports.

* Milestone: M10 (schema parts from M4/M5) (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.4, 6.9, 7.1 to 7.7.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/accounting/`. Register models in `mhvp/models.py` for Alembic autogenerate.
