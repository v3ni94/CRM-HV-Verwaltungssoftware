# Runbook: local development

Applies to milestone M1. Contract: `docs/plans/M1.md` sections 4 and 5.

## 1. Docker Compose stack

```sh
cp .env.example .env    # set every change-me value; .env is git ignored
make dev                # docker compose --env-file .env -f infra/compose.yaml -f infra/compose.dev.yaml up -d --build
```

Services: traefik (dev only, `127.0.0.1:80`, dashboard `127.0.0.1:8080`), postgres
(`127.0.0.1:5432`), redis (`127.0.0.1:6379`), objectstore (S3 API `127.0.0.1:8333`,
SeaweedFS, see ADR 0005), migrate (one shot: `alembic upgrade head`, then
`python -m mhvp.core.storage_bootstrap`), api, worker, beat, web-crm, web-portal.

Hostnames (`*.localhost` resolves locally without DNS):

| URL | Service |
| --- | --- |
| `http://crm.localhost` | web-crm |
| `http://portal.localhost` | web-portal |
| `http://api.localhost/api/v1/health/live` | api liveness |
| `http://api.localhost/api/v1/health/ready` | api readiness (database, database_role, migrations, redis, object_storage) |
| `http://api.localhost/api/v1/docs` | OpenAPI UI |

`make down` stops the stack. `make migrate` runs Alembic in the migrate container.

Known limitation: in the Claude Code cloud environment Docker Hub downloads are blocked
(OPEN_QUESTIONS M1-07), so `make dev` could not be run end to end there.

## 2. Native development without Docker

Prerequisites: PostgreSQL 16 with the pgvector extension installed, Redis 7, Python 3.12
with uv, Node 22 with pnpm 10. An S3 compatible store is needed only for the
`object_storage` readiness check.

1. Bootstrap the database as a superuser (idempotent, `infra/postgres/sql/bootstrap.sql`):

   ```sh
   export PGHOST=localhost PGUSER=postgres PGPASSWORD=...
   export MHVP_DB_MIGRATOR_PASSWORD=... MHVP_DB_APP_PASSWORD=...
   make db-bootstrap
   ```

   Optional: `MHVP_DB_NAME` (default `mhvp`), `MHVP_DB_MIGRATOR_ROLE` (`mhvp_migrator`),
   `MHVP_DB_APP_ROLE` (`mhvp_app`). The bootstrap creates the `vector` extension; migration
   0001 fails with a clear message if it is missing.

2. Export the environment (all variables prefixed, no secrets in the repo):

   | Variable | Example |
   | --- | --- |
   | `MHVP_ENV` | `dev` (`dev`, `test`, `staging`, `prod`) |
   | `MHVP_LOG_LEVEL` | `INFO` |
   | `MHVP_LOG_FORMAT` | `console` or `json` |
   | `MHVP_DATABASE_URL` | `postgresql+psycopg://mhvp_app:<pw>@localhost:5432/mhvp` |
   | `MHVP_MIGRATION_DATABASE_URL` | `postgresql+psycopg://mhvp_migrator:<pw>@localhost:5432/mhvp` |
   | `MHVP_REDIS_URL` | `redis://localhost:6379/0` |
   | `MHVP_CELERY_BROKER_URL` | `redis://localhost:6379/1` |
   | `MHVP_CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` |
   | `MHVP_S3_ENDPOINT_URL` | `http://localhost:8333` |
   | `MHVP_S3_REGION` | `us-east-1` |
   | `MHVP_S3_ACCESS_KEY_ID`, `MHVP_S3_SECRET_ACCESS_KEY` | local values |
   | `MHVP_S3_BUCKET` | `mhvp` |
   | `MHVP_API_INTERNAL_URL` | `http://localhost:8000` (web apps, server side) |
   | `MHVP_APP_VERSION` | `0.1.0` |

3. Run migrations and the API:

   ```sh
   cd apps/api
   uv sync
   uv run alembic upgrade head          # role mhvp_migrator
   uv run uvicorn mhvp.main:app --reload --port 8000
   uv run celery -A mhvp.worker worker -Q default,io,ocr,ai,bank,mail,beat
   ```

4. Web apps: `pnpm install` at the root, then `pnpm --filter @mhvp/web-crm dev` (port 3000) and
   `pnpm --filter @mhvp/web-portal dev` (port 3001); see `apps/web-crm/README.md` and
   `apps/web-portal/README.md`.

## 3. Tests

| Command | Scope |
| --- | --- |
| `make test-api` | `cd apps/api && uv run pytest` |
| `make test-web` | Vitest in apps and packages |
| `make e2e` | Playwright smoke tests |
| `make lint`, `make typecheck` | ruff, eslint, agent docs sync; mypy strict, `tsc --noEmit` |

Integration tests (marker `integration`) need a real PostgreSQL bootstrapped as above. They
skip if no database is reachable, unless `MHVP_REQUIRE_INTEGRATION=1` is set; CI sets it so
a missing database fails the run. Report skipped tests as not executed (rule 0.1.9).

```sh
MHVP_REQUIRE_INTEGRATION=1 make test-api
```

## 4. Agent docs

Edit `docs/AGENT_RULES.md`, then `make agent-docs`. `python3 scripts/sync_agent_docs.py --check`
fails if `CLAUDE.md` or `AGENTS.md` is stale.

## 5. Not yet available

Observability (Grafana, Prometheus, Loki), the deploy, backup, EBICS and incident runbooks and
the seed helpers follow in M9 and later milestones (sections 17 and 18).
