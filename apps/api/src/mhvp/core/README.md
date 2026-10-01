# mhvp.core

Cross-cutting infrastructure used by every domain package.

| Module | Purpose | Reference |
| --- | --- | --- |
| `config.py` | Settings from `MHVP_*` environment variables, secrets as `SecretStr` | docs/plans/M1.md 4.1 |
| `logging.py` | structlog JSON logging, no request bodies or query strings | section 16 |
| `context.py`, `middleware.py` | Correlation id, sanitised access log, last resort 500 problem | ADR 0004 |
| `problems.py` | RFC 9457 problem details and the error code registry | ADR 0004 |
| `idempotency.py`, `ratelimit.py`, `request_identity.py` | `Idempotency-Key` middleware (Redis, 24 h, per tenant and actor) and rate limiting per token, API key or client address with `X-RateLimit-*` headers | ADR 0008 |
| `ids.py` | UUID v7 | section 4.1 |
| `db/` | Engines, declarative base, tenant transactions, RLS statements | ADR 0002 |
| `release_gates.py` | Release gates G1 to G5, fail closed | ADR 0003, section 18.0 |
| `health.py` | Liveness and readiness, runtime check of the database role | M1 acceptance |
| `storage.py`, `storage_bootstrap.py` | S3 client, bucket bootstrap job | ADR 0005 |
| `tasks.py` | Core Celery tasks (`mhvp.core.ping`) | section 3.2 |
| `auth/scope.py` | Legal entity access scope per membership (A37): `allowed_legal_entity_ids`, `ensure_session_legal_entity_allowed` for domain helpers, dependency `legal_entity_scope`; effective only for `SCOPED_ROLES` (tax_advisor), empty list means no access | docs/rules/M18-05-steuerberaterzugang.md |
| `auth/oidc.py`, `auth/oidc_clients.py` | OIDC provider for other tools (discovery, code flow with PKCE) and the operator CLI to register relying parties | ADR 0006 Nr. 7, docs/plans/M30-sso.md |

Rules for new tenant tables: column `tenant_id UUID NOT NULL`, leading index column, and the
statements of `db.rls.tenant_rls_statements()` in the same migration. The integration test
`test_every_tenant_table_is_isolated` fails otherwise.

## API versioning (ADR 0009, A50)

`mhvp.core.versioning`: `API-Version` on every response, `@deprecated(...)` or
`register_deprecation(...)` for endpoints (Deprecation, Sunset, Link headers; OpenAPI marks via
`mark_deprecated_routes`, which flattens included routers). `mhvp.openapi.breaking_removals`
and `make openapi-check` stop the removal of a path or field without a passed sunset.
Outgoing webhook event catalogue: `mhvp.core.webhooks.EVENT_TYPES` (docs/integrations/webhooks.md).

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `auth/keys.py`: `python -m mhvp.core.auth.keys`: new values for `MHVP_MASTER_KEY` and `MHVP_JWT_PRIVATE_KEY`
* `auth/passwords.py`: Argon2id hashing and password policy (A-012)
* `auth/permissions.py`: permission matrix resource x action, system roles with inheritance (3.4, M2-07)
* `auth/principal.py`: request principal from bearer token or API key, tenant and host check, permission guard
* `auth/service.py`: login, MFA, token sessions, tenant switch (3.4); password policy in `auth/passwords.py` (minimum 6 characters by operator decision M2-01, below the BSI recommendation, see `docs/OPEN_QUESTIONS.md`)
* `auth/tokens.py`: access tokens (JWT ES256), MFA step tokens, opaque secrets
* `auth/totp.py`: TOTP second factor (RFC 6238), optional per user (operator 26.09.2026, M2-01; self service under `/auth/totp/*`, trusted devices 90 days)
* `crypto.py`: field encryption AES-256-GCM with HKDF scoped keys (3.5, ADR 0006)
* `db/columns.py`: shared column definitions (id, tenant_id, created and updated metadata)
* `db/engine.py`: engine factories, psycopg 3 for async API and sync callers (ADR 0001)
* `db/tenancy.py`: tenant scoped transactions `tenant_tx` (ADR 0002, 5.3); `after_commit(session, hook)` registers a coroutine that `tenant_transaction` runs only after a successful commit (event consumers with side effects outside the database, for example mail archiving on ticket closure); hooks are dropped on rollback and a failing hook is logged, never raised
* `escaping.py`: escaping helpers for values that leave the application in a foreign syntax
* `events.py`: domain events and audit log, both append-only (2.5, 6.8)
* `numbering.py`: tenant wide business number sequences (4.1: contract, document, ticket numbers)
* `sqldump.py`: shared parser for `mysqldump`/MariaDB dumps used by data takeovers (FLOW, U-Protokoll, objektakte)
* `webhook_tasks.py`: Celery job: enqueue and deliver outgoing webhooks for every tenant (every minute)

## List pagination (`core/pagination.py`, review 26.09.2026)

`paginate(session, query, response, page=, page_size=, limit=, offset=)` counts the query,
fetches one page and sets `X-Total-Count`, `X-Page`, `X-Page-Size`; `PAGE_HEADERS`
documents them in OpenAPI. Responses stay plain lists (pattern of `GET /tickets`).

## Permission cache (`auth/permission_cache.py`, review 26.09.2026, item 2)

`get_principal` resolves the principal once per request (`request.state.principal`) and takes
roles and permissions of a bearer principal from a process local TTL cache keyed by
`(tenant_id, user_id)`: at most 30 s (`MHVP_PERMISSION_CACHE_TTL_SECONDS`, capped at 30, 0
disables), bound to the membership id. User (`active`) and membership (`status`, legal entity
scope) are read on every request, so locks take effect immediately; portal grants never use
the cache. `invalidate_permissions(tenant_id)` runs after the commit of `set_member_roles`,
`PUT /tenant/roles/{id}/permissions` and `sync_roles`; a change made in another process takes
effect after the TTL at the latest. Details: ADR 0002, addendum 26.09.2026.

## Auth additions (package P14, 30.09.2026)

- `auth/breached.py`: offline check against compromised passwords (bundled SHA-1 list, optional
  file `MHVP_BREACHED_PASSWORDS_FILE`, `register_source`); used by `passwords.policy_violation`
  (minimum 12, rule `docs/rules/M2-05-passwortregeln.md`).
- `auth/scope.py`: property assignment (`allowed_property_ids`, `ensure_property_allowed`,
  session variants) from `Membership.property_ids` (rule M2-02).
- `auth/webauthn.py`: passkeys (rule S16-01, replaces the prepared state of M2-03). Narrow
  WebAuthn Level 2 profile on top of `cryptography`: attestation `none`, ES256, EdDSA, RS256,
  single use Redis challenges (`webauthn:challenge:*`, 300 s, `GETDEL`), origin allow list,
  RP ID hash, user presence, user verification for passwordless, strictly increasing sign
  counter. Off unless `MHVP_WEBAUTHN_ENABLED`, `MHVP_WEBAUTHN_RP_ID` and
  `MHVP_WEBAUTHN_ORIGINS` are set. Endpoints `/auth/webauthn/register/{options,verify}`,
  `/auth/login/webauthn/{options,verify}` (second factor with `mfa_token`, passwordless
  without), list and revoke; errors `MHVP-AUTH-0012` (off) and `MHVP-AUTH-0013` (check failed).
  Review W01 (01.10.2026, `docs/reviews/WEBAUTHN-2026-10-01.md`): strict base64url, CBOR
  without duplicate keys or non minimal lengths, no trailing bytes after the attestation object,
  AT flag required at registration and refused in assertions, ED extensions must be exactly
  one CBOR map, `userHandle` must match the credential owner, failure reason only logged
  (response carries the generic `MHVP-AUTH-0013` text), inactive owner answers like unknown.
- `auth/portal_roles.py`: named portal roles and the derivation rule of 3.4 (S16-10).
- CSRF and field encryption evidence: `docs/security/S16-csrf-and-field-encryption.md`.

## Package Q13 (30.09.2026): property assignment, If-Match, key rotation

- `auth/scope.py` `property_path_guard`: router dependency (properties and contracts routers)
  that answers 404 for a `{property_id}` path outside the membership assignment (M2-02,
  docs/rules/M2-02-objektzuordnung.md). Domains filter lists with
  `session_allowed_property_ids` and check single records with
  `ensure_session_property_allowed`.
- `etag.py`: `etag_of` (version or `updated_at` in microseconds) and `check_if_match`
  (optional header, 412 `VERSION_CONFLICT`), ADR 0012 addendum (S12-04).
- `key_rotation.py`: generic master key rotation for all `EncryptedText` columns with dry run,
  fingerprint recomputation, idempotent rerun and JSON protocol without plaintext;
  `crypto.py` gained `ciphertext_scope`, `decrypt_with_master`, `encrypt_with_master`,
  `fingerprint_with_master` (S16-03, docs/runbooks/schluesselrotation.md).

## Package R08 (01.10.2026): property assignment in further domains

- `auth/scope.py` `property_column_guard(columns)`: router dependency factory mapping a path or
  query parameter to the column holding the property of that row (`legal_entity_id` and
  `ledger_id` columns resolve through the legal entity or the ledger); outside the membership
  assignment 404, unknown ids pass through. Used by billing (statements, owner statements,
  consumption info), hoa (`mhvp.hoa.property_scope`) and ledger reports.
- `mhvp.banking.property_scope`: account visibility by home property or assignment,
  `banking_path_guard` (transactions, accounts, payment orders, batches), list filters.
- Further `property_path_guard` users: properties sub routers, tax profile, notices.
- Global search and AI lookup tools filter by assignment; `workspace.routers.member` now keeps
  the legal entity and property scope of the principal (it dropped both before).

## Package Q12 (30.09.2026): list parameters, bulk endpoints, job switches, events

- `listparams.ListSpec` (GA04-05): declarative allowed filters, sorts, includes and optional
  `valid_from`/`valid_to` for `as_of`. `Depends(spec.dependency)` rejects with 422 every query
  parameter the route neither declares nor offers (also `as_of` on lists without validity);
  `spec.apply(query, params, default_order, request)` narrows and orders. Wired into
  `GET /banking/transactions`, `/hoa/resolutions`, `/accounting/dunning-runs` and
  `/mail/messages` (filters only, own order kept). ETag/If-Match (GA04-06) added to
  `PATCH /hoa/resolutions/{id}` and `GET`/`PATCH /mail/messages/{id}`; If-Match stays optional
  (ADR 0012) until AA04-01 is decided.
- AB04 (GA04-05, GA04-06 follow-up): `listparams.strict_query` is attached as route dependency
  (`dependencies=[Depends(strict_query)]`) to every GET list route (response `list[...]` or a
  page with `items`): every query parameter the route does not declare answers 422; `filter[...]`,
  `sort`, `fields`, `include` and `as_of` pass only to routes that parse them (`list_params` or a
  `ListSpec`). Existing parameters stay declared; `/tenant/events` now honours the formerly
  ignored `limit` as alias of `page_size`. Further `ListSpec` lists: `/work-orders`,
  `/sla/clocks`, `/sla/alerts`, `/automation/rules`, `/immoware/sync/runs`,
  `/metering/sync-jobs`, `/banking/rules`, `/banking/payment-orders`, `/letting/listings`,
  `/letting/prospects`. ETag/If-Match (optional, 412 on a stale token) on `PATCH /sla/rules/{id}`,
  `/automation/rules/{id}`, `/letting/listings/{id}`, `/letting/prospects/{id}`,
  `/banking/payment-orders/{id}`, `/teams/{id}`, `/mail/mailboxes/{id}`; ETag on `GET` of
  automation rules, listings and teams. Inventory test: `tests/integration/test_ab04_list_inventory.py`
  (list `REMAINING` for routes not converted, currently empty). GET routes without response model
  (60, mostly files and exports) are not part of the inventory.
- `listparams.py` (S12-03): `list_params` dependency parses `filter[field]=value` (comma means
  `IN`, `null` means `IS NULL`), `sort=field,-field`, `fields=a,b` and `include=x`.
  `apply_filters` and `apply_sort` accept only the columns a list declares, `check_include`
  only its offered relations, `sparse` reduces items to the requested keys plus `id`.
  Anything not offered answers 422 (`MHVP-CORE-0004`), never silently ignored. Wired into
  `GET /contacts`, `/properties`, `/contracts`, `/tickets` (include `property`; the legacy
  `sort=urgency|created_desc` stays), `/documents` and `/invoices`. Tenant, soft delete and
  property assignment filters stay in force. `embed` adds included relations (R07):
  `/contacts?include=properties` (via contract party or property owner),
  `/properties?include=legal_entities` (WEG entity and owners' entities),
  `/contracts?include=party,property`, `/documents?include=properties` (links to property,
  unit, contract, ticket), `/accounting/invoices?include=creditor` (provider contact).
  Included properties respect the property assignment (`mhvp.properties.refs`).
- `bulk.py` (S12-05): `run_bulk` with `BulkResultOut` and `BULK_MAX_ITEMS = 500`, used by
  `POST /contacts/bulk` (`add_tag`, `remove_tag`), `POST /properties/bulk`
  (`set_consumption_info`) and `POST /contracts/bulk` (`set_dunning_block`, reason
  required). Each item runs in its own savepoint; failures are reported per item.
- S15-03: the standard jobs of banking (`sync_all`, `sync_due`, `weekly_digest`), accounting
  (dunning and receivable previews), billing (consumption information) and workspace
  (reminders, digest, deadlines) ask `automation.job_schedule.job_allowed` per tenant.
- S12-01 events now emitted: `invoice.received`, `invoice.approved` (review closed),
  `invoice.paid` (bank evidence covers the gross amount), `dunning_case.created`,
  `dunning_case.sent`, `work_order.created`, `work_order.completed` (next to
  `work_order.done`), `document.shared` (new portal role in `visibility`),
  `ai_proposal.decided`.
- M9-02 `telemetry.py`: optional OpenTelemetry tracing, off unless `MHVP_OTEL_ENDPOINT` is set
  (OTLP/HTTP). FastAPI (path only, no query string, health probes excluded), SQLAlchemy engine,
  Celery (`worker_process_init`), httpx. `CorrelationIdMiddleware` returns `traceparent` next to
  `X-Correlation-ID`; `logging.add_trace_context` adds `trace_id` and `span_id` to log lines.
  Tests use `setup_tracing(..., span_processor=SimpleSpanProcessor(InMemorySpanExporter()))`.
  Runbook: `docs/runbooks/beobachtung.md`.

## Maskierung von Geheimnissen (S16-03)

`redaction.py` entscheidet zentral, welche Schlüsselnamen als Geheimnis gelten (`password`, `pin`,
`token`, `api_key`, `*_secret`, `*_password`, `*_token` usw.). Angewendet als structlog-Prozessor
auf jede Logzeile, auf `payload` und `changes` in `events.emit` (Domain Events, Audit-Log) und auf
geloggte Pfade mit Token (`/self-disclosure/…`, `/calendar-feed/…`). Prüfbericht:
`docs/reviews/SECRETS-2026-10-01.md`.

### Passkeys und Portalkonten (U04-02)

Passwortlose Passkey-Registrierung und -Anmeldung sind für reine Portalkonten (alle aktiven Mitgliedschaften nur mit Rolle `portal_user`) serverseitig gesperrt: 403 `MHVP-AUTH-0014`. Passkey als zweiter Faktor bleibt möglich. Prüfung in `core/auth/routers.py` (`_is_portal_only_user`), Regel `docs/rules/S16-01-passkeys.md`.
