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

