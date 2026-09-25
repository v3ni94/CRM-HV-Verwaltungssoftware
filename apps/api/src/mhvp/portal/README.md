# mhvp.portal

Portal specific endpoints and access matrix filters.

* Milestone: M21, M22 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.6, 14.
* Status: M21/M22 portal API implemented. See docs/plans/M21.md. Handover protocols of a
  participant (M30 stage 3) live in `mhvp.handover.portal`; their grants (`scope_type`
  `handover`, `legal_basis` `handover_participant`) are manual and survive `access.sync_grants`.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/portal/`. Register models in `mhvp/models.py` for Alembic autogenerate.
