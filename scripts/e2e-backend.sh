#!/usr/bin/env bash
# End-to-end tests of the CRM against a real API (Playwright tests tagged @backend).
#
# Expects a bootstrapped PostgreSQL (infra/postgres/bootstrap.sh, `make db-bootstrap`) and a
# Redis. Migrates, generates throwaway auth keys if unset, seeds a fresh admin account, starts
# the API on port 8000 in the background, builds the CRM and runs Playwright with E2E_BACKEND=1.
#
# Defaults match the local dev setup (roles mhvp_app/dev-app, mhvp_migrator/dev-migrator,
# database mhvp on 127.0.0.1:5432, Redis on 127.0.0.1:6379). Override via the MHVP_* variables.
# Each run seeds a new admin e-mail by default: the seed skips existing accounts, and an
# existing account would already have TOTP set up with an unknown secret.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
API_DIR="$ROOT/apps/api"
API_PORT="${MHVP_E2E_API_PORT:-8000}"

export MHVP_ENV="${MHVP_ENV:-test}"
export MHVP_DATABASE_URL="${MHVP_DATABASE_URL:-postgresql+psycopg://mhvp_app:dev-app@127.0.0.1:5432/mhvp}"
export MHVP_MIGRATION_DATABASE_URL="${MHVP_MIGRATION_DATABASE_URL:-postgresql+psycopg://mhvp_migrator:dev-migrator@127.0.0.1:5432/mhvp}"
export MHVP_REDIS_URL="${MHVP_REDIS_URL:-redis://127.0.0.1:6379/0}"
export MHVP_CELERY_BROKER_URL="${MHVP_CELERY_BROKER_URL:-redis://127.0.0.1:6379/1}"
export MHVP_CELERY_RESULT_BACKEND="${MHVP_CELERY_RESULT_BACKEND:-redis://127.0.0.1:6379/2}"
export MHVP_LOG_FORMAT="${MHVP_LOG_FORMAT:-console}"

cd "$API_DIR"

echo "==> migrate"
uv run alembic upgrade head

if [ -z "${MHVP_MASTER_KEY:-}" ] || [ -z "${MHVP_JWT_PRIVATE_KEY:-}" ]; then
  echo "==> generate throwaway auth keys"
  keys=$(uv run python -m mhvp.core.auth.keys)
  master=$(printf '%s\n' "$keys" | sed -n 's/^MHVP_MASTER_KEY=//p')
  pem=$(printf '%s\n' "$keys" | sed -n 's/^MHVP_JWT_PRIVATE_KEY="\(.*\)"$/\1/p')
  export MHVP_MASTER_KEY="${MHVP_MASTER_KEY:-$master}"
  # The generator prints the PEM with literal \n; turn them into real newlines.
  export MHVP_JWT_PRIVATE_KEY="${MHVP_JWT_PRIVATE_KEY:-$(printf '%b' "$pem")}"
fi

export MHVP_SEED_ADMIN_EMAIL="${MHVP_SEED_ADMIN_EMAIL:-e2e-$(date +%s)-$$@example.org}"
export MHVP_SEED_ADMIN_PASSWORD="${MHVP_SEED_ADMIN_PASSWORD:-$(openssl rand -hex 16)}"
export MHVP_SEED_ADMIN_NAME="${MHVP_SEED_ADMIN_NAME:-E2E Administrator}"

echo "==> seed (admin ${MHVP_SEED_ADMIN_EMAIL})"
uv run python -m mhvp.platform.seed

echo "==> start API on port ${API_PORT}"
# Outside test-results/: Playwright empties that directory on start.
LOG="${MHVP_E2E_API_LOG:-$ROOT/apps/web-crm/playwright-report-api.log}"
mkdir -p "$(dirname -- "$LOG")"
uv run uvicorn mhvp.main:app --host 127.0.0.1 --port "$API_PORT" >"$LOG" 2>&1 &
API_PID=$!
cleanup() { kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/health/live" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$API_PID" 2>/dev/null; then echo "API exited, see $LOG" >&2; cat "$LOG" >&2; exit 1; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/health/live" >/dev/null

cd "$ROOT"
export MHVP_API_INTERNAL_URL="http://127.0.0.1:${API_PORT}"
export E2E_ADMIN_EMAIL="$MHVP_SEED_ADMIN_EMAIL"
export E2E_ADMIN_PASSWORD="$MHVP_SEED_ADMIN_PASSWORD"

echo "==> build CRM"
pnpm --filter @mhvp/web-crm build

echo "==> Playwright (E2E_BACKEND=1)"
E2E_BACKEND=1 pnpm --filter @mhvp/web-crm e2e
