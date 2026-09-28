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

## P1 additions (Ergänzung CRM 4.2 to 4.4, AP2, 26.09.2026)

Migrations 0148 (property level) and 0149 (building and unit); rule `docs/rules/P1-02`.

* Property level: `PropertyOwner.clearing_account_id`, `power_of_attorney_document_id`,
  `tax_advisor_contact_id` (`POST /properties/{id}/owners`, `PUT .../owners/{oid}/details`);
  `PropertyBankAccount.ledger_account_id`; `PropertyBillingPeriod` (`/billing-periods`, one
  period per kind without overlap, `board_online_audit`); `SubCommunity` (`/sub-communities`,
  WEG only, `Unit.sub_community_id`); `PropertyPortalDocument` (`/portal-documents`, the
  Objektmappe with `visible_for` tenant or owner); `ServiceProviderRelation.customer_number`,
  `exemption_cert_status`, `exemption_cert_valid_until`, `creditor_account_id`.
* Account references (`services.check_ledger_account`) must belong to a ledger of a legal
  entity of the property; they are informational, no posting reads them.
* Building: `address_addition`, full energy certificate (only here, see A-053), `version`
  with `GET`/`PUT /buildings/{id}` (ETag, If-Match, 412 on mismatch).
* Unit: `version` (`PUT /units/{id}` with If-Match), `commission`, `commission_note`,
  `deposit_amount`, `vacancy_vat_option`; `UnitVacancyAllocationValue`
  (`/units/{id}/vacancy-allocation-values`, history, previous open value is closed).
* `MeterChange` (`/meters/{id}/changes`): final reading of the old device, initial reading
  of the new one, optional new number (the meter row keeps its id and readings).
* Tests: `tests/integration/test_properties_p1.py`.


## Inline editing (Ergänzung CRM AP8, ADR 0012, 27.09.2026)

`routers_patch.py`: `PATCH /properties/{id}`, `/buildings/{id}`, `/units/{id}` take only the
changed fields, merge them into the current record, validate with the `PUT` schema, check
`If-Match` against `version` (412) and write the same audit diff as `PUT`. Tests:
`tests/integration/test_patch_p1.py`.

## Catalogues and custom fields (Ergänzung CRM 4.11 and annex B, AP4, 27.09.2026)

* `catalogs.py`: frozen annex B lists (59 catalogues, 416 system entries); `defaults.py`
  seeds them per tenant with `is_system = true` (idempotent on tenant, catalogue, code),
  migration 0152 seeds existing tenants.
* `routers_catalogs.py`: `GET /catalogs` (summary), `GET|POST /catalogs/{catalog}`,
  `PATCH|DELETE /catalogs/{catalog}/{id}`, `GET|POST /custom-fields`,
  `PATCH|DELETE /custom-fields/{id}`. Read `properties:read`, write `tenant_settings:update`.
  System entries: relabel, reorder, deactivate; never delete (409). Code, entity, key and
  field type are immutable. Every change emits `catalog_entry.*` or `custom_field.*` events.
* `CustomFieldDefinition` carries the 4.11 attributes (group, validity per management type
  and contract kind, uniqueness, visible in main view, min, max, default, options,
  description, sort order); `services.check_custom_fields` validates the B.28 types with
  bounds (numbers: value, texts: length) and choice options.
* Operator decision 27.09.2026: catalogues serve new fields. Code enums that mirror an
  annex B list stay unchanged and are only documented: `ManagementType` (B.7),
  `heating_type_code` pattern (B.8), `UnitType` (B.10), `VatOption` (B.12), payment
  intervals and due rules in `contracts` (B.9), ticket status and priority in `tickets`
  (B.24), meeting and resolution enums in `hoa` (B.20 to B.22), delivery channels in
  `communication` (B.14). The matching catalogues exist for display and extension only;
  validation of those fields stays with the enum.
* Handbook: `docs/handbuch/kataloge.md`.

## Termination of the management relationship (operator 27.09.2026)

* `routers_termination.py`: `POST /properties/{id}/terminate` (`properties:update`, status
  onboarding or active) writes a `PropertyTermination` row (who gave notice, notice date, end
  of management, successor manager and owner contacts, notice letter document, note,
  `previous_status`), sets the property to `terminated` with `managed_to` = end of
  management and emits `property.terminated` with an audit diff.
  `POST /properties/{id}/reactivate` is reserved to the superadmin
  (`principal.is_superadmin`, ADR 0011; 403 `MHVP-PROP-0003` otherwise), closes the open
  termination (`reactivated_at`, `reactivated_by_user_id`), restores `previous_status` and
  emits `property.reactivated`. `GET /properties/{id}/termination` returns the open
  termination with resolved contact names and document title.
* `GET /properties` hides `terminated` properties; `include_terminated=true` (or an explicit
  `status=terminated`) is only effective for the superadmin and silently ignored for
  everybody else.
* Migration 0157 (`property_termination`, RLS, one open termination per property via the
  partial unique index `uq_property_termination_open`). Error codes `MHVP-PROP-0001` to
  `0004`. Rule `docs/rules/M4-05-objekt-deaktivieren.md`, handbook
  `docs/handbuch/objekte-einheiten.md` (Verwaltung beenden).


## Stammdaten in der Oberfläche (package C1, 28.09.2026)

* `AllocationKey.expected_total` (migration 0227, `NUMERIC(20,8)`, nullable, no default): the
  operator entered reference sum of a key within the property, for example the total of the
  Miteigentumsanteile per Teilungserklärung. Nothing derives from it; the CRM compares the
  sum of the unit values with it and shows a warning only (`docs/OPEN_QUESTIONS.md` C1-01).
* `PATCH /properties/{id}/allocation-keys/{kid}` (`properties:update`, `AllocationKeyPatch`):
  name, unit of measure, kind, meter type, sort order and `expected_total`; the code is
  immutable (422 when sent). A key of another property answers 404.
* `GET /properties/{id}/allocation-summary?as_of=` (`properties:read`,
  `AllocationSummaryOut`): every key with `total` (sum of the unit values valid at `as_of`,
  default today Europe/Berlin), `expected_total`, `difference` (`total - expected_total`,
  `null` without an expected total), `units_with_value`, `units_without_value`; the units in
  natural order and the single values. Decimals are serialised in plain notation.
* CRM: `BuildingsCreate`, `UnitsCreate` (unit number unique per property checked before
  saving, the API keeps the 409) and `AllocationKeysPanel` on the property page; handbook
  `docs/handbuch/anleitung-stammdaten.md`.
* Tests: `tests/integration/test_c1_allocation_summary.py` (fixed sums 750 and 1000 against
  an expected total of 1000, PATCH validation, 403 caretaker, second tenant 404, 401).
## Master data in the CRM (package C2, 28.09.2026)

`routers_masterdata.py` closes the second Stammdaten gap of the handbook (contact persons,
meters, maintenance items and custom field values only via import or API):

* `PATCH /properties/{id}/contacts/{assignment_id}`: category, period and portal audience of
  a contact person assignment; the contact itself is immutable (end and reassign).
  `GET|POST /properties/{id}/contacts` now return `contact_name`; both write routes emit
  `property.contact_added` or `property.contact_updated` with an audit diff.
* `PATCH /meters/{id}`: every meter field except `number` (unit link checked against the
  property, catalogue `meter_type`, period order); a replaced device stays a Zählerwechsel
  (`POST /meters/{id}/changes`). `MeterOut` carries `property_id`.
* `PATCH /maintenance/{id}`: kind, title, interval, due date, reminder, unit and provider
  relation (both checked against the property). `POST /maintenance/{id}/done` records
  `done_on` (stored as `done_at`, noon Europe/Berlin): with `interval_months` the due date
  becomes `done_on` plus the interval (day clamped to the month end, `services.add_months`)
  and the item stays open; without an interval the item is closed and a second completion
  is refused with 409 `MHVP-PROP-0005`. `MaintenanceOut` carries `done_at` and
  `last_done_on`. Rule `docs/rules/C2-01-wartungszyklus.md`; inspection cycles are operator
  entries (open point STAMM-01).
* Custom field values of a property are written with `PATCH /properties/{id}` and
  `If-Match` (existing, `services.check_custom_fields`); nothing new on the API.
* Permissions: `properties:update` for every write route above, `properties:create` for
  creating meters and maintenance items (unchanged). Tests:
  `tests/integration/test_property_masterdata_c2.py`.
* Web: `apps/web-crm/src/components/properties/ContactPersonsPanel.tsx`, `MetersPanel.tsx`,
  `MaintenancePanel.tsx`, `CustomFieldsPanel.tsx`, `OwnersDetails.tsx` on the property page;
  handbook `docs/handbuch/anleitung-stammdaten.md`.
