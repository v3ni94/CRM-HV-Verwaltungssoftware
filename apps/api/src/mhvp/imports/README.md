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

## Kontaktereignisse der Listenimporte (26.09.2026, A87)

`kontakte.apply_prepared` emits `contact.created` (payload `kind`, `source =
"import.kontakte"`) for every created contact and `contact.updated` (payload `fields:
["roles"]`, audit diff old/new, version bump) when a second list adds a role;
`zuordnung.apply_rows` emits one `contact.updated` (`source = "import.zuordnung"`, counted as
`kontakte_aktualisiert`) per contact whose roles changed through the assigned contracts or the
derived roles. The helpers live in `kontakte.py` (`emit_contact_created`, `emit_roles_updated`).
The events are outbox rows in the same transaction as the import; a test run (CLI without
`--apply`, API `mode=preview`) is rolled back and leaves no event, so no after-commit hook is
needed. The webhook dispatcher (`mhvp.core.webhooks.enqueue_deliveries`) and the rule engine
read them like the events of the manual API. Test:
`tests/integration/test_a87_import_contact_events.py`.

The staging import (`services._apply_contact`, report type `contacts`) emits `contact.created`
(`source = "import.staging"`) for every created contact through `mhvp.core.events.emit` with
the same payload (`kontakte` imports this module, so its helper is not imported back). An
existing contact is never changed by this path (`unchanged` or `conflict`), so it emits no
`contact.updated`. The test run (`POST /files/{id}/test-run`) runs inside a savepoint the
router rolls back, so it leaves no event. The objektakte import (`mhvp.objektakte.
objektakte_import.apply_tables`, manual upload and differential run of `tasks.py`) emits
`contact.created` and, when mapped fields of an existing contact differ from the export,
`contact.updated` with the changed field names, audit diff and version bump
(`source = "import.objektakte"`); preview mode and a failed (rolled back) run leave no event.
Test: `tests/integration/test_a87_import_contact_events_apply.py`.
## Abgleichbericht Parallelbetrieb (26.09.2026, A68)

`reconciliation.py` compares the staged rows of the report types `journal` and
`bank_transactions` per property with the platform (account balances, open receivables and
payables, reserve, bank balance, incoming payments) and stores the result as `import_run` with
`source = immoware24:reconciliation`; `reconciliation_routers.py` serves
`/api/v1/imports/reconciliation-reports` (list, create, JSON, CSV, column configuration);
`tasks.py` runs it daily (`mhvp.imports.reconciliation_all`, time `MHVP_IMPORT_RECONCILIATION_TIME`,
default 05:30). Read and compare only, nothing is posted. Column defaults are an assumption
(docs/ASSUMPTIONS.md A-047), configurable per tenant. Handbook:
`docs/handbuch/import-abgleichbericht.md`. Tests: `tests/unit/test_m8_reconciliation_report.py`,
`tests/integration/test_m8_reconciliation.py`.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `list_import_routers.py`: Immoware24 list imports over the API (`/api/v1/imports/immoware24/lists`); router registered in `main.py`

## Multi person names (addendum 26.09.2026, M8-04)

`kontakte.detect_multi_person` splits "Nachname, V1 & V2", "V1 und V2 Nachname", "Eheleute
...", "Herr und Frau ..." into persons; `apply_prepared` creates one contact per person and one
party named as exported (members carry `external_ids["immoware24_member"]`). Unclear names
(Erbengemeinschaft, missing first names, two family names) stay one contact and are reported
under `pruefung`. `zuordnung.import_party` finds the joint party of such members. Rule entry
`docs/rules/M8-04-mehrpersonen-bevollmaechtigte.md`.

## Vollimport mit Stichtag (27.09.2026, M8-01, M8-02, V9)

`vollimport.py` runs all exports of one cut-off date in one go: `precheck` (encoding,
delimiter, header comparison against `EXPORT_KINDS`, row count, duplicate keys, missing
required fields, SHA-256) without database access, `run_full` with `mode` preview (the router
rolls the savepoint back), apply (import via `objektdaten.apply_prepared`,
`kontakte.apply_prepared`, `adressen.apply_address_list`, then reconciliation) or abgleich
(comparison only). The reconciliation compares target (file rows) with actual (platform
records) per entity by Immoware24 object number, unit source id and contact id and lists
missing, duplicate and deviating records; `update_existing` lets a repeated import update
object name, unit label and location (never the management type). A balance list becomes
opening balance proposals per contract as a draft only (G1 closed, nothing posted).
`vollimport_vertraege.py` adds the export kinds `mietvertraege` and `eigentuemervertraege`
(column labels of the staging target fields): party via contact id, unit via object and unit
number, key Immoware24 contract number (`import_external_key`, migration 0204) or
object/unit/kind/start, rent and Hausgeld as contract payments with a monthly schedule
(nothing posted, contracts `pending` approval, source `immoware24:vollimport`), domain rules
of `contracts.services.creditor_entity` (no tenancy in pure HOA, SEV derived, landlord of
rental objects from ownership rows). Its reconciliation adds per object counts and target
sums (`je_objekt`). Opening balance entries are `zugeordnet` when exactly one contract
matches at the cut-off date.
`vollimport_routers.py` serves `/api/v1/imports/immoware24/vollimport` (export kinds,
pre-check, run, list, JSON, PDF draft); stored runs live in `import_full_run` (migration 0191).
Handbook: `docs/handbuch/import-abgleichbericht.md`, section Vollimport. Tests:
`tests/unit/test_vollimport.py`, `tests/integration/test_vollimport.py` (synthetic 67 objects
and 869 units from `tests/synthetic_immoware.py`).
