# mhvp.documents

Documents, links, categories, retention profiles, DMS mirrors (Paperless-ngx, Google Drive),
letter templates, PDF letters and serial letters.

* Milestone: M6, plan and decisions in `docs/plans/M6.md`.
* Specification: docs/MASTER-PROMPT.md 6.7, 6.9.5, 7.11, 11.
* Files: `models.py`, `schemas.py`, `routers.py`, `services.py` (store, link, retention,
  letter context), `blobs.py` (S3 originals), `text.py` (text layer, type checks), `dms.py`
  (store protocol and adapters), `tasks.py` (mirror job), `letters.py` (placeholders, DIN 5008
  PDF), `defaults.py` (categories, free letter).
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

## Performance (Review 26.09.2026)

`GET /documents/intake-proposals` loads the documents of a page in one IN query. Indexes
`document(tenant_id, created_at)` and `ai_proposal(tenant_id, entity_type, decision,
created_at)` (migration 0127). Measurements in `docs/reviews/2026-09-26-performance.md`.
