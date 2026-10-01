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
- `auth/webauthn.py`: passkeys prepared, `AVAILABLE = False`, endpoints under
  `/auth/webauthn/*` (rule M2-03).
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

## Package Q12 (30.09.2026): list parameters, bulk endpoints, job switches, events

- `listparams.py` (S12-03): `list_params` dependency parses `filter[field]=value` (comma means
  `IN`, `null` means `IS NULL`), `sort=field,-field`, `fields=a,b` and `include=x`.
  `apply_filters` and `apply_sort` accept only the columns a list declares, `check_include`
  only its offered relations, `sparse` reduces items to the requested keys plus `id`.
  Anything not offered answers 422 (`MHVP-CORE-0004`), never silently ignored. Wired into
  `GET /contacts`, `/properties`, `/contracts`, `/tickets` (include `property`; the legacy
  `sort=urgency|created_desc` stays), `/documents` and `/invoices`. Tenant, soft delete and
  property assignment filters stay in force.
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
