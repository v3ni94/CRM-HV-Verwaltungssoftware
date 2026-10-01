# mhvp.portal

Portal specific endpoints and access matrix filters.

* Milestone: M21, M22 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.6, 14.
* Status: M21/M22 portal API implemented. See docs/plans/M21.md. Handover protocols of a
  participant (M30 stage 3) live in `mhvp.handover.portal`; their grants (`scope_type`
  `handover`, `legal_basis` `handover_participant`) are manual and survive `access.sync_grants`.

Portal forms (A56): `forms.py` (templates, submissions, pure validation and rendering) and
`form_routers.py` (management under `/portal-admin/forms`, portal under `/portal/forms`); a
submission creates a ticket of the template's category with own uploads as attachments. The
CRM lists the submissions per template (`GET /portal-admin/forms/{id}/submissions`, A73,
tickets:read) with account, contact name and the created ticket; the values stay on the ticket.
The optional, repeatable `status` query parameter (A74) filters on the ticket status, which is
the processing state of a submission; the CRM offers all, open (new, in progress, waiting) or
one status.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/portal/`. Register models in `mhvp/models.py` for Alembic autogenerate.

Owner pages, read only (A51, section 14 role owner): `owner.py` serves
`GET /portal/resolutions` (announced resolutions of the own GdWE only), `GET /portal/property-contacts`
(manager display name, caretaker and emergency contacts released for owners, no private numbers)
and `GET /portal/hoa-account` (posted lines of the owner's debtor account in the community's
ledger with balance; note "keine Abrechnung, keine Rechtsfolge"; no ledger means a note and no
amounts). Role owner is required (grant `hoa_member_right`), everyone else gets 403.
`owner_meetings.py` adds `GET /portal/meetings` (M25-03, V13): meetings of the own community
after the invitation, with dial-in data only for hybrid or virtual meetings.

Access paths (docs/rules/M21-06.md, D29 to D31): `access.visible_documents` is the single
document filter for portal list and download; `access.document_scope_for_user` applies the same
filter to runs of the AI gateway started on behalf of a portal user; `access.redaction_notes`
marks a released (redacted) version of a receipt, linked to its original with
`entity_type="document"` and role `generated`.

Attachments and appointments (A55, A58, docs/plans/M21.md and M22.md, Nachtrag 26.09.2026):
`_own_uploads` is the single ownership check for portal documents attached to a ticket or a
work order (own portal uploads only, everything else 404); photos are sanitized on upload with
`mhvp.handover.images.sanitize_image`; HEIC/HEIF photos are decoded with pillow-heif and stored as JPEG (`.jpg`, `image/jpeg`), an unreadable HEIC is refused with a hint (A72). Appointment proposals of a provider live in
`mhvp.tickets.models.WorkOrderAppointmentProposal`; only the affected resident accepts one.

Read receipts and notices (A53, A54, docs/rules/M21-06.md rules 5 and 6): `read_receipts.py`
records `opened` and `downloaded` per account as an indication only; the CRM reads them via
`GET /documents/{id}/portal-read-receipts`. `notices.py` holds the Schwarzes Brett model,
`notice_routers.py` the CRM maintenance (`properties/{id}/notices`, `notices/{id}`,
`notices/{id}/end`, permission `properties:update`) and the portal view (`GET /portal/notices`,
`GET /portal/notices/{id}/document`): properties of the active grants, matching audience, valid
on the local day; reading writes nothing.

Schwarzes Brett nach 6.2 (GA02-02, docs/rules/AA09-schwarzes-brett.md, migration 0311):
`PropertyNotice` carries `category` (catalogue `notice_category`), `type` (neutral, info,
warning, danger, CHECK), `audiences` (list of tenant, owner, provider; the old `audience` value
is still accepted on input and echoed on output) and `document_ids` (several attachments, each
released for every audience). `NoticeBoardRead` (`notice_board_read`, unique per notice and
account) is written by `POST /portal/notices/{id}/read`; `GET /notices/{id}/reads` and the
`read_count`/`recipient_count` fields give the CRM the read quota. An indication only, no
delivery. Providers see notices of properties where they hold a work order.


Board audit room (A52, docs/rules/M21-07.md): `board.py` holds the role `board` (grant
`board_audit` per audit engagement, tables `board_access`, `board_audit_note`) and the portal
endpoints under `/portal/board`. The board reads its engagements, positions and the receipts
released through the positions only (`released_document_ids`), and records notes and questions;
the management answers in `mhvp.hoa.board`. No CRM right is granted.

Portal accounts per contact (A86, addendum 26.09.2026): `GET /portal-admin/accounts?contact_id=`
(`contacts:read`, tenant separated by RLS, empty list for an unknown or foreign contact) returns
`PortalAccountOut` rows: e-mail of the platform user, `status` of `PortalAccount` (`invited` until
the invitation is accepted, then `active`), `locked` (platform user inactive or `locked_until` in
the future), `invited_at` (creation), `invitation_expires_at`, `activated_at`, `last_login_at`.
The invitation hash, the token and password data are never returned; the token appears once in
the answer of `POST /portal-admin/accounts` only. The CRM contact page (section Portalzugang)
reads this on mount. Note: `last_login_at` is written by `mhvp.core.auth.service.verify_totp`
and, for password only and trusted device logins, by `record_login` (26.09.2026). Portal
users may enable the optional second factor and remember devices under Sicherheit
(operator 26.09.2026, M2-01).

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `staff_access.py`: portal access for staff members per CRM role matrix (M2-08)
* `mandates.py`: digital SEPA mandate from the portal as a proposal with Textform evidence
  (PDF, time stamp, IP); staff decision in the CRM creates only a contact bank account with
  mandate evidence, never a collecting mandate (M3-02 portal stage, G2). Model
  `SepaMandateProposal` in `models.py`, migration 0174. Address proposals with validity date
  and evidence: `routers.py` (`_address_payload`, `_apply_address`, M21-02).

## Consumption information (rule H03, addendum 29.09.2026)

`consumption_info.py` serves `GET /portal/consumption-info` and `GET /portal/consumption-info/{id}`
for tenants: the stored months of the own units (grants of scope `unit` with role `tenant`,
month inside the contract period). Everything answers 403 until the tenant switch
`consumption_info_enabled` and the operator's `consumption_info_template_verified` are set; the
operator's verification list, data basis ids and missing flags never reach the portal output
(only the estimated marking). Portal notifications of kind `consumption_info` link to `/verbrauch`.

## Dienstleister, Paket P11

`POST /portal/work-orders/{id}/accept` (Annahme ohne Freigabe, Status bleibt), `decline` mit optionaler Begründung, Ereignis und Ticketverlauf je Portalschritt, `invoice_submissions` und `quote_document_id` in der Auftragsantwort, Duplikatprüfung der Rechnungsnummer (409). Regel `docs/rules/P11-tickets-w2.md`.

## Package P13 (Lückenliste 30.09.2026)

Rule `docs/rules/P13-portal-w2.md`, migration 0262.

* `chat.py`: chat as a message channel at the ticket (external `TicketComment`), CRM reply with
  notification, rule based pre-qualification proposal; AI stage only behind `chat_ai_prequalification_enabled`
  and the gateway gate (no provider call yet).
* `features.py`, `management.py`: tenant feature switches (all off by default), portal statistics,
  representatives with power of attorney (read only grants with `legal_basis = representation`
  derived in `access.sync_grants`), consent bound read only support view with access log.
* `owner_extra.py`: owner tickets released for owners, resolved payments with validity and payee,
  consumption information for self used units.
* `forms.py`, `form_routers.py`: 14 element types, delivery as ticket or e-mail.
* `routers.py`: `GET /portal/documents` with `is_new`, `last_opened_at`, `context`; `location`
  on `POST /portal/tickets`; `GET /portal/me` with `features` and `representations`.

## Welle 3 (Q10)

- `GET /portal/documents?q=&sort=` (Suche in Titel und Dateiname, Sortierung created, title, filename) und `POST /portal/documents/bundle` (ZIP mit INDEX.csv, max. 100 Belege, gleiche Sichtbarkeitsprüfung, Abrufe als Indiz protokolliert).
- `GET /portal/me` liefert zusätzlich `portal_roles` (abgeleitet über `core/auth/portal_roles.py`).
- Tickets: `external_comments` und `external_attachments` werden im Portal durchgesetzt (Standard open, Migration 0279, Annahme A-Q10-01).

- Paket Q05 (Welle 3): `GET /portal-admin/representations` liefert zusätzlich `representative_contact_id` und `representative_email`; Vollmachten im CRM am Kontakt (Liste, Anlage mit Dokument, Widerruf). Regel: `docs/rules/Q05-crm-oberflaechen.md`.
- `GET /portal/owner/statements` und `.../statements/{id}/units/{unit_id}/pdf` (M24-03, Status issued bis locked, G4), `GET /portal/owner/allocation-properties` und `/rental-income`, `own_share` in `/portal/owner/payment-resolutions`.
- `POST /portal/work-orders/{id}/einvoice` (M22-01, XML, Vorschlag über `mhvp.receipts.einvoice`).
- `GET /portal/board/engagements/{id}/positions/{item_id}/context` (M25-04, lesend).
- `GET /portal/documents?q&sort` (R05) filters and sorts in the database via `access.visible_documents(q=, sort=)`; the matrix still decides what is visible. The owner statement PDF path is covered by `tests/integration/test_r05_positive_paths.py`.

- R10 (B20, B26): Mandanteneinstellung `portal_second_factor` (`account_choice` Standard, `required`) steuert den E-Mail-Code der Magic-Link-Anmeldung (`magic_link.consume_link`). Das öffentliche Branding liefert `platform` (`GET /tenant/branding`, `/tenant/branding/logo/{variant}`, Header `X-Portal-Host`); das Portal wendet es über `apps/web-portal/src/lib/branding.ts` an. Regel: `docs/rules/R10.md`.

- `GET /portal/owner/takeover-checklist` (R03, M7-01): Stand der Objektübernahme der eigenen Objekte (Bezeichnung, Status, Fälligkeit), lesend, ohne Notizen, Dokumente und Tickets; Mieter und Dienstleister erhalten 403. Anzeige auf der Seite Eigentum.

## Objektzuordnung der Portalverwaltung (T14, R08-01)

`portal/property_scope.py`: ein Kontakt ist für ein eingeschränktes Mitglied sichtbar, wenn eine seiner Parteien einen Vertrag auf einem zugeordneten Objekt hat. `GET /portal-admin/accounts` liefert sonst eine leere Liste, `POST /portal-admin/accounts` 404, Pfade mit `{account_id}` (Router-Abhängigkeit `portal_admin_guard` an beiden `admin` Routern) 404. Nicht angeschlossen: Änderungsvorschläge, Vollmachten, Mandatsvorschläge.

### Rechnungseinreichung, Übernahme von Netto, USt-Satz und IBAN (U09, M22-02)

`POST /portal/work-orders/{id}/invoice` nimmt optional `net`, `vat_rate` und `iban` an (Plausibilität, 422). Bei Annahme legt `_apply_invoice_submission` den Belegentwurf mit Netto, USt und IBAN-Kandidat an und schreibt Befunde: IBAN-Abgleich mit dem Kreditorenstamm (Abweichung kennzeichnet nur) und Duplikatprüfung gegen das Rechnungsbuch (Aussteller plus Nummer oder Datum plus Brutto). Regel `docs/rules/U09-invoice-submission.md`.

## Vertretung im Portal (U05, M21-05)

`features.own_representations` liefert die Vollmachten eines Kontos mit Zustand (`rep_state`: active, pending, expired, revoked), Namen des Vertretenen und Resttagen; `GET /portal/representations` gibt sie dem Portal. `/portal/me` ergänzt `portal_roles` um `representative`, solange eine Vollmacht gültig ist; Verträge aus Vollmachten zählen nicht als eigenes Eigentum. Der Zugriffsverlust nach Ablauf folgt aus der Datumsprüfung in `access.grants`. Regel: `docs/rules/M21-05-vertretung.md`.

## Erneute Einladung (U12, T13-01)

`POST /portal-admin/accounts` stellt für einen Kontakt mit abgelaufener, nie angenommener Einladung (Status invited, Ablauf erreicht) denselben Zugang erneut aus: neues Token, Ablauf auf INVITE_DAYS zurückgesetzt, Rechte neu abgeleitet, Ereignis `portal_account.invitation_reissued`, Antwort mit `reissued: true`. Aktives, gesperrtes oder noch gültig eingeladenes Konto bleibt 409.

## Objektzuordnung der Mandatsvorschläge (Y01)

Mandatsvorschläge der Portalverwaltung folgen dem Objekt ihres Vertrags: Liste gefiltert,
Entscheidung außerhalb der Zuordnung 404.

## Portal account fields (AA08, GA02-07)

`portal_account.roles` (from the access grants), `invited_at`, status CHECK with not_invited,
invited, active, locked, expired, revoked (migration 0310). `GET /portal-admin/accounts` returns
`roles` and the derived status (`expired`, `locked`); see `docs/rules/AA08-abrechnungszeitraum-status.md`.

## Status model of the portal account (AB08, GA02-07)

The status of 6.2 is stored (`mhvp.portal.status`), the check constraint of migration 0310 is
authoritative. Beat job `mhvp.portal.sync_account_status` (every 15 minutes, `portal/tasks.py`)
persists `expired` and `locked`/`active`; it is idempotent and never touches `revoked`.

| From | To | Trigger |
| --- | --- | --- |
| new | not_invited | create with `send_invitation=false` |
| new | invited | create with invitation |
| not_invited | invited | invitation by mail or letter |
| invited | active | acceptance (`activated_at`) |
| invited | expired | job, `invitation_expires_at` passed |
| expired | invited | reissued invitation (mail or letter) |
| active | locked | job, platform user locked or inactive |
| locked | active | job, lock lapsed (account was activated) |
| any | revoked | staff access withdrawn (`revoke_staff_portal_access`), final |

`last_login_at` lives on the platform user and is written on every successful login.
Rule: `docs/rules/AA08-abrechnungszeitraum-status.md`.

## Access grants by document class, provider information (AA14)

* `AccessGrant.scope_type = "document_class"` (migration 0316, GA03-05): `scope_id` is the legal
  entity, `document_class` the class; `access._document_class_ids` releases documents linked to
  the entity whose retention profile class matches and whose `visibility` contains the grant
  role. Endpoints `GET/POST /portal-admin/accounts/{id}/document-class-grants`; legal basis
  `document_class_grant` survives `sync_grants`.
* `provider_info.py` (GA11-04): `GET /portal/provider/framework-contracts` (own service
  contracts, no internal notes), `GET /portal/provider/availability`, management side
  `GET/POST/DELETE /portal-admin/provider-availability`; table `provider_availability`.
* `forms.py` knows 20 element types (GA11-02), see rule AA14 and A-AA14-01.
* Access path protocol: `tests/integration/test_aa14_access_paths.py` (list, detail, download,
  bundle, search, export, CRM API, AI scope and AI input).

## Sprache am Portalkonto (GA11-01, AB12)

* `portal_account.locale` (migration 0331, nullable). `PATCH /portal/me/locale` speichert `de` oder `en` (`PORTAL_LOCALES`, sonst 422, `null` löscht); `GET /portal/me` liefert `locale`. Das Portal übernimmt die Sprache bei der Anmeldung in den Cookie (`apps/web-portal/src/lib/locale-sync.ts`); der Cookie hat Vorrang für nicht angemeldete Besucher.
* CRM: Seite `/einstellungen/dienstleister-portal` (Zeitfenster und Klassenfreigaben, bestehende API `portal-admin/provider-availability` und `document-class-grants`).
* Offen: AB12-01 (Gate G5 für Klassenfreigaben, nichts geändert).

### AC04: Rechtsträgerauswahl für die Dienstleister-Seite

`GET /portal-admin/legal-entities` (Recht `tenant_settings:read`, nur `id` und `name`, RLS auf den eigenen Mandanten, unbekannte Query-Parameter 422) ersetzt für die CRM-Seite `/einstellungen/dienstleister-portal` den Pfad `/tenant/legal-entities`, der `members:read` verlangt. Tests: `tests/integration/test_ab12_portal_locale.py::test_ac04_legal_entity_choices_need_only_settings_read`.
