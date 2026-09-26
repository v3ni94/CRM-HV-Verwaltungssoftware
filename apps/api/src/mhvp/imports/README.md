# mhvp.imports

Immoware24 import assistant (M8). Plan: `docs/plans/M8.md`.

* Specification: docs/MASTER-PROMPT.md 13.1, 6.9.10.
* Files: `models.py` (mappings, source files, staging rows), `fields.py` (target fields and
  parsing), `services.py` (stage, validate, test run, apply, reconcile), `routers.py`.
* Import runs and undo come from `mhvp.ai` (`import_run`, `import_run_item`).
* Tests: `apps/api/tests/integration/test_m8_import.py`, `apps/api/tests/unit/test_m8_fields.py`.

## Objektdaten CLI (26.09.2026)

`python -m mhvp.imports.objektdaten FILE --tenant <slug> [--user <email>] [--apply]
[--number-map ALT=NEU,...] [--skip-handed-over]` creates properties and units from the
Immoware24 object list (one row per unit). Default is a test run; `--apply` writes. It reuses
`_apply_property` and `_apply_unit` (existing records: unchanged or conflict, never
overwritten). Owner and tenant names with agreed amounts land only in `unit.custom_fields
["altsystem"]`; no contact, contract, receivable or posting is created. Name prefixes "Z
ABGEGEBEN" set status `terminated`, "Y ABRECHNUNG" sets `active`, otherwise `onboarding`.
Numbers with more than three digits need `--number-map`; one and two digit numbers are zero
padded. Handbook: `docs/handbuch/import-objektdaten.md`. Tests:
`tests/unit/test_objektdaten_import.py`, `tests/integration/test_objektdaten_import.py`.

## Kontakte CLI (26.09.2026)

`python -m mhvp.imports.kontakte FILE... --tenant <slug> [--user <email>] [--apply] [--verbose]`
creates contacts from the Immoware24 contact lists; the operator role comes from the file name
(eigentuemer, mieter, bank, sonstige) or `ROLE=PATH`. Person or company is derived from the
name, the family name from "Nachname, Vorname" or the salutation line, phones are composed from
country code, area code and number and validated; invalid phone or mail values are kept only as
a note. Duplicates by `external_ids["immoware24"]` are not created again, they receive the
additional role. Handbook: `docs/handbuch/import-kontakte.md`. Tests:
`tests/unit/test_kontakte_import.py`, `tests/integration/test_kontakte_import.py`.
