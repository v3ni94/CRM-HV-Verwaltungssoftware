# mhvp.tickets

Tickets, work orders, templates, SLA.

* Milestone: M19 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.6.
* Status: M19 implemented (tickets, templates, teams, SLA, work orders). See docs/plans/M19.md.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/tickets/`. Register models in `mhvp/models.py` for Alembic autogenerate.
