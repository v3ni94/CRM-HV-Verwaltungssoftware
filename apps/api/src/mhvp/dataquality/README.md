# mhvp.dataquality

Entry standards (rules ES-01 to ES-11, `docs/rules/ES-erfassungsstandards.md`) and the data
quality report. Operator handbook: `docs/handbuch/erfassungsstandards.md`.

- `rules.py`: pure checks for property, contact and deadline drafts, returning `Finding`s with
  rule id, field, severity (`error`, `warning`, `hint`) and a German message. Mirrored for the
  CRM in `apps/web-crm/src/lib/entry-standards.ts` (keep ids and logic in sync).
- `routers.py`: `GET /data-quality/report` (read only, tenant RLS via `tenant_tx`, sections
  filtered by permission) and `POST /data-quality/check` (advisory, no side effects).

Only ES-01 (German postcode) is enforced, by the property endpoints through
`mhvp.properties.services.check_postcode`. No migration, no automatic data change.
