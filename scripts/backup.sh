#!/usr/bin/env bash
# Daily full backup (MASTER-PROMPT 3.5, 6.9.5): pg_dump custom format, encrypted with age,
# checksum, rolling retention. Backup is operational protection, not the archive (E05).
#
# Database access:
#   host tools (default): pg_dump with PGHOST, PGUSER, PGPASSWORD, PGDATABASE
#   BACKUP_COMPOSE="docker compose -p mhvp --env-file .env.prod -f infra/compose.yaml -f infra/compose.prod.yaml":
#       pg_dump runs inside the postgres container; no client tools on the server needed.
# Optional:
#   BACKUP_OBJECTSTORE_VOLUME=mhvp_objectstore-data  also archives the document store volume
#   BACKUP_JOURNAL_CMD="docker compose ... exec -T api python -m mhvp.documents.export_deletions"
#       Deletion journal (D47, GAK-405): exported with every dump as mhvp-deletions-<STAMP>.json,
#       encrypted like the dump and copied off-site with it. Default in compose mode:
#       $BACKUP_COMPOSE exec -T api python -m mhvp.documents.export_deletions. Without a command
#       the backup is refused (exit 3), unless BACKUP_SKIP_JOURNAL=1 is set on purpose.
#   BACKUP_JOURNAL_SINCE=2000-01-01                   start of the exported journal (ISO date)
#   BACKUP_REMOTE=user@host:/path                    copies the new files off the server (rsync)
#   ALERT_WEBHOOK_URL=https://...                    on any failure a short JSON message is posted
#                                                    there (same target as healthcheck.sh, M9-04;
#                                                    e.g. an Uptime Kuma push URL with status=down,
#                                                    see docs/runbooks/monitoring.md). The platform
#                                                    has no system mail sender of its own; e-mail
#                                                    goes out through the Uptime Kuma notification.
set -euo pipefail

# Failure alarm (M9-04) on any non-zero exit, also from pipelines and the refusal paths:
# journal line plus optional webhook; no personal data, no secrets.
alert_failure() {
  local status=$?
  (( status == 0 )) && return 0
  # No half written files of this run: the health check must not count them as a backup.
  [[ -n "${STAMP:-}" ]] && rm -f "$BACKUP_DIR"/mhvp-*"$STAMP"*
  local text="MHVP $(hostname): Backup fehlgeschlagen (Exit $status)"
  echo "backup: $text" >&2
  if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    local body
    body="$(printf '{"text":"%s"}' "${text//\"/\'}")"
    curl -fsS --max-time 10 -H 'content-type: application/json' -d "$body" "$ALERT_WEBHOOK_URL" >/dev/null || true
  fi
}
trap alert_failure EXIT

: "${PGDATABASE:?PGDATABASE must be set}"
: "${BACKUP_DIR:?BACKUP_DIR must be set}"
[[ -n "${BACKUP_COMPOSE:-}" ]] || : "${PGHOST:?PGHOST must be set (or BACKUP_COMPOSE)}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
umask 077

if [[ -z "${BACKUP_AGE_RECIPIENT:-}" && "${BACKUP_ALLOW_UNENCRYPTED:-0}" != "1" ]]; then
  echo "backup: BACKUP_AGE_RECIPIENT missing; unencrypted backups are refused (3.5)" >&2
  exit 3
fi

JOURNAL_CMD="${BACKUP_JOURNAL_CMD:-}"
if [[ -z "$JOURNAL_CMD" && -n "${BACKUP_COMPOSE:-}" ]]; then
  JOURNAL_CMD="$BACKUP_COMPOSE exec -T api python -m mhvp.documents.export_deletions"
fi
if [[ -z "$JOURNAL_CMD" && "${BACKUP_SKIP_JOURNAL:-0}" != "1" ]]; then
  echo "backup: BACKUP_JOURNAL_CMD missing; the deletion journal must be backed up (D47, 7.11)" >&2
  exit 3
fi

# Writes stdin to $1 (encrypted with age when a recipient is set) plus a checksum file.
store() {
  local out="$1"
  if [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
    out="$out.age"
    age --recipient "$BACKUP_AGE_RECIPIENT" --output "$out.part"
  else
    cat > "$out.part"
  fi
  mv "$out.part" "$out"
  (cd "$BACKUP_DIR" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
  echo "$out"
}

if [[ -n "${BACKUP_COMPOSE:-}" ]]; then
  # shellcheck disable=SC2086 # BACKUP_COMPOSE is a command line on purpose
  $BACKUP_COMPOSE exec -T postgres pg_dump -U postgres --format=custom --no-owner --no-privileges "$PGDATABASE" \
    | store "$BACKUP_DIR/mhvp-$STAMP.dump"
else
  pg_dump --format=custom --no-owner --no-privileges "$PGDATABASE" | store "$BACKUP_DIR/mhvp-$STAMP.dump"
fi

if [[ -n "$JOURNAL_CMD" ]]; then
  # Deletion journal next to the dump (D47): after a total loss of the database it is the only
  # record of lawful deletions made after the dump. A failing export fails the backup.
  # shellcheck disable=SC2086 # the journal command is a command line on purpose
  $JOURNAL_CMD --since "${BACKUP_JOURNAL_SINCE:-2000-01-01}" --out - \
    | store "$BACKUP_DIR/mhvp-deletions-$STAMP.json"
fi

if [[ -n "${BACKUP_OBJECTSTORE_VOLUME:-}" ]]; then
  docker run --rm -v "$BACKUP_OBJECTSTORE_VOLUME:/data:ro" alpine:3.22 tar -C /data -cf - . \
    | store "$BACKUP_DIR/mhvp-objects-$STAMP.tar"
fi

find "$BACKUP_DIR" -name 'mhvp-*' -type f -mtime "+$RETENTION_DAYS" -delete

if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  # Off-site copy; retention on the target is managed there (never --delete from here).
  rsync -a --partial "$BACKUP_DIR"/mhvp-*"$STAMP"* "$BACKUP_REMOTE/"
fi
if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
  # Off-site copy to the operator's S3 compatible object storage (M9-02, 26.09.2026);
  # a failure there exits non zero and fires the alarm above.
  "$(dirname "${BASH_SOURCE[0]}")/backup-offsite.sh" --stamp "$STAMP"
fi
echo "backup: done $STAMP"
