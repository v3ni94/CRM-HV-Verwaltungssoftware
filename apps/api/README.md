# apps/api

FastAPI application, Celery worker and Alembic migrations of the MH Verwaltungsplattform
(Python package `mhvp`, layout per `docs/MASTER-PROMPT.md` section 17).

## Commands

```sh
uv sync                                   # install (exact versions from uv.lock)
uv run ruff check . && uv run ruff format --check .
uv run mypy                               # strict
uv run pytest                             # unit tests; integration tests skip without a DB
uv run alembic upgrade head               # needs MHVP_MIGRATION_DATABASE_URL (owner role)
uv run alembic check                      # fails on model/migration drift
uv run python -m mhvp.openapi > openapi.json
uv run uvicorn mhvp.main:app --reload     # needs the MHVP_* variables of docs/plans/M1.md 4.1
uv run celery -A mhvp.worker worker -Q default,io,ocr,ai,bank,mail,beat
```

Integration tests need a PostgreSQL 16 with pgvector prepared by `make db-bootstrap` and the
variables `MHVP_DATABASE_URL` (runtime role `mhvp_app`), `MHVP_MIGRATION_DATABASE_URL`
(owner role `mhvp_migrator`) and `MHVP_REDIS_URL`. With `MHVP_REQUIRE_INTEGRATION=1` a missing
database fails the run instead of skipping (CI). Details: `docs/runbooks/local-development.md`.

## Structure

* `src/mhvp/core/`: settings, logging, correlation id, problem details, tenancy and RLS,
  release gates, health, storage (see `src/mhvp/core/README.md`).
* `src/mhvp/<domain>/`: domain packages, reserved until their milestone.
* `src/mhvp/main.py`: app factory, `src/mhvp/worker.py`: Celery app.
* `alembic/`: migrations, run as the owner role only.
* `openapi.json`: committed OpenAPI document; CI fails on drift.

## Rules that apply to every change here

* Every tenant table: `tenant_id UUID NOT NULL`, leading index column, and
  `mhvp.core.db.rls.tenant_rls_statements()` in the same migration (ADR 0002). The test
  `test_every_tenant_table_is_isolated` enforces it.
* Tenant queries only inside `mhvp.core.db.tenancy.tenant_transaction()`.
* Functions behind release gates G1 to G5 use `require_release_gate` (API) or
  `ensure_release_gate_open` (jobs, imports, bulk, integrations) (ADR 0003).
* Errors are raised as `ProblemError` with a code registered in `mhvp.core.problems` (ADR 0004).
* Money is `Decimal` and `NUMERIC(14,2)`, intermediate values `NUMERIC(20,8)` (section 6.9.8).
