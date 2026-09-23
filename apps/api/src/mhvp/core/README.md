# mhvp.core

Cross-cutting infrastructure used by every domain package.

| Module | Purpose | Reference |
| --- | --- | --- |
| `config.py` | Settings from `MHVP_*` environment variables, secrets as `SecretStr` | docs/plans/M1.md 4.1 |
| `logging.py` | structlog JSON logging, no request bodies or query strings | section 16 |
| `context.py`, `middleware.py` | Correlation id, sanitised access log, last resort 500 problem | ADR 0004 |
| `problems.py` | RFC 9457 problem details and the error code registry | ADR 0004 |
| `ids.py` | UUID v7 | section 4.1 |
| `db/` | Engines, declarative base, tenant transactions, RLS statements | ADR 0002 |
| `release_gates.py` | Release gates G1 to G5, fail closed | ADR 0003, section 18.0 |
| `health.py` | Liveness and readiness, runtime check of the database role | M1 acceptance |
| `storage.py`, `storage_bootstrap.py` | S3 client, bucket bootstrap job | ADR 0005 |
| `tasks.py` | Core Celery tasks (`mhvp.core.ping`) | section 3.2 |

Rules for new tenant tables: column `tenant_id UUID NOT NULL`, leading index column, and the
statements of `db.rls.tenant_rls_statements()` in the same migration. The integration test
`test_every_tenant_table_is_isolated` fails otherwise.
