# ES-01 to ES-11 Erfassungsstandards (entry standards) and data quality report

| Field | Content |
| --- | --- |
| ID | `ES-01` to `ES-11` |
| Title | Uniform entry of properties, contacts and deadlines so that automatic mail and ticket assignment (A-068, A80-01) finds the right records; hard check only for the German postcode, all other rules are non blocking hints plus a read only report |
| Scope | `mhvp.dataquality.rules` (pure rules), `mhvp.dataquality.routers` (`GET /data-quality/report`, `POST /data-quality/check`), property endpoints `POST /properties`, `PUT /properties/{id}`, `PATCH /properties/{id}` (ES-01 via `mhvp.properties.services.check_postcode`); CRM mirror `apps/web-crm/src/lib/entry-standards.ts`, hints in `PropertyCreate`, `PropertyMasterData`, `ContactForm`, `ContactMasterData`, `TicketCreate`, `TicketEdit`, page `/einstellungen/datenqualitaet`. No money effect, no legal rule |
| Source status | Produktschutz (internal standard, never claimed as legal duty). No annex C entry needed. Operator feedback 28.09.2026 (staff request for visible entry standards) |
| Acceptance case | None in annex D. Tests `apps/api/tests/unit/test_entry_standards.py` (every rule with predefined inputs), `apps/api/tests/integration/test_data_quality.py` (ES-01 on create, PATCH and other countries, report entries, read only, tenant separation, 401/403, check endpoint), `apps/web-crm/src/components/common/EntryStandards.test.tsx` (mirror rules, form hints, past date confirmation, report page) |
| Implementation | No migration; reads existing tables `property`, `contact`, `contact_email`, `ticket` under tenant RLS |
| Change reason | Automatic links depend on everyone applying the same standards (property name "Straße Hausnummer, PLZ Ort", contact "Name, Vorname", deadlines with responsible person); staff asked for visible and softly enforced standards |

## Model facts (read before implementing)

- Contacts have separate `first_name` and `last_name`; `display_name` is derived by
  `mhvp.contacts.services.display_name` as "last, first" (title before the first name). "Name,
  Vorname" is therefore a display and sorting convention; the rules check that the parts are in
  the right fields, never the display name.
- Properties have `name`, `street`, `house_number`, `postal_code`, `city`, `country` (default DE).
- Deadlines with a responsible person are ticket working due dates (`ticket.due_on`, responsible
  `ticket.assignee_user_id`). `compliance_deadline` rows are derived from source records and have
  no responsible person; manual calendar entries belong to their owner. ES-09/ES-10 do not apply
  to those.

## Rules

| ID | Entity | Severity | Rule |
| --- | --- | --- | --- |
| ES-01 | property | error (API 422, field `postal_code`, code `postcode_invalid`) | Country DE (or empty): a set postcode has exactly five digits. Checked on create and when postcode or country change, so stored legacy values do not block edits of other fields. Imports keep their values and show up in the report |
| ES-02 | property | warning | Street, house number, postcode and city are set |
| ES-03 | property | warning | Street ends with a number while the house number is empty |
| ES-04 | property | hint | Name matches "Straße Hausnummer, PLZ Ort"; suggestion built from the address |
| ES-05 | contact (person) | warning | No comma in last or first name |
| ES-06 | contact (person) | warning | First name empty and last name has two or more words not starting with a name particle (von, van, de, der, den, zu, zur, vom, di, da, del, la, le, ten, ter, du, dos, af) |
| ES-07 | contact (person) | warning | Name contains a company marker (GmbH, mbH, AG, KG, OHG, GbR, UG, e. V., WEG, Hausverwaltung, Verwaltung, Stadtwerke, Versicherung, Bank, Sparkasse, Gesellschaft, Stiftung, Ltd, Inc) |
| ES-08 | contact | hint (person first name) / warning (company name) | Person without first name only when no other name finding; company without company name |
| ES-09 | deadline | warning, form confirmation | Due date before today (Europe/Berlin) needs an explicit confirmation in the CRM; the API accepts it (advisory check only) |
| ES-10 | deadline | warning | Due date set without responsible person |
| ES-11 | contact | warning (report only) | Active, not blocked contact with role `eigentuemer` or `mieter` without any e-mail address |

## Report

`GET /data-quality/report?limit=200` requires `contacts:read`; the sections `properties` and
`deadlines` additionally need `properties:read` and `tickets:read` and are listed in
`sections_omitted` otherwise. Terminated properties and deleted contacts are excluded; tickets
count when status is new, in_progress or waiting. Each section returns `total` and at most
`limit` items. Hints (severity `hint`) of contacts are not listed. Nothing is changed.

`POST /data-quality/check` with `{"entity": "property"|"contact"|"deadline", "data": {...}}`
requires `contacts:read` plus the entity's read permission and returns the findings without side
effects (422 for an unreadable due date).
