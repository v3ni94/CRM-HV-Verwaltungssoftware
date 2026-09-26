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

## Zuordnung CLI (26.09.2026)

`python -m mhvp.imports.zuordnung FILE --tenant <slug> [--user <email>] [--apply]
[--start-date YYYY-MM-DD] [--skip-handed-over]` is the third step after `objektdaten` and
`kontakte`. It reads the same object list, finds units by `source_id` ("<object>/<unit>") and
matches the current owner and tenant by normalised name (case, whitespace, "u." equals "&")
against contacts with `external_ids["immoware24"]` (exported name in
`external_ids["immoware24_name"]`, display name, reordered first and last name as fallback).
Ambiguous names are reported, never guessed. Per match it uses the contact's single member
party (created if missing) and creates an ownership contract (WEG-Verwaltung, WEG mit
SE-Verwaltung; SEV flag when the unit is let) or a tenancy (Mietverwaltung, WEG mit
SE-Verwaltung) with debtor account, a monthly payment (`hoa_fee` or `rent`) and a monthly
schedule, and adds the role eigentuemer or mieter. Start date defaults to 1 January of the
current year and is reported as assumption. An active contract of the same kind with the same
party is left as is; another party or a missing landlord is a conflict. Handbook:
`docs/handbuch/import-zuordnung.md`. Tests: `tests/unit/test_zuordnung_import.py`,
`tests/integration/test_zuordnung_import.py`.
