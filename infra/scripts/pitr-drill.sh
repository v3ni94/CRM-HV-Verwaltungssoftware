#!/usr/bin/env bash
# Point-in-time-recovery drill (GAJ-505, MASTER-PROMPT 3.5 and 16 Backup, M9).
#
# Restores a physical base backup plus archived WAL segments into a throwaway PostgreSQL
# cluster up to a recovery target time, measures the wall-clock duration against the RTO and
# writes a Markdown protocol. It never touches the productive cluster: the restore runs in a
# temporary data directory, listens only on a Unix socket in the work directory and is
# stopped and removed on exit (unless --keep-work).
#
# Modes:
#   --selftest
#       Builds its own throwaway primary (initdb, archive_mode=on), takes a base backup with
#       pg_basebackup -X none, writes rows before and after a recorded target time, then
#       restores with WAL replay and checks that exactly the rows up to the target are
#       present. Used by CI (job pitr-drill) and make pitr-drill-selftest.
#   --base <base.tar|base.tar.age|dir> --wal-dir <dir> --target '<timestamp with zone>'
#       Real drill per docs/runbooks/backup.md section "Wiederherstellung (Basisbackup plus
#       WAL-Replay)". .age files (base and WAL) are decrypted with BACKUP_AGE_IDENTITY into
#       the work directory. Checks: recovery reached and promoted, alembic_version readable,
#       row count of journal_entry (if the table exists).
#
# Options: --protocol <file> (default: docs/reviews/pitr-YYYY-MM-DD.md in real mode, the work
# directory in selftest mode), --keep-work, --dry-run (tools and arguments only).
#
# Environment: PG_BIN (directory with initdb, pg_ctl, postgres, psql, pg_basebackup; default
# from pg_config or /usr/lib/postgresql/<newest>/bin), PITR_RUN_AS (user for the server
# processes when run as root, default postgres), PITR_RTO_SECONDS (default 14400, the RTO of
# under 4 hours from MASTER-PROMPT 3.5 / section 16 table "Backup", as used in
# docs/runbooks/leistungsmessung.md), BACKUP_AGE_IDENTITY (only for .age input).
#
# Exit codes: 0 restore and checks passed within the RTO, 1 a check failed or the RTO was
# exceeded (protocol still written), 2 usage or missing tools.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MODE=""
BASE=""
WAL_DIR=""
TARGET=""
PROTOCOL=""
KEEP_WORK=0
DRY_RUN=0
RTO="${PITR_RTO_SECONDS:-14400}"

die() { echo "pitr-drill: $*" >&2; exit 2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --selftest) MODE=selftest; shift ;;
    --base) [[ $# -ge 2 ]] || die "--base needs a path"; BASE="$2"; MODE="${MODE:-real}"; shift 2 ;;
    --wal-dir) [[ $# -ge 2 ]] || die "--wal-dir needs a path"; WAL_DIR="$2"; shift 2 ;;
    --target) [[ $# -ge 2 ]] || die "--target needs a timestamp"; TARGET="$2"; shift 2 ;;
    --protocol) [[ $# -ge 2 ]] || die "--protocol needs a path"; PROTOCOL="$2"; shift 2 ;;
    --keep-work) KEEP_WORK=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,33p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown argument $1" ;;
  esac
done
[[ -n "$MODE" ]] || die "choose --selftest or --base/--wal-dir/--target"
[[ "$RTO" =~ ^[0-9]+$ ]] || die "PITR_RTO_SECONDS must be an integer"
if [[ "$MODE" == real ]]; then
  [[ -n "$WAL_DIR" && -n "$TARGET" ]] || die "--base needs --wal-dir and --target"
  [[ -e "$BASE" ]] || die "base backup $BASE not found"
  [[ -d "$WAL_DIR" ]] || die "WAL directory $WAL_DIR not found"
fi

if [[ -z "${PG_BIN:-}" ]]; then
  if command -v pg_config >/dev/null 2>&1 && [[ -x "$(pg_config --bindir)/pg_ctl" ]]; then
    PG_BIN="$(pg_config --bindir)"
  else
    PG_BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -n1 || true)"
  fi
fi
for t in initdb pg_ctl postgres psql pg_basebackup; do
  [[ -x "$PG_BIN/$t" ]] || die "missing $t in PG_BIN=$PG_BIN"
done
command -v tar >/dev/null || die "missing tar"
if [[ "$MODE" == real ]] && { [[ "$BASE" == *.age ]] || compgen -G "$WAL_DIR/*.age" >/dev/null; }; then
  command -v age >/dev/null || die "missing age for encrypted input"
  [[ -r "${BACKUP_AGE_IDENTITY:-}" ]] || die "BACKUP_AGE_IDENTITY must point to a readable key"
fi
RUN_AS="${PITR_RUN_AS:-postgres}"
if [[ "$(id -u)" == 0 ]]; then
  id "$RUN_AS" >/dev/null 2>&1 || die "running as root needs PITR_RUN_AS (user $RUN_AS missing)"
  as_pg() { runuser -u "$RUN_AS" -- "$@"; }
else
  as_pg() { "$@"; }
fi
if [[ "$DRY_RUN" == 1 ]]; then
  echo "pitr-drill: dry run ok (mode $MODE, PG_BIN $PG_BIN, RTO ${RTO}s)"
  exit 0
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/mhvp-pitr.XXXXXX")"
chmod 755 "$WORK"
[[ "$(id -u)" == 0 ]] && chown "$RUN_AS" "$WORK"
SOCK="$WORK/sock"; as_pg mkdir -p "$SOCK"
PORT=55432
cleanup() {
  for d in "$WORK/primary" "$WORK/restore"; do
    [[ -f "$d/postmaster.pid" ]] && as_pg "$PG_BIN/pg_ctl" -D "$d" -m immediate stop >/dev/null 2>&1 || true
  done
  if [[ "$KEEP_WORK" == 1 ]]; then echo "pitr-drill: work directory kept: $WORK"; else rm -rf "$WORK"; fi
}
trap cleanup EXIT
psql_q() { as_pg "$PG_BIN/psql" -h "$SOCK" -p "$PORT" -U postgres -d postgres -XAtq -v ON_ERROR_STOP=1 -c "$1"; }
start_pg() { as_pg "$PG_BIN/pg_ctl" -D "$1" -w -t 600 -l "$1.log" -o "-p $PORT -k $SOCK -c listen_addresses=''" start >/dev/null; }

ROWS=()
fail=0
check() { if [[ "$2" == "$3" ]]; then ROWS+=("OK $1: $2"); else ROWS+=("FAIL $1: ist $2, erwartet $3"); fail=1; fi; }

EXPECTED=""
if [[ "$MODE" == selftest ]]; then
  ARCH="$WORK/wal-archive"; as_pg mkdir -p "$ARCH"
  as_pg "$PG_BIN/initdb" -D "$WORK/primary" -U postgres -A trust >/dev/null
  cat >> "$WORK/primary/postgresql.conf" <<EOF
wal_level = replica
archive_mode = on
archive_command = 'test ! -f $ARCH/%f && cp %p $ARCH/%f'
max_wal_senders = 2
EOF
  start_pg "$WORK/primary"
  psql_q "CREATE TABLE pitr_probe(id int PRIMARY KEY, at timestamptz DEFAULT clock_timestamp()); INSERT INTO pitr_probe(id) SELECT g FROM generate_series(1,100) g;"
  as_pg "$PG_BIN/pg_basebackup" -h "$SOCK" -p "$PORT" -U postgres -D "$WORK/base" -Ft -X none -c fast >/dev/null 2>&1
  psql_q "INSERT INTO pitr_probe(id) SELECT g FROM generate_series(101,150) g;"
  sleep 1.2
  TARGET="$(psql_q "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS.US')||'+00'")"
  sleep 1.2
  psql_q "INSERT INTO pitr_probe(id) SELECT g FROM generate_series(151,175) g;"
  psql_q "SELECT pg_switch_wal();" >/dev/null
  # wait until the switched segment is archived
  for _ in $(seq 1 60); do
    [[ "$(psql_q "SELECT last_archived_wal IS NOT NULL AND last_archived_wal = (SELECT pg_walfile_name(pg_current_wal_lsn() - 1)) FROM pg_stat_archiver")" == t ]] && break
    sleep 0.5
  done
  as_pg "$PG_BIN/pg_ctl" -D "$WORK/primary" -m fast stop >/dev/null
  BASE="$WORK/base/base.tar"
  WAL_DIR="$ARCH"
  EXPECTED=150
  : "${PROTOCOL:=$WORK/pitr-selftest.md}"
fi
: "${PROTOCOL:=$REPO_ROOT/docs/reviews/pitr-$(date -u +%F).md}"

# --- restore (timed) -------------------------------------------------------------------
T0=$(date +%s)
R="$WORK/restore"; as_pg mkdir -p "$R"; chmod 700 "$R"; [[ "$(id -u)" == 0 ]] && chown "$RUN_AS" "$R"
if [[ -d "$BASE" ]]; then
  cp -a "$BASE/." "$R/"
elif [[ "$BASE" == *.age ]]; then
  age -d -i "$BACKUP_AGE_IDENTITY" "$BASE" | tar -x -C "$R"
else
  tar -x -C "$R" -f "$BASE"
fi
WAL_USE="$WORK/wal"; mkdir -p "$WAL_USE"
for f in "$WAL_DIR"/*; do
  [[ -f "$f" ]] || continue
  b="$(basename "$f")"
  if [[ "$b" == *.age ]]; then age -d -i "$BACKUP_AGE_IDENTITY" -o "$WAL_USE/${b%.age}" "$f"; else cp "$f" "$WAL_USE/$b"; fi
done
[[ "$(id -u)" == 0 ]] && chown -R "$RUN_AS" "$R" "$WAL_USE"
chmod 700 "$R"
rm -f "$R/postmaster.pid"
# Never inherit the archive settings of the source; the restore must not write anywhere.
cat >> "$R/postgresql.auto.conf" <<EOF
archive_mode = off
restore_command = 'cp $WAL_USE/%f %p'
recovery_target_time = '$TARGET'
recovery_target_action = 'promote'
EOF
as_pg touch "$R/recovery.signal"
start_ok=1
start_pg "$R" || start_ok=0
promoted=f
if [[ "$start_ok" == 1 ]]; then
  for _ in $(seq 1 1200); do
    promoted="$(psql_q "SELECT NOT pg_is_in_recovery()" 2>/dev/null || echo f)"
    [[ "$promoted" == t ]] && break
    sleep 0.5
  done
fi
T1=$(date +%s)
DURATION=$((T1 - T0))
check "Wiederherstellung bis Zielzeitpunkt abgeschlossen und hochgestuft" "$promoted" t
if [[ "$promoted" == t ]]; then
  if [[ "$MODE" == selftest ]]; then
    check "Zeilen bis Zielzeitpunkt (pitr_probe)" "$(psql_q "SELECT count(*) FROM pitr_probe")" "$EXPECTED"
  else
    DBN="${PITR_DATABASE:-mhvp}"
    rev="$(as_pg "$PG_BIN/psql" -h "$SOCK" -p "$PORT" -U postgres -d "$DBN" -XAtq -c "SELECT version_num FROM alembic_version" 2>/dev/null || echo "nicht lesbar")"
    [[ "$rev" == "nicht lesbar" || -z "$rev" ]] && { ROWS+=("FAIL Alembic-Revision in $DBN nicht lesbar"); fail=1; } || ROWS+=("OK Alembic-Revision: $rev")
    je="$(as_pg "$PG_BIN/psql" -h "$SOCK" -p "$PORT" -U postgres -d "$DBN" -XAtq -c "SELECT count(*) FROM journal_entry" 2>/dev/null || echo "-")"
    ROWS+=("INFO Buchungen (journal_entry) bis Zielzeitpunkt: $je")
  fi
  last_wal="$(grep -o 'restored log file "[0-9A-F]*"' "$R.log" | tail -n1 | tr -d '"' | awk '{print $4}' || true)"
else
  last_wal=""
fi
if (( DURATION <= RTO )); then ROWS+=("OK Dauer ${DURATION}s innerhalb RTO ${RTO}s"); else ROWS+=("FAIL Dauer ${DURATION}s über RTO ${RTO}s"); fail=1; fi

mkdir -p "$(dirname "$PROTOCOL")"
{
  echo "# Point-in-Time-Wiederherstellung $(date -u +%d.%m.%Y)"
  echo
  echo "Modus: \`$MODE\`. Aufgerufen mit \`infra/scripts/pitr-drill.sh\` (GAJ-505)."
  echo "Zielzeitpunkt (\`recovery_target_time\`): \`$TARGET\`. Letztes eingespieltes Segment: \`${last_wal:-unbekannt}\`."
  echo "PostgreSQL: \`$("$PG_BIN/postgres" --version)\`. Wegwerf-Cluster, nur Unix-Socket, nach dem Lauf entfernt."
  echo "Dauer (Entpacken, WAL-Replay, Hochstufung): ${DURATION}s. Vorgabe RTO: ${RTO}s (unter 4 Stunden, MASTER-PROMPT 3.5 und 16)."
  echo
  echo "## Ergebnis"
  echo
  for row in "${ROWS[@]}"; do echo "* $row"; done
  echo
  if [[ "$fail" == 0 ]]; then echo "Gesamtergebnis: bestanden."; else echo "Gesamtergebnis: FEHLGESCHLAGEN. Betreiber informieren (Runbook \`docs/runbooks/backup.md\`)."; fi
  echo
  echo "## Vom Prüfer zu ergänzen (nur realer Lauf)"
  echo
  echo "* Basisbackup-STAMP:"
  echo "* Herkunft der WAL-Segmente (lokal oder Off-site \`runs/*/wal/\`):"
  echo "* Stichprobe Dokumenthash:"
  echo "* Prüfer und Datum (TT.MM.JJJJ):"
  echo "* Befund und Folgemaßnahmen:"
} > "$PROTOCOL"
echo "pitr-drill: Protokoll geschrieben nach $PROTOCOL (Dauer ${DURATION}s, Ergebnis $([[ $fail == 0 ]] && echo bestanden || echo FEHLGESCHLAGEN))"
[[ "$MODE" == selftest ]] && cat "$PROTOCOL"
exit "$fail"
