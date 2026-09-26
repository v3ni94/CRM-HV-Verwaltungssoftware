# mhvp.properties

Properties, buildings, units, allocation keys and values, meters, contacts, service provider relations, bank accounts, maintenance.

* Milestone: M4 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.2, 6.9.1.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/properties/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `defaults.py`: tenant defaults for M4: catalogues and allocation key template (annex A.2, A.3)

## Performance (Review 26.09.2026)

`GET /properties/{id}/units` loads allocation values and VAT options of all units in two
queries (`_units_out`). Indexes `property(tenant_id, status, management_type)` and
`maintenance_item(tenant_id, status, due_date)` (migration 0127). Measurements in
`docs/reviews/2026-09-26-performance.md`.
