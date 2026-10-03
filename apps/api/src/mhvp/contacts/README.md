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

## P16 follow-up maintenance (wave 2)

`routers_p16.py`: `PATCH/DELETE /parties/{id}` (name, complete member list with roles and shares;
delete only without references, else 409), `PATCH/DELETE /contacts/{id}/notes/{note_id}`, tag
administration `GET /contact-tags`, `PATCH/DELETE /contact-tags/{id}`, `POST /contact-tags/{id}/merge`.
Every change writes an audit event. Not done: contact merge (P16-01), portal status (P16-02).
Rule: `docs/rules/P16-stammdaten-pflege.md`.

Paket Q05 (Welle 3): CRM-Oberflächen für Parteien (`PartiesPanel`, Reiter Beziehungen), Tag-Verwaltung (Einstellungen, Kontakt-Tags) und Portalstatus am Kontakt (`PortalStatusBadge`, lesend aus `GET /portal-admin/accounts`). Regel: `docs/rules/Q05-crm-oberflaechen.md`.

## Kontakt-Merge (Q04, M3-03)

`merge.py`, `routers_merge.py`: `GET/POST /contact-merges`, `GET /contact-merges/{id}`, `POST /contact-merges/{id}/reject|execute`. Vorschlag (`contacts:update`), Ausführung und Ablehnung (`contacts:approve`, zweite Person). Verweise werden über ein Registry aus den Fremdschlüsseln auf `contact.id` umgehängt (plus `document_link`), die Quelle bleibt als zusammengeführt erhalten (`merged_into_id`, `merged_at`, `deleted_at`). Regel: `docs/rules/M3-03-kontakt-merge.md`. UI: `/kontakte/zusammenfuehrung`.

## Consent checks per purpose (AC06, GA02-06)

`consent_rules` evaluates the consent kinds of 6.1 (rule `docs/rules/AC06-einwilligungen.md`):
`email_delivery_decision` (dispatch falls back to post), `contacts_with_consent` (marketing
filter of advertising serial dispatch), `portal_terms_decision` (portal activation and access
once `portal_terms_version` is published) and `data_sharing_decision` (check before a transfer
to a service provider; not yet wired in tickets and automation, AC06-02). Tenant switches in
`tenant_settings.sources.consent_policy`, API `GET/PUT /api/v1/consent-policy`.

## Access export with review (AC07, GA08-06)

`access_export.py`: data subject access export built from an explicit field allowlist per
entity plus a second filter that drops secret, hash and fingerprint keys. Other persons appear
only with their role (relations, parties, deviating account holder). Workflow prepared,
reviewed, released (review and release by a person other than the preparer), downloaded;
journaled as `contact.access_export.*` domain events (no own table, migration 0340 noop). The
prepared event stores the content hash only; review, release and download rebuild the export
and refuse with MHVP-CONT-0032 when the data changed. The old `GET /contacts/{id}/export`
returns 409. Rule: `docs/rules/AC07-auskunft-loeschung.md`; open: AC07-01.

## Legal basis per processing and objection (AE34, AC06-01 to AC06-03)

`consent_rules.py` keeps a register `tenant_settings.sources["consent_legal_basis"]` (separate
from `consent_policy`) with the legal basis per purpose (`email_delivery`, `data_sharing`,
`marketing`, `portal_terms`): `consent` (default), `contract`, `legitimate_interest`, each other
basis with a justification. API: `GET /consent-legal-basis`, `PUT` and `DELETE
/consent-legal-basis/{purpose}` (change needs `contacts:approve`, events
`consent_legal_basis.updated` and `.reset`). `ConsentPolicy.basis_for(purpose)` is the single
read path: register entry, else the legacy `consent_or_contract` switch (counts as `contract`),
else `consent`. The decisions (`email_delivery_decision`, `data_sharing_decision`,
`marketing_permitted`) follow it; under `legitimate_interest` an objection record
(`POST /contacts/{id}/objections`, `consent.record_type = objection`, never a consent) or a
revoked consent of the same kind blocks the contact. Migration 0390 adds `record_type`,
`text_version` and `ip_hash` (keyed hash of the client address) to `consent`. Rule:
`docs/rules/AE34-01.md`; open: AC06-01 to AC06-03, AE34-01 to AE34-03.

## Access export scope as tenant switches (AE33, AC07-01)

`contact_access_export_setting` (migration 0389, one row per tenant, no row means the defaults):
`third_party_scope` `none` (default, other persons by role only) or `names` (name and role, never
address, contact data, identifiers or bank data), `include_internal_notes` (default off; note
field and contact notes without author). `GET` and `PUT /contact-access-export-settings`
(`tenant_settings:read` and `tenant_settings:update`, event
`contact_access_export_setting.updated`). The scope is frozen into the prepared event
(`options`); review, release and download rebuild exactly that content, so the hash check holds
when the switches change later. Events without `options` count as the defaults. Rule:
`docs/rules/AE33-papierkorb-auskunft.md`; open: AC07-01.

## Access export sources (AJ13, GAI-506)

`contact-access-export-settings` carries three further switches `include_tickets`,
`include_communication`, `include_documents` (stored in `tenant_settings.sources`
`access_export_sources`, default off, omitted in PUT keeps the stored value). Off: count only.

## Address list and cut off date (AM14, GAJ-610)

`GET /contacts/{contact_id}/addresses` returns the current addresses (`history_available`
false). The parameter `as_of` is refused with 422 `MHVP-CONT-0034` until the address history
(valid_to, open question AM14-01, schema draft there) is decided: returning today's address for
a past date would be a wrong delivery proof. A contact merge moves the source addresses, phones
and emails to the target; moved rows lose `is_primary` when the target already has a primary
row, so the target keeps exactly one.
