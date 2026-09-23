#!/bin/bash
# SessionStart hook for Claude Code on the web: dependencies plus local PostgreSQL 16
# (pgvector, roles per ADR 0002) and Redis, so lint, tests and integration tests run.
set -euo pipefail
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then exit 0; fi
cd "$CLAUDE_PROJECT_DIR"

(cd apps/api && uv sync)
pnpm install

if ! [ -f /usr/share/postgresql/16/extension/vector.control ]; then
  apt-get install -y postgresql-16-pgvector >/dev/null 2>&1 || apt-get update -q >/dev/null && apt-get install -y postgresql-16-pgvector >/dev/null
fi
PGDIR=/var/lib/mhvp-dev-pg
if ! [ -d "$PGDIR/data" ]; then
  mkdir -p "$PGDIR" && chown postgres:postgres "$PGDIR" && chmod 700 "$PGDIR"
  su postgres -s /bin/bash -c "echo postgres > $PGDIR/pw && /usr/lib/postgresql/16/bin/initdb -D $PGDIR/data -U postgres --auth-local=trust --auth-host=scram-sha-256 --pwfile=$PGDIR/pw -E UTF8 --locale=C.UTF-8 >/dev/null"
fi
if ! pg_isready -q -h 127.0.0.1; then
  su postgres -s /bin/sh -c "setsid /usr/lib/postgresql/16/bin/postgres -D $PGDIR/data -p 5432 -k /tmp -c listen_addresses=127.0.0.1 >>$PGDIR/log.txt 2>&1 < /dev/null &"
  for _ in $(seq 1 30); do pg_isready -q -h 127.0.0.1 && break; sleep 1; done
fi
redis-cli ping >/dev/null 2>&1 || setsid redis-server --daemonize yes --port 6379 --save '' --appendonly no >/dev/null

PGHOST=127.0.0.1 PGUSER=postgres PGPASSWORD=postgres \
  MHVP_DB_MIGRATOR_PASSWORD=dev-migrator MHVP_DB_APP_PASSWORD=dev-app sh infra/postgres/bootstrap.sh

cat >> "$CLAUDE_ENV_FILE" <<ENV
export MHVP_DATABASE_URL=postgresql+psycopg://mhvp_app:dev-app@127.0.0.1:5432/mhvp
export MHVP_MIGRATION_DATABASE_URL=postgresql+psycopg://mhvp_migrator:dev-migrator@127.0.0.1:5432/mhvp
export MHVP_REDIS_URL=redis://127.0.0.1:6379/0
export MHVP_REQUIRE_INTEGRATION=1
ENV
