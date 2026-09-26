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
