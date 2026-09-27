# mhvp.metering: Messdienstleister module (stage 1, stage 2 read paths, controlled write workflows)

Specification: master prompt "Messdienstleister" (operator, 26.09.2026), sections 2 to 10 in
stage 1; rule `docs/rules/M40-01.md`; operator document `docs/integrations/messdienstleister.md`.

## Architecture

| Module | Content |
| --- | --- |
| `providers.py` | Provider catalogue as code constants (ista, Techem, KALO, Brunata Minol, BRUNATA-METRONA, other) with the documented API state per function and the source references Q1 to Q11. Research state 26.09.2026, re-check before implementing an adapter. |
| `adapters.py` | Adapter interface (`MeteringAdapter`: `test_connection`, `fetch`, `download_document`, `acknowledge_document`, `submit_billing_unit_setup`, `fetch_billing_template`, `send_billing_input`, `send_roles`), record types (`WriteResult` with outcomes accepted, validated, rejected, unclear, failed), `ManualAdapter` (no remote call) and `FakeAdapter` (tests only, honoured only in the `test` environment; records every write in `writes`). Registers the real adapters at import. |
| `http.py` | `ProviderHttp`: pinned HTTPS client (`pin_target`, TLS on, no redirects), OAuth 2 client credentials with token cache, Basic, optional mTLS client certificate, GET retries with exponential backoff, writes sent exactly once (timeout = `unclear`), body size limit, `sanitize` for error texts (no secrets). |
| `bved.py` | Parsers and call sequences of the bved / ARGE OpenAPI families (billing-unit-data 1.0.2, billing-result 1.0.3, consumption-data 1.2.1, documents 1.3, billing-input 1.0.3 with `VALIDATE` / `SEND` / `SEND_AND_IGNORE_WARNINGS`, on-site-roles 2.0.2): offset/limit pagination (max 100), `_links.next` only on the configured host, exact `Decimal` amounts, `missing` never coerced, bounded parallelism (`run_bounded`). |
| `adapters_base.py` | `BvedAdapterBase`: family table per provider, `config_environment` guard (test and production never share a configuration), authentication per family, read only connection test, fetch per function, document download and receipt, setup submission (write, unexposed). |
| `adapters_ista.py`, `adapters_kalo.py` | Provider specific families, hosts and authentication schemes with their sources (see docs/integrations/messdienstleister.md, capability matrix). |
| `models.py` | Tenant tables with RLS (migration 0145): `metering_connection`, `metering_external_billing_unit`, `metering_property_assignment`, `metering_unit_assignment`, `metering_sync_job`, `metering_clearing_item`, `metering_consumption_value`, `metering_billing_result`; migration 0153: `metering_transmission` (controlled write workflows). |
| `services.py` | Shared business service used identically by the object tab and the central overview: capability matrix, connection test, conflict check, optimistic locking, provider change, sync job creation and execution, clearing. |
| `transmissions.py` | Controlled write workflows (section 12): payload construction for roles (complete set per unit, explicit vacancy and end markers) and billing input (period, provider template, CRM recipients, cost input), local validation, provider validation (`VALIDATE`), diff against the last ordered transmission, fingerprint, release, binding order, invalidation. |
| `csv_io.py` | CSV template, preview, apply and export of property assignments (numbers as text, no formula export, duplicate protection, nothing stored by the preview). |
| `routers.py` | `/api/v1/metering` (see below). |
| `tasks.py` | Celery task `mhvp.metering.run_sync_job`: `FOR UPDATE SKIP LOCKED` on the job row (no double start), `BlobStore` for document jobs, provider receipts in a second transaction after the commit. No beat entry: scheduled fetches are off. |

### Four dimensions per function (section 3)

`services.capability_matrix` combines documented support (catalogue), adapter implemented
(adapter's `implemented` set and `spec_version`), account release (maintained per connection by
the tenant, `account_release`) and the last connection test (result, timestamp, `test_stale`
after relevant configuration or secret changes). `available` is true only when all four are
fulfilled; writing functions (`roles`, `billing_input`) additionally need the per connection
release flag `write_sync_enabled` (default off), otherwise the reason names the flag.

### Secrets (section 9)

Secrets are an encrypted JSON object (`EncryptedText`, tenant scope, ADR 0006). The API accepts
them on `POST /connections` and `PUT /connections/{id}/secrets` (empty value removes one) and
returns only `secret_names`. They are decrypted only inside `services.connection_secrets` for an
adapter call. Nothing logs them.

### Assignments (sections 5 and 7)

`metering_property_assignment` links a CRM property to an external billing unit for one service
scope and validity. Conflict check (`_conflicting_assignments`): same property and scope with
overlapping validity, or the same external unit on another property, unless both rows carry the
same explicit `group_id` with disjoint `unit_scope`. Every update needs the current `version`
(409 `MHVP-METR-0003` otherwise). A provider change ends the old row the day before the change
date and creates the new one; documents and results keep their original assignment reference and
late imports are matched by their business period (`_find_assignment`).

`metering_unit_assignment` maps an internal unit to the external Nutzeinheit; `unit_id` and
`external_unit_number` are immutable (a correction is a new row), occupant changes touch only
recipients and `occupancy_status` (occupied, vacant, owner_use, unclear).

### Documents (section 11)

Provider documents are stored through `mhvp.documents.services.store_document` (validation with
`check_upload`, object store, links to `property` and, when the external unit is assigned,
`unit`) with `source_system="metering"`, `source_id=<connection>:<external id>:<version>` and a
`source_meta` block (provider, connection, environment, external id, version, doctype, period,
external billing unit and unit, assignment ids, sync job, fetched_at, `supersedes`,
`acknowledge_pending`). The assignment is resolved before the download; an unknown reference goes
to the clearing area. A re download of a known version is skipped (no duplicate); a changed
billing (new hash or type version) becomes a new document referencing the earlier ones. Documents
arrive with visibility `tenant` only (no resident release by the import). The provider receipt
(`PUT /documents/out/{id}/status`) is sent by the worker only after the transaction that stored
the document has committed; a failed receipt stays `acknowledge_pending` on the document.

### Sync jobs (section 10)

`POST /sync-jobs` (manual "Jetzt abrufen") creates a queued job when the function is available,
no assignment in scope is in conflict and no identical job is queued or running. The worker
takes the row with `FOR UPDATE SKIP LOCKED` (a second worker returns `skipped`), re-checks the
summed assignment version before fetching and passes the per data kind cursor
(`last_sync["_cursors"]`, advanced only after a fully successful run; `from` of billing unit
data, `updatedsince` of billing results). Statuses: `queued`, `running`, `waiting_provider`
(asynchronous Ordnungsbegriffsabgleich still running at the provider), `succeeded`, `partial`,
`failed`, `unclear`; `parts` carry `provider`, `fetch`, `store` and `clearing` with their errors.
Billing unit data results (setup status, matched and additional external units) are stored as
`remote_payload` of the known external billing unit; nothing is assigned automatically. Results: values stored per unit,
period, kind, unit of measure, source and version (identical values are skipped, changed
values become a new version, missing values stay NULL); unknown identifiers go to
`metering_clearing_item`. "No data" is a success; `unclear` is reported for an undetermined
outcome and never retried automatically; `last_success_at` is kept after later failures.

### Controlled write workflows (section 12, cases 11 and 12)

`metering_transmission` keeps every checked data set with its `fingerprint` (SHA-256 of the
canonical payload plus the summed versions of the property assignment and its unit
assignments), the validation result, the diff against the last ordered transmission of the
same assignment and kind, and a `log` of every step (user, time, data version, provider
answer). Steps and permissions:

1. `POST /transmissions/check` ("Daten prüfen", permission of the kind): builds the complete
   data set from the CRM. Roles (On-Site Roles 2.0 semantics): one `SendOnSiteRoles` body per
   unit assignment with partners (CRM contact id as `pmnumber`, names only), billing contract
   with explicit `vacancy`, `terminateall...` markers with date when the unit assignment has
   ended; missing unit assignments, unclear occupancy and missing recipients are errors. The
   check of roles is local (the API has no validate only action). Billing input: period,
   provider template (`fetch_billing_template`, when the function is available), recipients
   inside the period, cost input (amounts as text with two decimals, never rounded), then the
   provider validation with `action=VALIDATE` (stores nothing). Errors give status `invalid`,
   otherwise `checked`. Earlier open transmissions of the same assignment and kind become
   `superseded`.
2. `POST /transmissions/{id}/release` (same permission): status `checked` required, the given
   fingerprint must equal the stored one and the recomputed one (409 `MHVP-METR-0012`
   otherwise, row becomes `superseded`); warnings must be acknowledged explicitly (422
   `MHVP-METR-0013`), never skipped silently.
3. `POST /transmissions/{id}/order` ("Abrechnung verbindlich beauftragen" or "Nutzer und Rollen
   verbindlich übermitteln", same permission): status `released`, fingerprint unchanged,
   connection active, function available (documented, implemented, account released, tested,
   `write_sync_enabled`), no assignment conflict. Billing input sends `SEND`, or
   `SEND_AND_IGNORE_WARNINGS` only when the releasing user acknowledged warnings. Roles send
   one request per unit and stop at the first rejected or unclear unit. Every write is sent
   exactly once: `unclear` (timeout) is final until clarified manually, nothing is retried.

Any change of the property assignment or a unit assignment (create, update, provider change)
supersedes the open transmissions of that assignment (`services.invalidate_transmissions`).
Permissions: `metering_users:submit` for roles, `metering_billing:order` for billing input,
checked per kind on every step; `metering_data:read` lists and reads transmissions.

## Endpoints (`/api/v1/metering`)

| Method and path | Permission | Purpose |
| --- | --- | --- |
| GET /providers | metering_data:read | Catalogue with documented state per function, sources, research note |
| GET /connections, GET /connections/{id} | metering_data:read | Connections with capability matrix, never secrets |
| POST /connections, PATCH /connections/{id} | metering_connections:manage | Create (secrets optional), change with `version` |
| PUT /connections/{id}/secrets | metering_connections:manage | Set or replace secrets |
| POST /connections/{id}/test | metering_connections:manage | Read only authentication check through the adapter |
| GET /assignments (search, filters, page, page_size) | metering_data:read | Object tab (`property_id`) and central overview share this list |
| POST /assignments, GET /assignments/{id}, PATCH /assignments/{id} | update / read / update | Create, read, change with `version` |
| POST /assignments/{id}/remote-confirm | metering_assignments:update | Record the technical confirmation with its basis |
| POST /assignments/{id}/change-provider | metering_assignments:update | End old, create new |
| GET, POST /assignments/{id}/units; PATCH /unit-assignments/{id} | read / update | Unit assignments |
| GET /assignments/{id}/consumption, /billing-results | metering_data:read | Data views, period filter |
| GET, POST /sync-jobs; GET /sync-jobs/{id} | read / metering_sync:run | Jobs |
| GET /transmissions, GET /transmissions/{id} | metering_data:read | Controlled write workflows |
| POST /transmissions/check, POST /transmissions/{id}/release, POST /transmissions/{id}/order | metering_users:submit (roles) or metering_billing:order (billing_input) | "Daten prüfen", release, binding order (separate endpoints) |
| GET /clearing-items; POST /clearing-items/{id}/resolve | read / metering_assignments:update | Clearing area |
| GET /assignments-import/template; POST /assignments-import/preview, /apply; GET /assignments-export | read / update / update / read | CSV |

All write endpoints require `tenant_settings.metering_module_enabled` (403 `MHVP-METR-0001`).

## Blocked pending provider documentation

* No real access exists: all tests run against `httpx.MockTransport` and the `fake` adapter.
  End to end checks against ista or KALO test systems are not executed (M40-01).
* ista: base URLs and the OAuth 2 token URL are transmitted at onboarding (Q9) and must be
  configured per connection (`base_urls`, `token_url`, `config_environment`); test access needs
  the mTLS client certificate (`client_cert_pem`, `client_key_pem` in the secrets).
* KALO: no test system URL, no billing unit data or billing result API, no documented body for
  the document status call on the KALO page (bved 1.3 body used), no documented mapping of
  `resident` references to a billing unit (such documents go to clearing).
* Techem, Brunata Minol and BRUNATA-METRONA: no technical endpoint documentation (M40-02);
  catalogue "Dokumentation erforderlich" or "Ungeklärt", never "Nein"; adapter `manual`.
* Writing functions: roles (bved on-site-roles 2.0.2) and billing input (bved billing-input
  1.0.3) are implemented for ista from the bved zip files (Q6, checked 27.09.2026; Q10 and Q11
  name the modes but no endpoint paths) and reachable only through the transmission workflow;
  the ista base URLs (`base_urls.roles`, `base_urls.billing_input`) come from the onboarding
  (Q9). The setup submission of the Ordnungsbegriffsabgleich (`submit_billing_unit_setup`) is
  still not offered by any endpoint (M40-03). KALO: roles documented (Q3) but not implemented
  (no endpoint documentation on Q3), billing input unclear; Techem, Brunata Minol and
  BRUNATA-METRONA: manual adapter, "Dokumentation erforderlich". For these providers the
  workflow stops at the local check (provider validation skipped with the reason shown) and
  the order is refused (409 `MHVP-METR-0004`).
* No real order, user change or billing has been triggered: all write tests run against the
  `fake` adapter or `httpx.MockTransport`; the end to end check against an ista test system
  is not executed (M40-01).
* The document store has no malware scanner; `check_upload` (size, MIME allow list, content
  sniffing) is the existing check that is applied.
