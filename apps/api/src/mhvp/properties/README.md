# mhvp.properties

Properties, buildings, units, allocation keys and values, meters, contacts, service provider relations, bank accounts, maintenance.

* Milestone: M4 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.2, 6.9.1.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/properties/`. Register models in `mhvp/models.py` for Alembic autogenerate.
