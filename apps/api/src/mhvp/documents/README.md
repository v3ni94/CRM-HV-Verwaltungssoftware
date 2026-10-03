# mhvp.documents

Documents, links, categories, retention profiles, DMS mirrors (Paperless-ngx, Google Drive),
letter templates, PDF letters and serial letters.

* Milestone: M6, plan and decisions in `docs/plans/M6.md`.
* Specification: docs/MASTER-PROMPT.md 6.7, 6.9.5, 7.11, 11.
* Files: `models.py`, `schemas.py`, `routers.py`, `services.py` (store, link, retention,
  letter context), `blobs.py` (S3 originals), `text.py` (text layer, type checks), `dms.py`
  (store protocol and adapters), `tasks.py` (mirror job), `letters.py` (placeholders, DIN 5008
  PDF), `defaults.py` (categories, free letter), `letter_records.py` (letters on the letterhead
  filed as documents with ticket link and dispatch record, M12 gaps 29.09.2026: used by the
  Nachforderungsschreiben and the rent increase letter; nothing is sent, a mail draft leaves
  only through the mail approval).
* Tests: `apps/api/tests/integration/test_m6_documents.py`, `apps/api/tests/unit/test_m6_documents.py`.
* Locks: deletion only with a released retention profile; nothing is sent from here.
* Retention: standard profiles per tenant are seeded as drafts by `defaults.py` (operator
  decision M6-04, 26.09.2026, rule `docs/rules/M6-04-aufbewahrungsprofile.md`); a draft never
  unlocks deletion, release needs `tenant_settings:update`, four eyes and is audited;
  `permanent` profiles (WEG minutes, resolutions) never unlock deletion.
* Storage errors: `blobs.BlobStore` answers a missing configuration (`MHVP_S3_*`) or an
  unreachable store with `MHVP-DOC-0007` (503, `application/problem+json`, ADR 0004); the
  underlying boto error is logged, the upload aborts before an index row exists
  (`services.store_document` writes the object first, then the row).
* Content check (`text.sniff_matches`, called by `services.check_upload` for every upload
  path: CRM, portal, mail attachments, handover, letting, metering): PDF, JPEG, PNG, TIFF,
  ZIP and OOXML by magic bytes; HEIC/HEIF (A72) only with an ISO BMFF `ftyp` box whose major
  or compatible brand is a HEIF brand (`heic`, `heix`, `heim`, `heis`, `hevc`, `hevx`,
  `hevm`, `hevs`, `mif1`, `msf1`), so a renamed executable, an MP4 or an AVIF declared as
  `image/heic` is refused with `MHVP-DOC-0003` (422). Portal photos are additionally decoded
  and re-encoded by `mhvp.handover.images.sanitize_image`.
* Malware scan (operator decision 27.09.2026, `scan.py`): `store_document` streams every
  file to clamd (`INSTREAM`, TCP) before the blob is written, except platform generated PDFs
  (`DocumentSource.GENERATED`) or `scan_for_malware=False`. A finding answers
  `MHVP-DOC-0008` (422) and is journaled as `document.malware_rejected` with the signature in
  an own transaction; an unreachable scanner answers `MHVP-DOC-0009` (503) in mode `enforce`
  and journals `document.scan_skipped` in mode `warn`. Settings `MHVP_CLAMAV_*`, readiness
  check `clamav`, runbook `docs/runbooks/virenscan.md`.
* Drafts: an automatically generated letter (A83, `mhvp.automation`) is marked with
  `Document.source_meta["is_draft"] = true`; `GET /documents?is_draft=true|false` filters on
  that marker (missing key counts as not a draft) and `DocumentHit.is_draft` exposes it.

## M31: Paperless-Dokumente in Ticket- und Objektansicht

Read-only search against the already-mirrored Paperless-ngx instance, for the ticket and
property detail screens in the CRM frontend.

* `paperless_search.py`: `PaperlessSearch` (10 s timeout httpx client), `list_by_object_number`
  (custom_field_query on the tenant's configured field id), `list_by_ticket` (full text search,
  no dedicated ticket-number field exists in Paperless), `fetch_file` (download/preview/thumb).
* Field ids are configured per tenant on `DmsConnection.options` as the string keys
  `object_field_id` and `company_field_id` (existing free-form JSONB column, no new columns or
  migration needed for this). A common value is 7 respectively 5 (see the Immoware Hub
  reference), never hard-coded here; without a configured `object_field_id` the property search
  returns an empty page instead of guessing.
* Endpoints (`documents:read`): `GET /api/v1/properties/{id}/dms-documents`,
  `GET /api/v1/tickets/{id}/dms-documents` (ticket's property, if any, plus a full text search on
  the ticket number, results deduplicated by Paperless document id), and
  `GET /api/v1/dms-documents/{id}/file?kind=download|preview|thumb`, which proxies the file
  through the API so the Paperless token never reaches the browser. The list endpoints'
  `preview_url`/`download_url` point at this proxy.
* Errors: `MHVP-DOC-0005` (502, no enabled Paperless connection) and `MHVP-DOC-0006` (503,
  Paperless unreachable or erroring); messages never contain the token.
* Tests: `tests/unit/test_documents_paperless_search.py` (MockTransport, no DB needed). The
  router endpoints themselves need Postgres fixtures and are not yet covered by an integration
  test in this environment (no local Postgres to run `RefreshDatabase`-style fixtures against).

## Hub 7.2: Paperless object search and company filter

Takes over the Immoware Hub logic (`docs/integrations/immoware-hub.md` sections 5 and 7.2),
read only. `object_number_matches` implements the object rule (exactly `<number>` or starting
with `<number>, `, so `523` never hits `5230` or `1523`); it is sent as `custom_field_query` and
re-applied to results that carry `custom_fields`. The company filter compares the option id of
the select field `company_field_id`; the mapping option id to company is the text option
`company_options` (`Option-ID=Company` per line, empty by default, validated on
`PUT /dms-connections/paperless`). Endpoints: `GET /dms-documents` (object number, company, full
text; at least one criterion; 403 for legal-entity scoped memberships),
`GET /dms-documents/companies`, query parameter `company` on the property and ticket lists.
Unknown company or unconfigured field: 422. Assumption A-050.

## A30: Paperless post-consume webhook

`paperless_webhook.py`: `POST /documents/webhooks/paperless[/{tenant}]`, no login; HMAC-SHA256
with the tenant's `DmsConnection.webhook_secret` over `"<timestamp>." + raw body`
(`X-MHVP-Timestamp`, `X-MHVP-Signature: sha256=<hex>`, `X-MHVP-Tenant` slug or id), 300 s
window, replay lock in Redis (409 `MHVP-HOOK-0003`), invalid or missing signature 401
(`MHVP-HOOK-0002`). Indexes the document once through `PaperlessSearch.fetch_file`
(`Document.source_system="paperless"`, `source_id`=Paperless id, mirror marked done) and, only
with `DmsConnection.auto_receipt_intake` (default off, M14-05), queues a receipt draft via the
existing receipts functions (`mhvp.documents.paperless_receipt_intake`). Migration 0098.
Tests: `tests/integration/test_m14_paperless_webhook.py`.

## A43: Spiegelkopien nach der Löschung (6.9.5, M6-03, Betreiberentscheidung 26.09.2026)

`mirror_deletion.py`. After the platform deletion (`DELETE /documents/{id}`, only with a
released, expired retention profile and no hold; the block of mirrored documents is lifted) one
step row `document_mirror_deletion` and one event `document.mirror_delete_requested` per mirror
are written in the deleting transaction; the Celery task `mhvp.documents.delete_mirror` (queue
`io`, retry ladder 1 min to 24 h, six attempts) performs the steps afterwards:

* Google Drive (`action=delete`): permanent delete through `GoogleDriveStore.delete`; when
  Drive refuses it (for example a shared drive without delete right) the copy is moved to
  the trash (`GoogleDriveStore.trash`) and the journal says so (`result` `deleted`,
  `trashed` or `already_gone`, `note` with the reason for the fallback). Event
  `document.mirror_deleted`.
* Paperless-ngx (`action=tag`): the document is kept and receives the tag `gelöscht`
  (`PaperlessStore.add_tag`, tag created with the tenant token when missing, assigned once);
  `result` `tagged` or `already_gone`. Event `document.mirror_marked_deleted`.
* Failure: `document.mirror_delete_failed` with attempt and error, the step stays `open`
  with `attempts` and `last_error`; nothing is dropped silently (D46).

The deletion of a document is `open` ("offen") until every step is `done`:
`GET /documents/deletions[?status=open|done]` lists deletions with their steps,
`POST /documents/deletions/{document_id}/retry` re-queues the open steps (permission
`documents:delete`). The step table has no foreign key to `document` (the row is gone) and
RLS like every tenant table (migration 0143). The restore replay (A44) deletes mirrored
documents the same way and queues their steps after each commit. Rule
`docs/rules/M6-03-loeschung-spiegel.md`, tests `tests/integration/test_m6_mirror_deletion.py`
and `tests/unit/test_documents_mirror_deletion_clients.py` (MockTransport, no network).

## A44: Löschjournal und Wiederanwendung nach Restore (D47, M9-03)

`deletion_journal.py` derives the journal from the append only domain events
(`document.deleted`, `document.deletion_refused`, `document.hold_set`, `document.hold_cleared`)
without touching the store. CLIs: `python -m mhvp.documents.export_deletions --since <ISO> --out
<file>` before a restore, `python -m mhvp.documents.replay_deletions --journal <file> [--apply]
[--report <file>]` afterwards (dry run by default). The replay deletes a document only when it
exists, its hash equals the hash recorded at the original deletion, no deletion hold and no
other blocker (`services.deletion_blocker`) applies; mirrored documents are deleted as well and
their mirror steps (A43) are queued after the commit; every deletion and refusal is emitted
again with `replay: true`. Procedure: `docs/runbooks/backup.md`;
test: `tests/integration/test_m9_restore_replay.py`.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `intake_routers.py`: document inbox proposals (A42): list, accept, reject
* `mirror_deletion.py`: logged mirror steps after a deletion, Drive delete and Paperless tag "gelöscht" (A43, 6.9.5, M6-03, section above)
* `property_filing.py`: direct filing of one document into a property's Drive year folder (M11-finapi stage 3)
* `retention.py` (27.09.2026, M6-04, migration 0175): period computation per start rule, category
  to profile mapping (`document_category.retention_profile_id`, `POST /retention-profiles/apply`),
  hold per ticket (`/tickets/{id}/retention-hold`), the monthly deletion proposal job
  `mhvp.documents.deletion_proposals` (`deletion_proposal`, `deletion_proposal_item` as the
  deletion log) with four eyes approval (`/approve`, not the initiator) and separate execution
  (`/execute`, not the approver), re-check of every document on the day of execution, and
  `delete_now` shared with `DELETE /documents/{id}` (mirror steps per M6-03). Legal status of the
  periods stays "zu prüfen durch Steuerberater" (rule `docs/rules/M6-04-aufbewahrungsprofile.md`,
  assumption A-058). CRM: `/einstellungen/aufbewahrung`, `/dokumente/loeschvorschlaege`.

## Performance (Review 26.09.2026)

`GET /documents/intake-proposals` loads the documents of a page in one IN query. Indexes
`document(tenant_id, created_at)` and `ai_proposal(tenant_id, entity_type, decision,
created_at)` (migration 0127). Measurements in `docs/reviews/2026-09-26-performance.md`.

## Package F (28.09.2026): Standardkategorien 04/05, Ordnerstruktur, Upload mit Verknüpfungen

* `defaults.CATEGORIES` enthält zusätzlich `tenant_file` (Mieterakte, `04_Mieterakte`) und
  `owner_file` (Eigentümerakte, `05_Eigentümerakte`), am Ende der Liste, damit die Sortierung
  bestehender Mandanten unverändert bleibt. Neue Mandanten erhalten sie bei der
  Bereitstellung; bestehende über `POST /document-categories/ensure-defaults`
  (`tenant_settings:update`, idempotent, ändert keine vorhandene Zeile) oder den Knopf
  "Standardkategorien ergänzen" auf der Seite DMS, Suche im Archiv.
* `folders.py` und `GET /document-folders` (`documents:read`): die sechs Ordner aus
  `dms.DRIVE_FOLDERS` mit der Ablagevorgabe des Handbuchs (`anleitung-objektordner.md`), den
  Kategorien je Ordner und für 04 und 05 den Unterordnern aus der Objektübernahme
  (`objektakte_document_class.subfolder_name` mit den Dokumenttypen). Die Bezeichnungen der
  elf Unterordner liegen nicht im Repository und werden nicht erfunden; ohne Import zeigt das
  CRM "zu verifizieren" (`docs/OPEN_QUESTIONS.md` F-01). CRM: `DmsFolderStructure.tsx`.
* Upload in der Dokumentsuche (`DmsUpload.tsx`): zusätzlich Kategorie (`category_id`), Vertrag
  der Einheit oder des Objekts und Kontakt (Suche) als Verknüpfungen `contract` und `contact`
  mit Rolle `original`; der Endpunkt `POST /documents` konnte das bereits.
* Tests: `tests/integration/test_package_f_handover_folders.py`,
  `DmsUpload.test.tsx`, `DmsFolderStructure.test.tsx`.

## P17 (30.09.2026): Metadatenabgleich und Datenschutz

* `DocumentStore.update_meta` (M6-06): Änderungen an Titel, Kategorie und Verknüpfung markieren fertige Spiegel (`document_mirror.meta_dirty`), der Spiegeljob überträgt sie. Paperless setzt zusätzlich die Custom Fields `entity_type` und `entity_id` (M6-07) und das Kategorie-Tag `document_category.paperless_tag` (M6-09); Drive schreibt Beschreibung und `appProperties`.
* Datenschutz liegt im Modul `mhvp.privacy` (Löschprofile je Datenart, Löschantrag Art. 17, Register, Verarbeitungsverzeichnis als Entwurf), Regel `docs/rules/S16-P17-privacy.md`.

## Q03 (30.09.2026): transfer, ZIP import, redactions, holds, intake address, Drive changes

`transfer_routers.py` is included into `routers.router`:

* `POST /documents/uploads` and `/documents/uploads/{id}/complete`: presigned PUT into `tmp/<tenant>/uploads/<id>`, then the normal checks and `store_document` (S12-06). `GET /documents/{id}/download-url`: presigned GET for S3 originals.
* `POST /documents/zip-import`: every archive entry through the pipeline, refused files listed; recorded as `import_run` (source `document_zip`, M6-03).
* `GET/POST /documents/{id}/redactions`, `POST .../{rid}/release`: redacted copy with reason, scope and steps (`document_redaction`), internal until a second person releases it (M25-01).
* `GET/PUT /document-intake-address`: plus address per tenant (`intake_address.py`, stored in `TenantSettings.sources`); `intake.process_mailbox` treats mail to it as source `forward` (M6-04).
* `POST /dms-changes/google-drive/sync` and beat `mhvp.documents.drive_changes`: Drive Changes API with cursor `changes_page_token` in `DmsConnection.options` (`drive_changes.py`, M6-05).
* Beat `mhvp.documents.cleanup_tmp`: lifecycle rule on `tmp/` plus sweep (M6-08).
* Retention (S711-06): `document.retention_hold_kind`, `document.permanent_record`, `retention.profile_for_document` (profile per legal entity kind), `retention.related_hold`; see `docs/rules/Q03-documents-w3.md`.
* Retention U11 (S711-06 Rest): `retention.procedure_hold` (automatische Sperre bei aktiver Mahnsperre `litigation` oder `insolvency` auf einem offenen Posten eines verknüpften Vertrags), `retention.require_second_person` (Sperre am Dokument und am Vorgang hebt nur eine zweite Person auf), `GET /documents/{id}/retention-status`; see `docs/rules/U11-retention-sperren.md`.
* R02: `GET/PUT /document-direct-upload` (tenant switch for the browser upload, default off, stored in `TenantSettings.sources`), `distribute` flag in `/document-intake-address` and `distribution.py` (hub tenant hands messages with another tenant's token over to that tenant before `process_mailbox`; watermark `document_intake_distribution_watermark`). Migration 0284 is a no-op that keeps the chain.
* V03 (U11-01, V11-07): start rule `resolution` (`Document.retention_resolution_id`, migration 0300, `retention.sync_resolution_base` copies `Resolution.decided_on` into `retention_base_on`); `POST /documents/{id}/hold` answers 409 while a hold is active; `retention-status` adds `retention_resolution_id` and `hold_set_by_four_eyes_required`.
* AA13 (GA10-01 to GA10-05): `intake.match_units`/`match_contracts`, IBAN (fingerprint) and customer number in `match_contacts`, `intake_followup.suggest` (proposals in `AiProposal.final["followups"]`, `POST .../followups/{kind}/confirm` only links ticket or contract), `intake.auto_file` behind `TenantSettings.sources["document_intake_auto_file"]` (default off, `POST .../revert-auto`), `DocumentStore` with `get`, `search`, `list_changes` and `MinioStore`; see `docs/rules/AA13-intake-zuordnung.md`. Migration 0315 is a no-op.
* AA05 (GA04-10, GA04-11): `DocumentTemplate.master_template_id`, `context_types` (contact, contract, unit, property, meeting, statement, ticket; empty means unrestricted) and `placeholders_used` (computed by `letters.placeholders_of`); `GET /document-templates?context_type=`; a letter with an entity the template does not allow answers 422. `GeneratedDocument` (`generated_document`, migration 0307) records template, version, context, recipient and dispatch of every stored letter (`_letter`, `letter_records.store_letter`, `record_dispatch`); `GET /generated-documents` joins channel and evidence of the dispatch. `template_block` is open (AA05-02). Rule `docs/rules/GA04-vorlagen-erzeugte-dokumente.md`.
* AA17 (GA01-09): `folder_scheme.py` validates and renders the Drive folder scheme (`dms_connection.options["folder_scheme"]`, default `{objekt}/{jahr}`); `GoogleDriveStore.file_in_property_year_folder` uses it, `PUT /dms-connections/google_drive` validates it.
* AB05 (GA04-07, GA04-10, GA04-11): `PATCH /document-templates/{id}` maintains `context_types` (placeholders recomputed); `GET /generated-documents` filters by `template_id`, `created_from`, `created_to`. CRM page `/dokumente/erzeugt`.

## AC05: Verknüpfungsziele Vermögensbericht und Abrechnungslauf

`LINKABLE` kennt `asset_report` (HoaAssetReport) und `statement` (Abrechnungslauf der Betriebskosten). Erzeugte Dokumente (Versandbrief, Informationsblatt) tragen diese Verknüpfung zusätzlich zu `generated_document.context`. Ein Ziel eines anderen Mandanten antwortet 404 (RLS).

## AC07: deletion checklist per target and follow up (GA08-08)

`deletion_checklist.py` derives the state of a deletion per target (index, original, Paperless,
Drive, embeddings, AI extracts, thumbnails not stored, backups out of scope) from rows and
events. `retention.delete_now` and the journal replay purge embeddings and replace AI extract
content in the deleting transaction and journal the storage key. The daily task
`mhvp.documents.deletion_follow_up` and `POST /documents/deletions/{id}/follow-up` repeat open
targets; a document that exists again (restore) is never deleted by the follow up. A repeated
deletion after a restore resets the mirror steps to open (`mirror_deletion.request`). Backups
are not edited (runbook `backup.md`). Rule: `docs/rules/AC07-auskunft-loeschung.md`; open:
AC07-02, AC07-03.

## AE16: Textbausteine mit Freigabe (AA11-01, AA11-02)

Tabelle `legal_text_block` (Migration 0372), Router `text_block_routers.py` unter `/document-text-blocks`, Lesezugriff `text_blocks.approved_texts`. Status draft, submitted, approved, retired; Freigabe nur durch eine zweite Person (documents:approve). Das Informationsblatt und die Eigentümerausgaben (billing) setzen nur freigegebene Texte ein, sonst "Text nicht freigegeben". Regel docs/rules/AE16-01.md.

## AE29: Rechtstexte des Portals als Textbausteine

`TEXT_BLOCK_CODES` enthält zusätzlich `impressum`, `datenschutz` und `nutzungsbedingungen` (Portal, M21-04). Lebenszyklus und Vier-Augen-Freigabe sind unverändert; `approve_block` ruft `mhvp.platform.legal_texts.follow_terms_version` auf (wirkt nur beim Code `nutzungsbedingungen` und nur im Mandantenschalter follow_text). Öffentlicher Abruf und Abgleich mit der Einwilligungsrichtlinie: siehe `mhvp/platform/README.md`.

## AE33: document trash (AC07-03)

`trash.py`: tenant switch `document_trash_setting` (off by default, period 30 days as a
proposal, open question AE33-01). `retention.dispose` is the single door of a lawful deletion
(`DELETE /documents/{id}` and the proposal execution): switch off means `delete_now` as before,
switch on means `trash.move_to_trash` (`document.deleted_at`, `deleted_by`, `purge_at`, event
`document.trashed`). A trashed document is hidden from every ORM query by the session filter at
the end of `models.py` (`include_trashed` execution option or the `trash.trashed_visible`
context opts in). `GET /documents/trash`, `POST /documents/trash/{id}/restore` and `.../purge`
(reason required, `document.restored`, `document.deleted` with `from_trash`), `GET` and `PUT
/documents/trash-settings`; the daily task `mhvp.documents.trash_purge` deletes what is due.
Every final deletion runs `services.deletion_blocker` again, a hold keeps the document in the
trash (refusal logged once per reason). The deletion checklist has the target `trash` and the
overall status `in_trash`; the journal export carries `document.trashed` and
`document.restored`, and the replay applies the last statement per document (`trashed`,
`restored`). Backups are not edited. Rule: `docs/rules/AE33-papierkorb-auskunft.md`.

## Eingebettete Schriften im Briefbogen (GAE-37, Welle 17)

`pdf_fonts.py` registriert eine freie TrueType-Schrift (Liberation Sans, sonst DejaVu Sans) für
`letters.render_pdf`, damit alle Schriften eingebettet sind (Voraussetzung der PDF/A-3-Vorprüfung
in `accounting/zugferd.py`). Suchreihenfolge: Verzeichnis aus `MHVP_PDF_FONT_DIR`, dann
`/usr/share/fonts/truetype/liberation`, `liberation2`, `dejavu` (Pakete `fonts-liberation` und
`fonts-dejavu-core` im API-Image). Fehlt jede Schrift, gilt Helvetica als Fallback; die
Vorprüfung meldet dann den Blocker "Schriften nicht eingebettet" mit Installationshinweis.

## Textbausteine, Zweitpersonprüfung (AF12)

`/document-text-blocks/policy` (GET, PUT) liest und setzt den Mandantenschalter `require_second_person` (Standard an, gespeichert in `tenant_settings.sources["text_block_policy"]`). Abschalten braucht eine Begründung; die Freigabe ohne zweite Person erzeugt das Ereignis `text_block.approved_without_second_person`. Der Code `letter_notice` ist der Hinweis im Mieter-Anschreiben (`billing/letters.py`), gedruckt nur freigegeben, sonst "Text nicht freigegeben".

## AF10: pipeline follow-ups (wave 17, rule AF10-01)

* `services.store_document` emits `document.created` for every source (payload `size`,
  `source`, caller context via `event_payload`); routers no longer emit it (GAB-07).
* `tasks.mirror_tenant`: after a Paperless consume task resolves, `PaperlessStore.content`
  fills `ocr_text` of a `pending` document (GAB-04). Search vector is generated; embeddings
  follow through `updated_at`.
* Tenant switch `invoice_intake_auto` (`GET/PUT /document-invoice-intake-auto`, default off):
  accepting an invoice intake proposal starts `paperless_webhook.intake_document` (receipt
  draft, proposal only). Off: the CRM button "Beleg erfassen" calls `POST /receipts/drafts`.
* `trash.restore_for_reimport`: the objektakte import queries with `include_trashed` and
  restores its own trashed row instead of hitting `uq_document_source`; the tenant export
  includes trashed documents (GAE-35).

## AF21 (GAB-16)

`POST /documents/bulk-link` verknüpft viele Dokumente mit einem Objekt als Anlage (Teilerfolgsbericht, Savepoint je Dokument, Ereignis `document.linked`). Original, Beleg und erzeugte Rollen werden nicht gesammelt gesetzt.

## AH16 (GAG-26, wave 19)

`POST/DELETE /documents/{id}/hold` now have a CRM screen in `RetentionStatusCard.tsx`
(set: `documents:update`, lift: `documents:approve`; the API keeps the second person check).
The BFF forwards a JSON body on DELETE when one is present (needed for the lift reason).
API coverage: `tests/integration/test_u11_retention_procedure_holds.py` (422, 403, 404, 409,
second person) and `test_q03_documents_w3.py`.

## AM01 (GAJ-301, wave 23): payment files locked behind G2

`mhvp.documents.payment_files`: a document is a payment file when its category code is
`payment_file` or a direct debit run (pain.008) or payment batch (pain.001) references it. For
such a document `GET /documents/{id}/content` and `/download-url` answer 403
`MHVP-GATE-0001` while G2 is closed; the portal single download and `POST /portal/documents/bundle`
answer 404; `queue_mirrors` queues no DMS mirror and the mirror job marks older queued mirrors
`failed` (`payment_file_locked`). The pain.008 file is stored in the `payment_file` category
(created on demand); `POST /document-categories/ensure-defaults` aligns older files. Events
`direct_debit_run.file_generated` and `.file_downloaded` carry no document id. Rule
`docs/rules/GAJ-301-zahlungsdateien.md`.
