#!/usr/bin/env bash
# Restore drill (D47, M9-05, B18, M27-03, MASTER-PROMPT 16 Betrieb, 18 Marktreife).
#
# Extends scripts/backup-verify.sh: restores the newest off-site run (Hetzner S3, age
# encrypted; docs/runbooks/backup.md section "Off-site-Kopie") into a throwaway database AND
# a throwaway object-store directory, compares checksums and row/object counts against the
# running production instance, measures wall-clock duration and writes a Markdown protocol
# to docs/reviews/restore-YYYY-MM-DD.md. It never writes to production and never touches the
# real backup files (everything downloaded goes into a temporary work directory, removed on
# exit). No real credentials are read from this script; every value comes from the
# environment or an --env-file the caller points at (see infra/env.backup.example).
#
# Usage (on a restore machine or the server, never the productive database):
#   infra/scripts/restore-drill.sh [--env-file /opt/mhvp/.env.backup] [--stamp <STAMP>]
#                                   [--skip-objects] [--keep-work]
#
# Required environment (same names as scripts/backup-offsite.sh / backup-verify.sh):
#   PGDATABASE, PGHOST, PGUSER (or BACKUP_COMPOSE), BACKUP_S3_ENDPOINT_URL,
#   BACKUP_S3_REGION, BACKUP_S3_BUCKET, BACKUP_S3_ACCESS_KEY_ID,
#   BACKUP_S3_SECRET_ACCESS_KEY, BACKUP_S3_PREFIX, BACKUP_AGE_IDENTITY (private key file,
#   mounted only for the drill, see docs/runbooks/backup.md "Schluesselverwahrung"),
#   RESTORE_DATABASE (default mhvp_restore_drill), RESTORE_OBJECTSTORE_DIR (default a
#   directory under the work dir), REPO_ROOT (default: repository root of this script).
#
# Exit codes: 0 all checks passed, 1 a check failed (protocol still written with the failure),
# 2 usage or missing configuration. Nothing here replaces the quarterly point-in-time-recovery
# drill in docs/runbooks/backup.md ("Wiederherstellung (Basisbackup plus WAL-Replay)").
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ENV_FILE=""
STAMP=""
SKIP_OBJECTS=0
KEEP_WORK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) [[ $# -ge 2 ]] || { echo "restore-drill: --env-file needs a path" >&2; exit 2; }; ENV_FILE="$2"; shift 2 ;;
    --stamp) [[ $# -ge 2 ]] || { echo "restore-drill: --stamp needs a value" >&2; exit 2; }; STAMP="$2"; shift 2 ;;
    --skip-objects) SKIP_OBJECTS=1; shift ;;
    --keep-work) KEEP_WORK=1; shift ;;
    -h|--help) sed -n '2,24p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "restore-drill: unknown argument $1" >&2; exit 2 ;;
  esac
done

if [[ -n "$ENV_FILE" ]]; then
  [[ -r "$ENV_FILE" ]] || { echo "restore-drill: cannot read $ENV_FILE" >&2; exit 2; }
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${PGDATABASE:?PGDATABASE must be set}"
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET must be set}"
: "${BACKUP_S3_ACCESS_KEY_ID:?BACKUP_S3_ACCESS_KEY_ID must be set}"
: "${BACKUP_S3_SECRET_ACCESS_KEY:?BACKUP_S3_SECRET_ACCESS_KEY must be set}"
: "${BACKUP_AGE_IDENTITY:?BACKUP_AGE_IDENTITY must be set (private age key, drill only)}"
[[ -r "$BACKUP_AGE_IDENTITY" ]] || { echo "restore-drill: cannot read BACKUP_AGE_IDENTITY" >&2; exit 2; }
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-mhvp}"
RESTORE_DATABASE="${RESTORE_DATABASE:-mhvp_restore_drill}"
[[ "$RESTORE_DATABASE" =~ ^[a-z_][a-z0-9_]*$ && "$RESTORE_DATABASE" != "$PGDATABASE" ]] \
  || { echo "restore-drill: invalid RESTORE_DATABASE" >&2; exit 2; }

WORK="$(mktemp -d)"
cleanup() {
  if [[ "$KEEP_WORK" == 1 ]]; then
    echo "restore-drill: work directory kept at $WORK" >&2
  else
    rm -rf "$WORK"
  fi
  if [[ -n "${BACKUP_COMPOSE:-}" ]]; then
    $BACKUP_COMPOSE exec -T postgres psql -q -U postgres -d postgres \
      -c "DROP DATABASE IF EXISTS \"$RESTORE_DATABASE\"" >/dev/null 2>&1 || true
  else
    psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$RESTORE_DATABASE\"" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ -n "${BACKUP_COMPOSE:-}" ]]; then
  pg() { local tool="$1"; shift; $BACKUP_COMPOSE exec -T postgres "$tool" -U postgres "$@"; }
else
  pg() { local tool="$1"; shift; "$tool" "$@"; }
fi
query() { pg psql -tA -d "$1" -c "$2"; }

s3() {
  python3 - "$@" <<'PY'
import sys, boto3
cmd = sys.argv[1]
s3 = boto3.client(
    "s3",
    endpoint_url=__import__("os").environ.get("BACKUP_S3_ENDPOINT_URL") or None,
    region_name=__import__("os").environ.get("BACKUP_S3_REGION") or None,
    aws_access_key_id=__import__("os").environ["BACKUP_S3_ACCESS_KEY_ID"],
    aws_secret_access_key=__import__("os").environ["BACKUP_S3_SECRET_ACCESS_KEY"],
)
bucket = __import__("os").environ["BACKUP_S3_BUCKET"]
if cmd == "latest-run":
    prefix = sys.argv[2]
    paginator = s3.get_paginator("list_objects_v2")
    stamps = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/runs/", Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            part = cp["Prefix"][len(f"{prefix}/runs/"):].rstrip("/")
            if part:
                stamps.add(part)
    if not stamps:
        sys.exit(1)
    print(sorted(stamps)[-1])
elif cmd == "list-objects":
    prefix = sys.argv[2]
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/objects/"):
        for obj in page.get("Contents", []):
            print(obj["Key"])
elif cmd == "download":
    key, dest = sys.argv[2], sys.argv[3]
    s3.download_file(bucket, key, dest)
else:
    sys.exit(f"unknown s3 subcommand {cmd}")
PY
}

START_TS="$(date -u +%s)"
NOW="$(date -u +%Y-%m-%d)"
mkdir -p "$REPO_ROOT/docs/reviews"
PROTOCOL="$REPO_ROOT/docs/reviews/restore-$NOW.md"

if [[ -z "$STAMP" ]]; then
  STAMP="$(s3 latest-run "$BACKUP_S3_PREFIX" || true)"
  [[ -n "$STAMP" ]] || { echo "restore-drill: no run found under $BACKUP_S3_PREFIX/runs/" >&2; exit 1; }
fi
echo "restore-drill: using run $STAMP"

fail=0
declare -a ROWS

add_row() { ROWS+=("$1"); }

# 1. Datenbank herunterladen, Prüfsumme, entschlüsseln, einspielen -----------------------------
DUMP_KEY="$BACKUP_S3_PREFIX/runs/$STAMP/db/mhvp-$STAMP.dump.age"
SHA_KEY="$DUMP_KEY.sha256"
DUMP_ENC="$WORK/mhvp-$STAMP.dump.age"
if s3 download "$DUMP_KEY" "$DUMP_ENC" && s3 download "$SHA_KEY" "$DUMP_ENC.sha256"; then
  (cd "$WORK" && sha256sum --check --status "$(basename "$DUMP_ENC").sha256") \
    && add_row "ok   Datenbank-Prüfsumme (S3)" || { add_row "FAIL Datenbank-Prüfsumme (S3)"; fail=1; }
  age --decrypt --identity "$BACKUP_AGE_IDENTITY" --output "$WORK/restore.dump" "$DUMP_ENC" \
    && add_row "ok   Datenbank entschlüsselt" || { add_row "FAIL Datenbank-Entschlüsselung"; fail=1; }
  if [[ -f "$WORK/restore.dump" ]]; then
    if [[ -n "${BACKUP_COMPOSE:-}" ]]; then
      $BACKUP_COMPOSE exec -T postgres psql -q -U postgres -d postgres \
        -c "DROP DATABASE IF EXISTS \"$RESTORE_DATABASE\"" \
        -c "CREATE DATABASE \"$RESTORE_DATABASE\""
      $BACKUP_COMPOSE exec -T postgres pg_restore --no-owner --no-privileges \
        --exit-on-error --dbname="$RESTORE_DATABASE" < "$WORK/restore.dump" \
        && add_row "ok   pg_restore in $RESTORE_DATABASE" || { add_row "FAIL pg_restore"; fail=1; }
    else
      psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$RESTORE_DATABASE\"" \
        -c "CREATE DATABASE \"$RESTORE_DATABASE\""
      pg_restore --no-owner --no-privileges --exit-on-error --dbname="$RESTORE_DATABASE" \
        < "$WORK/restore.dump" \
        && add_row "ok   pg_restore in $RESTORE_DATABASE" || { add_row "FAIL pg_restore"; fail=1; }
    fi
  fi
else
  add_row "FAIL Download der Datenbanksicherung ($DUMP_KEY)"; fail=1
fi

# 2. Vergleich Alembic-Revision und Kerntabellen -----------------------------------------------
if [[ -f "$WORK/restore.dump" ]]; then
  src_rev="$(query "$PGDATABASE" "SELECT version_num FROM alembic_version")"
  dst_rev="$(query "$RESTORE_DATABASE" "SELECT version_num FROM alembic_version" 2>/dev/null || echo missing)"
  if [[ "$src_rev" == "$dst_rev" ]]; then
    add_row "ok   Alembic-Revision: $dst_rev"
  else
    add_row "FAIL Alembic-Revision: Produktion=$src_rev Wiederherstellung=$dst_rev"; fail=1
  fi
  for table in tenant app_user contact property unit contract document; do
    src_n="$(query "$PGDATABASE" "SELECT count(*) FROM $table" 2>/dev/null || echo missing)"
    dst_n="$(query "$RESTORE_DATABASE" "SELECT count(*) FROM $table" 2>/dev/null || echo missing)"
    if [[ "$src_n" == "$dst_n" && "$src_n" != missing ]]; then
      add_row "ok   Tabelle $table: $dst_n Zeilen"
    else
      add_row "FAIL Tabelle $table: Produktion=$src_n Wiederherstellung=$dst_n"; fail=1
    fi
  done
fi

# 3. Objektspeicher: Stichprobe je Objekt in ein temporäres Verzeichnis --------------------------
RESTORE_OBJECTSTORE_DIR="${RESTORE_OBJECTSTORE_DIR:-$WORK/objectstore}"
mkdir -p "$RESTORE_OBJECTSTORE_DIR"
if [[ "$SKIP_OBJECTS" == 1 ]]; then
  add_row "übersprungen Objektspeicher (--skip-objects)"
else
  count=0
  ok=0
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    count=$((count + 1))
    name="$(basename "$key")"
    if s3 download "$key" "$RESTORE_OBJECTSTORE_DIR/$name" 2>/dev/null; then
      dec="$RESTORE_OBJECTSTORE_DIR/${name%.age}"
      if age --decrypt --identity "$BACKUP_AGE_IDENTITY" --output "$dec" \
           "$RESTORE_OBJECTSTORE_DIR/$name" 2>/dev/null; then
        ok=$((ok + 1))
      fi
    fi
  done < <(s3 list-objects "$BACKUP_S3_PREFIX" 2>/dev/null || true)
  if [[ "$count" -gt 0 ]]; then
    add_row "ok   Objektspeicher: $ok von $count Objekten entschlüsselt (Verzeichnis $RESTORE_OBJECTSTORE_DIR)"
    [[ "$ok" == "$count" ]] || { add_row "FAIL Objektspeicher: nicht alle Objekte entschlüsselbar"; fail=1; }
  else
    add_row "FAIL Objektspeicher: keine Objekte unter $BACKUP_S3_PREFIX/objects/ gefunden"; fail=1
  fi
fi

END_TS="$(date -u +%s)"
DURATION=$((END_TS - START_TS))

{
  echo "# Wiederherstellungsprobe $NOW"
  echo
  echo "Lauf: \`$STAMP\`. Ziel-Datenbank: \`$RESTORE_DATABASE\` (verworfen nach diesem Lauf)."
  echo "Objektverzeichnis: \`$RESTORE_OBJECTSTORE_DIR\` (temporär, kein Produktionsverzeichnis)."
  echo "Dauer: ${DURATION}s. Aufgerufen mit \`infra/scripts/restore-drill.sh\`."
  echo
  echo "## Ergebnis"
  echo
  for row in "${ROWS[@]}"; do
    echo "* $row"
  done
  echo
  if [[ "$fail" == 0 ]]; then
    echo "Gesamtergebnis: bestanden."
  else
    echo "Gesamtergebnis: FEHLGESCHLAGEN. Siehe Zeilen mit FAIL oben. Betreiber informieren"
    echo "(Runbook \`docs/runbooks/backup.md\`, Abschnitt Off-site-Kopie und WAL-Archivierung)."
  fi
  echo
  echo "Kein echtes Zugangsdatum, kein Schlüssel und kein Bucket-Name dieses Laufs ist in diesem"
  echo "Protokoll enthalten außer dem Lauf-Stempel; Werte kommen ausschließlich aus der Umgebung"
  echo "des Aufrufers (siehe \`infra/env.backup.example\`)."
} > "$PROTOCOL"

echo "restore-drill: Protokoll geschrieben nach $PROTOCOL"
exit "$fail"
