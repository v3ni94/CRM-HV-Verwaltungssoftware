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

## A44: Löschjournal und Wiederanwendung nach Restore (D47, M9-03)

`deletion_journal.py` derives the journal from the append only domain events
(`document.deleted`, `document.deletion_refused`, `document.hold_set`, `document.hold_cleared`)
without touching the store. CLIs: `python -m mhvp.documents.export_deletions --since <ISO> --out
<file>` before a restore, `python -m mhvp.documents.replay_deletions --journal <file> [--apply]
[--report <file>]` afterwards (dry run by default). The replay deletes a document only when it
exists, its hash equals the hash recorded at the original deletion, no deletion hold and no
other blocker (`services.deletion_blocker`) applies and no non pending DMS mirror exists; every
deletion and refusal is emitted again with `replay: true`. Procedure: `docs/runbooks/backup.md`;
test: `tests/integration/test_m9_restore_replay.py`.

