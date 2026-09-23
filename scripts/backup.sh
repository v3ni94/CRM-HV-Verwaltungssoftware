#!/usr/bin/env bash
# Daily full backup (MASTER-PROMPT 3.5, 6.9.5): pg_dump custom format, encrypted with age,
# checksum, 30 day rolling retention. Object storage sync and WAL archiving run separately
# (docs/runbooks/backup.md). Backup is operational protection, not the archive (E05).
set -euo pipefail

: "${PGHOST:?PGHOST must be set}" "${PGDATABASE:?PGDATABASE must be set}"
: "${BACKUP_DIR:?BACKUP_DIR must be set}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
DUMP="$BACKUP_DIR/mhvp-$STAMP.dump"

pg_dump --format=custom --no-owner --no-privileges --file="$DUMP" "$PGDATABASE"
if [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
  age --recipient "$BACKUP_AGE_RECIPIENT" --output "$DUMP.age" "$DUMP"
  rm -f "$DUMP"
  DUMP="$DUMP.age"
elif [[ "${BACKUP_ALLOW_UNENCRYPTED:-0}" != "1" ]]; then
  rm -f "$DUMP"
  echo "backup: BACKUP_AGE_RECIPIENT missing; unencrypted backups are refused (3.5)" >&2
  exit 3
fi
sha256sum "$DUMP" > "$DUMP.sha256"
find "$BACKUP_DIR" -name 'mhvp-*.dump*' -mtime "+$RETENTION_DAYS" -delete
echo "backup: $DUMP"
