# mhvp.billing

Operating cost statements, economic plans, HOA fee statements, reserves, special levies, heating costs.

* Milestone: M17, M24 (status model schema from M5) (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.5, 6.9.3, 7.6, 7.8, 7.10.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/billing/`. Register models in `mhvp/models.py` for Alembic autogenerate.
