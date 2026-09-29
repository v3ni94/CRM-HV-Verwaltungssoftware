# mhvp.letting

Rent increases, vacancies, exposés, prospects, listings and the OpenImmo export (M26, M28).
Plans: `docs/plans/M26.md`, `docs/plans/M28-makler.md`. Rules: `docs/rules/M26-rent-law.md`,
`docs/rules/M26-02.md`, `docs/rules/M28-01.md`.

## Files

* `models.py`: rent increase cases, prospects, listings (migration 0023 and later, RLS).
* `routers.py`: `/api/v1/letting` (rent increase process, vacancies, exposé draft, prospects,
  listings); registered in `main.py`.
* `rentlaw.py`: rent law rule set for rent increases (M26-01); `platform_router` and
  `tenant_router` registered in `main.py`.
* `openimmo.py`: OpenImmo 1.2.7 XML export for listings (M26-02), read only, no portal upload.
* `openimmo_schema.py`: structural check of the OpenImmo export (no official XSD bundled).
* `flow_import.py`: FLOW import from a MySQL/MariaDB dump (M28 stage 4), idempotent per
  `external_uuid`.
* `tasks.py`: Celery job deleting prospect records after their deletion date (data minimisation).

Gates: no money flows; sending to portals or FLOWFACT is not implemented (M28 stage 3 open).

## Addendum 29.09.2026 (rent increase letter on the letterhead, M12 gaps)

* `routers.py`: `POST /letting/rent-increases/{id}/letter/pdf` (`contracts:approve`) files the
  letter of `rentlaw.letter_body` on the tenant letterhead as a document of the case, contract,
  unit, property and tenant, optional ticket link and dispatch record
  (`mhvp.documents.letter_records`). The process step `send` stays behind G3, the portal
  channel is refused while G3 is closed, e-mail only as a draft for the mail approval; the PDF
  carries the draft marking until the legal review is documented.

