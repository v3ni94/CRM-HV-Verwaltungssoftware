# mhvp.platform

Tenants, users, memberships, roles, licenses, usage, release gate persistence.

* Milestone: M2 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 5, 18.0.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/platform/`. Register models in `mhvp/models.py` for Alembic autogenerate.
