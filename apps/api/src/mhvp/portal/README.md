# mhvp.portal

Portal specific endpoints and access matrix filters.

* Milestone: M21, M22 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.6, 14.
* Status: M21/M22 portal API implemented. See docs/plans/M21.md. Handover protocols of a
  participant (M30 stage 3) live in `mhvp.handover.portal`; their grants (`scope_type`
  `handover`, `legal_basis` `handover_participant`) are manual and survive `access.sync_grants`.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/portal/`. Register models in `mhvp/models.py` for Alembic autogenerate.

Access paths (docs/rules/M21-06.md, D29 to D31): `access.visible_documents` is the single
document filter for portal list and download; `access.document_scope_for_user` applies the same
filter to runs of the AI gateway started on behalf of a portal user; `access.redaction_notes`
marks a released (redacted) version of a receipt, linked to its original with
`entity_type="document"` and role `generated`.
