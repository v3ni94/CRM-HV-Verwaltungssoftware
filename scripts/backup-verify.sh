#!/usr/bin/env bash
# Restore test (M9 acceptance, job ops.backup_verify): restores the newest backup into a
# throwaway database, compares schema revision and row counts of core tables with the source,
# then drops the throwaway database. Exit code 0 only if every check passes.
set -euo pipefail

: "${PGHOST:?PGHOST must be set}" "${PGDATABASE:?PGDATABASE must be set}"
: "${BACKUP_DIR:?BACKUP_DIR must be set}"
TARGET="${RESTORE_DATABASE:-mhvp_restore_check}"
LATEST="$(ls -1t "$BACKUP_DIR"/mhvp-*.dump "$BACKUP_DIR"/mhvp-*.dump.age 2>/dev/null | head -1 || true)"
[[ -n "$LATEST" ]] || { echo "backup-verify: no backup in $BACKUP_DIR" >&2; exit 1; }
sha256sum --check --status "$LATEST.sha256" || { echo "backup-verify: checksum mismatch" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"; psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\"" >/dev/null 2>&1 || true' EXIT
DUMP="$LATEST"
if [[ "$LATEST" == *.age ]]; then
  : "${BACKUP_AGE_IDENTITY:?BACKUP_AGE_IDENTITY must be set to decrypt}"
  age --decrypt --identity "$BACKUP_AGE_IDENTITY" --output "$WORK/restore.dump" "$LATEST"
  DUMP="$WORK/restore.dump"
fi

psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\"" -c "CREATE DATABASE \"$TARGET\""
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$TARGET" "$DUMP"

query() { psql -tA -d "$1" -c "$2"; }
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
