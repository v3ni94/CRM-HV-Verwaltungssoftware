# mhvp.banking

Bank connectors (EBICS, aggregator, FinTS fallback, file import), transactions, rules, matching.

* Milestone: M11, M12 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.4, 6.9.7, 7.4, 8.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/banking/`. Register models in `mhvp/models.py` for Alembic autogenerate.
