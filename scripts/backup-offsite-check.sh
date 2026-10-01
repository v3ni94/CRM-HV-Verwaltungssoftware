#!/usr/bin/env bash
# Check script for the off-site run (M9-06): dry run against a local directory, no S3 access,
# no secrets. A directory tree built in a temporary folder stands in for the target bucket
# (one key per file below <prefix>/runs/<STAMP>/). The script feeds the key listing to
# `scripts/backup-offsite.sh --dry-run --list` and verifies the retention plan:
#   1. the newest BACKUP_OFFSITE_KEEP_DAILY runs are kept,
#   2. nothing newer than the oldest kept daily run is deleted,
#   3. keep plus delete equals the number of runs,
#   4. --list without --dry-run is refused (exit 2).
# Optional: --dir <local directory> uses that directory (layout <prefix>/runs/<STAMP>/...)
# instead of the generated one. Exit 0 when all checks pass, 1 on a failed check.
# Usage: scripts/backup-offsite-check.sh [--dir <directory>] [--days <n>]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/backup-offsite.sh"
DIR=""
DAYS=120
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) [[ $# -ge 2 ]] || { echo "backup-offsite-check: --dir needs a value" >&2; exit 2; }; DIR="$2"; shift 2 ;;
    --days) [[ $# -ge 2 ]] || { echo "backup-offsite-check: --days needs a value" >&2; exit 2; }; DAYS="$2"; shift 2 ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "backup-offsite-check: unknown argument $1" >&2; exit 2 ;;
  esac
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PREFIX="${BACKUP_S3_PREFIX:-mhvp}"
KEEP_DAILY="${BACKUP_OFFSITE_KEEP_DAILY:-14}"

if [[ -z "$DIR" ]]; then
  DIR="$WORK/bucket"
  for ((i = 0; i < DAYS; i++)); do
    stamp="$(date -u -d "-$i days" +%Y%m%dT020000Z)"
    mkdir -p "$DIR/$PREFIX/runs/$stamp/db"
    : >"$DIR/$PREFIX/runs/$stamp/db/mhvp-$stamp.dump.age"
    : >"$DIR/$PREFIX/runs/$stamp/status.json"
  done
fi
[[ -d "$DIR" ]] || { echo "backup-offsite-check: $DIR is not a directory" >&2; exit 2; }

(cd "$DIR" && find . -type f | sed 's#^\./##' | sort) >"$WORK/listing"
PLAN="$WORK/plan"
"$SCRIPT" --dry-run --list "$WORK/listing" >"$PLAN" 2>"$WORK/err"

fail=0
check() { if ! "$@"; then echo "FAILED: $*" >&2; fail=1; fi; }

runs=$(sed -n "s#^[a-z]* *$PREFIX/runs/\\([^/]*\\)/\$#\\1#p" "$PLAN" | sort -u | wc -l)
total=$(grep -c . <(cd "$DIR" && find "$PREFIX/runs" -mindepth 1 -maxdepth 1 -type d))
kept=$(grep -c '^keep ' "$PLAN" || true)
deleted=$(grep -c '^delete ' "$PLAN" || true)
newest=$(cd "$DIR" && find "$PREFIX/runs" -mindepth 1 -maxdepth 1 -type d | sed "s#.*/##" | sort -r | head -n "$KEEP_DAILY")
oldest_daily=$(printf '%s\n' "$newest" | tail -n 1)

check test "$runs" -eq "$total"
check test "$((kept + deleted))" -eq "$total"
for stamp in $newest; do
  check grep -q "^keep   $PREFIX/runs/$stamp/\$" "$PLAN"
done
while read -r _ path; do
  stamp="${path#"$PREFIX"/runs/}"; stamp="${stamp%/}"
  [[ "$stamp" < "$oldest_daily" ]] || { echo "FAILED: $stamp is newer than the oldest daily run but deleted" >&2; fail=1; }
done < <(grep '^delete ' "$PLAN")
if "$SCRIPT" --list "$WORK/listing" >/dev/null 2>&1; then
  echo "FAILED: --list without --dry-run was not refused" >&2; fail=1
fi

echo "backup-offsite-check: runs=$total keep=$kept delete=$deleted keep_daily=$KEEP_DAILY status=$([[ $fail -eq 0 ]] && echo ok || echo failed)"
exit "$fail"
