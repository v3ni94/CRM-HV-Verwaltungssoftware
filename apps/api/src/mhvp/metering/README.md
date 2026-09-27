# mhvp.metering: Messdienstleister module (stage 1)

Specification: master prompt "Messdienstleister" (operator, 26.09.2026), sections 2 to 10 in
stage 1; rule `docs/rules/M40-01.md`; operator document `docs/integrations/messdienstleister.md`.

## Architecture

| Module | Content |
| --- | --- |
| `providers.py` | Provider catalogue as code constants (ista, Techem, KALO, Brunata Minol, BRUNATA-METRONA, other) with the documented API state per function and the source references Q1 to Q11. Research state 26.09.2026, re-check before implementing an adapter. |
| `adapters.py` | Adapter interface (`MeteringAdapter`), `ManualAdapter` (no remote call, every catalogue provider in stage 1) and `FakeAdapter` (tests only, honoured only in the `test` environment). |
| `models.py` | Tenant tables with RLS (migration 0145): `metering_connection`, `metering_external_billing_unit`, `metering_property_assignment`, `metering_unit_assignment`, `metering_sync_job`, `metering_clearing_item`, `metering_consumption_value`, `metering_billing_result`. |
| `services.py` | Shared business service used identically by the object tab and the central overview: capability matrix, connection test, conflict check, optimistic locking, provider change, sync job creation and execution, clearing. |
| `csv_io.py` | CSV template, preview, apply and export of property assignments (numbers as text, no formula export, duplicate protection, nothing stored by the preview). |
| `routers.py` | `/api/v1/metering` (see below). |
| `tasks.py` | Celery task `mhvp.metering.run_sync_job` for manually requested jobs. No beat entry: scheduled fetches are off. |

### Four dimensions per function (section 3)

`services.capability_matrix` combines documented support (catalogue), adapter implemented
(adapter's `implemented` set and `spec_version`), account release (maintained per connection by
the tenant, `account_release`) and the last connection test (result, timestamp, `test_stale`
after relevant configuration or secret changes). `available` is true only when all four are
fulfilled; writing functions (`roles`, `billing_input`) stay unavailable in stage 1.

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

### Sync jobs (section 10)

`POST /sync-jobs` (manual "Jetzt abrufen") creates a queued job when the function is available,
no assignment in scope is in conflict and no identical job is queued or running. The worker
re-checks the summed assignment version before fetching. Results: values stored per unit,
period, kind, unit of measure, source and version (identical values are skipped, changed
values become a new version, missing values stay NULL); unknown identifiers go to
`metering_clearing_item`. "No data" is a success; `unclear` is reported for an undetermined
outcome and never retried automatically; `last_success_at` is kept after later failures.

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
| GET /clearing-items; POST /clearing-items/{id}/resolve | read / metering_assignments:update | Clearing area |
| GET /assignments-import/template; POST /assignments-import/preview, /apply; GET /assignments-export | read / update / update / read | CSV |

All write endpoints require `tenant_settings.metering_module_enabled` (403 `MHVP-METR-0001`).

## Blocked pending provider documentation (stage 2)

* No real adapter exists. ista and KALO are the first candidates; their methods, payloads,
  authentication (ista: different schemes per API family, mTLS differs between test and
  production, Q9) and versions must be taken from the official technical specification after
  access is granted (`docs/OPEN_QUESTIONS.md` M40-01 to M40-03).
* Techem, Brunata Minol and BRUNATA-METRONA: no technical endpoint documentation in the checked
  sources; catalogue states "Dokumentation erforderlich" or "Ungeklärt", never "Nein".
* Billing unit data reconciliation (Q8), roles submission (Q10) and billing input (Q11) are
  writing processes and are not offered in stage 1; `metering_users:submit` and
  `metering_billing:order` are registered but no endpoint uses them.
* Document retrieval into the document store (section 11) waits for a documented adapter.
* Real adapters must route outbound calls through `mhvp.core.webhooks.pin_target` and keep
  TLS verification on.
