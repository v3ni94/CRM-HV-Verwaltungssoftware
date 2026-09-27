# ADR 0012: Inline editing of master data with PATCH and optimistic locking

- Status: Accepted (operator wish, Ergänzung CRM AP8, 27.09.2026)
- Date: 2026-09-27

## Context

The operator wants master data of property, building, unit and contact editable in place on
the detail page (pencil or "Bearbeiten"), saved per field without a form round trip. The
existing routes are full replacements (`PUT` with the complete record and `If-Match`). A per
field autosave with `PUT` would have to resend the whole record on every keystroke and would
overwrite concurrent changes of other fields.

## Decision

1. Partial updates via `PATCH`: `/properties/{id}`, `/buildings/{id}`, `/units/{id}`
   (`mhvp.properties.routers_patch`), `/contacts/{id}` (master data fields only) and
   `/contracts/{id}/notes`. The body carries only the changed fields (`exclude_unset`); the
   server merges them into the current record and validates the result with the schema of the
   `PUT` route, so no rule of the full update is bypassed. Merge errors are answered as the same
   422 problem details as a body error (`mhvp.core.problems.body_validation_error`).
2. Optimistic locking as on `PUT`: `If-Match` against `version`, 412 `MHVP-PLAT-0003` on a
   stale version, `ETag` in the response. Permissions equal the `PUT` route
   (`properties:update`, `contacts:update`, `contracts:update`).
3. Audit as on `PUT`: one domain event per `PATCH` with the diff of the changed fields and the
   list of sent fields (`payload.fields`).
4. Contracts (operator decision (c) 4, option a): only `notes`, `dunning_block` and
   `dunning_block_reason` change in place and without a new contract version. Payments,
   terms and parties keep the version path (7.4, invariants B01 to B09). The notes route sends
   no `If-Match`, since `version` of a contract is the business version, not a lock counter.
5. Frontend: `EditableSection` (toggle, status, conflict notice), `InlineField` (one field,
   view and edit mode) and `useAutosave` (debounced queue of `PATCH` requests per field,
   version taken from each response, one retry on a network failure, 412 shown as "Von
   jemand anderem geändert, neu laden"). Fields are editable only with the write permission;
   financial fields are never inline fields.

## Consequences

- Two write paths per entity (`PUT` and `PATCH`) share the schema and the audit format; the
  `PUT` routes stay for the forms and the API client.
- Children of a contact (addresses, phones, e-mails, identifiers, dates, bank accounts, types,
  roles, tags) are not patchable; the four eyes rule for IBANs stays untouched.
- No migration: `version` exists on property, building, unit and contact (AP2 added it to
  building and unit).
