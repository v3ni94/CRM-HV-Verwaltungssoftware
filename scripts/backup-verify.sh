#!/usr/bin/env bash
# Restore test (M9 acceptance, job ops.backup_verify): restores the newest backup into a
# throwaway database, compares schema revision and row counts of core tables with the source,
# then drops the throwaway database. Exit code 0 only if every check passes.
# BACKUP_COMPOSE: run psql/pg_restore inside the postgres container (see scripts/backup.sh).
set -euo pipefail

: "${PGDATABASE:?PGDATABASE must be set}"
: "${BACKUP_DIR:?BACKUP_DIR must be set}"
[[ -n "${BACKUP_COMPOSE:-}" ]] || : "${PGHOST:?PGHOST must be set (or BACKUP_COMPOSE)}"
TARGET="${RESTORE_DATABASE:-mhvp_restore_check}"
[[ "$TARGET" =~ ^[a-z_][a-z0-9_]*$ && "$TARGET" != "$PGDATABASE" ]] \
  || { echo "backup-verify: invalid RESTORE_DATABASE" >&2; exit 2; }
LATEST="$(ls -1t "$BACKUP_DIR"/mhvp-2*.dump "$BACKUP_DIR"/mhvp-2*.dump.age 2>/dev/null | head -1 || true)"
[[ -n "$LATEST" ]] || { echo "backup-verify: no backup in $BACKUP_DIR" >&2; exit 1; }
# Read by the job ops.backup_verify (A67) for the operating metrics; keep the prefix.
echo "backup-verify: file $LATEST"
(cd "$(dirname "$LATEST")" && sha256sum --check --status "$(basename "$LATEST").sha256") \
  || { echo "backup-verify: checksum mismatch" >&2; exit 1; }

if [[ -n "${BACKUP_COMPOSE:-}" ]]; then
  # shellcheck disable=SC2086
  pg() { local tool="$1"; shift; $BACKUP_COMPOSE exec -T postgres "$tool" -U postgres "$@"; }
else
  pg() { local tool="$1"; shift; "$tool" "$@"; }
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"; pg psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\"" >/dev/null 2>&1 || true' EXIT
DUMP="$LATEST"
if [[ "$LATEST" == *.age ]]; then
  : "${BACKUP_AGE_IDENTITY:?BACKUP_AGE_IDENTITY must be set to decrypt}"
  age --decrypt --identity "$BACKUP_AGE_IDENTITY" --output "$WORK/restore.dump" "$LATEST"
  DUMP="$WORK/restore.dump"
fi

pg psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\"" -c "CREATE DATABASE \"$TARGET\""
pg pg_restore --no-owner --no-privileges --exit-on-error --dbname="$TARGET" < "$DUMP"

query() { pg psql -tA -d "$1" -c "$2"; }
fail=0
check() {
  local label="$1" sql="$2" src dst
  src="$(query "$PGDATABASE" "$sql")"; dst="$(query "$TARGET" "$sql")"
  if [[ "$src" == "$dst" ]]; then echo "ok   $label: $dst"; else echo "FAIL $label: source=$src restore=$dst"; fail=1; fi
}
check "alembic revision" "SELECT version_num FROM alembic_version"
for table in tenant app_user contact property unit contract document; do
  n="$(query "$TARGET" "SELECT count(*) FROM $table" 2>/dev/null || echo missing)"
  [[ "$n" == missing ]] && { echo "FAIL table $table missing"; fail=1; } || echo "ok   $table rows: $n"
done
exit "$fail"
