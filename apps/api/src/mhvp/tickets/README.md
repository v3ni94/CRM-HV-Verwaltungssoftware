# mhvp.tickets

Tickets, work orders, templates, SLA.

* Milestone: M19 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.6.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/tickets/`. Register models in `mhvp/models.py` for Alembic autogenerate.
