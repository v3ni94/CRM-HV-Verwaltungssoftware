# mhvp.contracts

Tenancy and ownership contracts, payments, schedules, SEPA mandates, deposits, versioning.

* Milestone: M5 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.3, 6.9.2, 6.9.11.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/contracts/`. Register models in `mhvp/models.py` for Alembic autogenerate.
