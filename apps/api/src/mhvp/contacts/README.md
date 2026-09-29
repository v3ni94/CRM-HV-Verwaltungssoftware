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

## Bank accounts on an existing contact (CRM screen, addendum 28.09.2026, migration 0225)

Handbook gap "Bankverbindung" (`docs/handbuch/anleitung-bankverbindung.md`). Services in
`services.py`, endpoints in `routers.py`, all under `/contacts/{id}/bank-accounts`:

- `POST .../bank-accounts` (`contacts:update`): `add_bank_account` creates one pending row
  (`requested_by`, event `bank_account.pending` with `source: crm`) without rewriting the
  other accounts; `is_default` clears the previous default; same IBAN on the contact is
  `MHVP-CONT-0003`. The IBAN suffix is appended to `search_text`.
- `POST .../{account}/replace` (`contacts:update`): same service with `replaces`; the new
  version carries `replaces_account_id` and never a default flag. On release
  `decide_bank_account` ends the old row (`valid_to` = new `valid_from` minus one day), hands
  over `is_default` and returns the mandate reference of an active mandate on the old row so
  the router adds the M3-02 note (`_note_mandate_iban_changed`). IBAN history stays.
- `POST .../{account}/end` (`contacts:update`): `end_bank_account` applies `valid_to` at once
  only for a tenant user with `contacts:approve` on a contact that is no legal entity
  (`is_legal_entity_contact`: party member of a `legal_entity` or contact type `manager`);
  otherwise it stores `ContactBankAccountChange` (table `contact_bank_account_change`, RLS,
  kind `end`, one pending per account) and emits `bank_account.end_requested`.
- `POST .../{account}/changes/{change}/approve|reject` (`contacts:approve`):
  `decide_bank_account_change`, four eyes as for the IBAN (`_check_second_person`), events
  `bank_account.end_approved` / `bank_account.end_rejected`. `BankAccountOut.pending_change`
  carries the open change; `replaces_account_id` the replaced row.
- Guards: `MHVP-CONT-0001` (ended or rejected account), `MHVP-CONT-0002` (a replacement or
  end is still pending, or the account itself is pending).
- `PUT /contacts/{id}` with `bank_accounts` still rewrites all rows (ids regenerate); pending
  changes cascade away and `replaces_account_id` is not carried. The CRM form omits
  `bank_accounts` on edit, so this only concerns API clients.
- System role `approver` ("Freigabe") in `mhvp.core.auth.permissions`: `contacts:approve`
  plus read scopes, added to existing tenants by `ensure_system_roles`.
- Tests: `tests/integration/test_contact_bank_accounts_crm.py`.

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

## Creditor contacts from bank transactions (rule M11-08, 29.09.2026)

`mhvp.properties.creditors.create_creditor_from_transaction` creates a company contact with
role `dienstleister` through `services.apply_fields` and `services.write_children`, so the
counterparty IBAN of the transaction starts as a `pending` bank account and follows the
existing four eyes release (M5-01); nothing here approves an IBAN. `GET
/contacts/{id}/creditor-properties` lists the properties a contact is linked to as creditor.
