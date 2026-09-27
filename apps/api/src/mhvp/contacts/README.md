# mhvp.contacts

Contacts, addresses, channels, identifiers, bank accounts, parties, consents, portal accounts.

* Milestone: M3 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.1.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/contacts/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `validation.py`: normalisation and validation of contact data (IBAN per ISO 13616, phone numbers E.164)

## Performance (Review 26.09.2026)

`services.summaries` loads primary email, phone, city, tags and types of a page in one
UNION ALL statement; `GET /parties` loads the members of all parties in one query
(`_parties_out`). Index `contact(tenant_id, display_name)` for the list ordering (migration
0127). Measurements in `docs/reviews/2026-09-26-performance.md`.

## Four eyes release of IBANs (M5-01, addendum 26.09.2026)

`decide_bank_account` stores the rejection reason on the row (`rejected_reason`, migration
0132) in addition to the audit event. `bank_account_out` builds `BankAccountOut` and mirrors
`decided_by` and `decided_at` of a rejected row as `rejected_by` and `rejected_at`.
`summaries` marks contacts with at least one pending bank account (`iban_pending`) inside the
existing UNION ALL statement, so the contacts list shows "IBAN wartet auf Freigabe" without a
query per contact. Rule addendum in `docs/rules/M19-05.md`.

## Authorised representatives and delivery rule (addendum 26.09.2026)

`ContactRelation` of kind `representative` carries `delivery_mode` (`both`, default;
`representative_only`; `owner_only`, migration 0140). `recipients.resolve_recipients` is the
single place that applies the rule; `mhvp.communication.dispatch` (serial dispatch),
`mhvp.documents.routers.serial_letter` and `mhvp.hoa.meetings.invitation_recipients` call it.
Endpoints `GET/PATCH/DELETE /contacts/{id}/contact-relations` (`contacts:read` /
`contacts:update`, audited with old and new values). Rule entry
`docs/rules/M8-04-mehrpersonen-bevollmaechtigte.md`.

## Fields of section 4.1 (Masterprompt Ergänzung 27.09.2026, AP1, migration 0147)

`Contact.letter_salutation`, `blocked_at`, `retention_profile_id` (FK `retention_profile`) and
`delete_after`; `ContactAddress.state`; `ContactPhone.country_code`, `area_code`, `note`;
`ContactDate` (table `contact_date`, kinds `birthday`, `death`, `wedding`, `foundation`,
`other`, rewritten with the other children on PUT); `ContactBankAccount.kind`
(`ContactBankAccountKind`, catalogue B.4, DB enum `contact_bank_account_kind`, distinct from
the property enum `bank_account_kind`), `is_default`, `bank_contact_id`; `ContactNote.title`,
`follow_up_on`. Partial unique indexes `ux_contact_email_portal_login` and
`ux_contact_bank_account_default` enforce exactly one portal login address and one default
account per contact; `ContactIn._single_flags` rejects the input earlier with 422.
`services.apply_fields` sets `blocked_at` when a block starts and clears it when it is lifted.
`services.apply_retention` accepts only a released retention profile of the tenant and computes
`delete_after` with `services.delete_after` (start: block date, else the day of assignment;
`end_of_year_*` rules round to 31.12.; permanent profiles yield no date). Operator decision
26.09.2026: the date is a reservation shown as due, the deletion itself stays the manual four
eyes `DELETE /contacts/{id}`; there is no automatic deletion job. `GET /contacts?blocked=true`
is the block list. The approval logic of bank accounts is unchanged. Rule entry
`docs/rules/P1-01-kontakt-sperre-loeschdatum.md`, tests
`tests/integration/test_contacts_p1.py`.

## Inline editing (Ergänzung CRM AP8, ADR 0012, 27.09.2026)

`PATCH /contacts/{id}` (`ContactPatch`) changes master data fields only; the merged record is
validated as `ContactIn`, `If-Match` against `version`, audit diff as on `PUT`. Addresses,
phones, e-mails, identifiers, dates, bank accounts, types, roles and tags stay on `PUT`.
