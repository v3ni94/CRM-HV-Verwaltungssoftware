#!/usr/bin/env bash
# Test of infra/scripts/pitr-drill.sh (GAJ-505): argument checks, dry run, and when PostgreSQL
# binaries are present a full self test against a throwaway cluster plus an RTO breach case.
# shellcheck disable=SC2015
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../pitr-drill.sh"
WORK="$(mktemp -d)"; chmod 755 "$WORK"
trap 'rm -rf "$WORK"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL $*"; }

set +e
bash "$SCRIPT" >/dev/null 2>&1; [[ $? == 2 ]] && ok || bad "no mode must exit 2"
bash "$SCRIPT" --base /nonexistent --wal-dir /tmp --target x >/dev/null 2>&1; [[ $? == 2 ]] && ok || bad "missing base must exit 2"
PITR_RTO_SECONDS=abc bash "$SCRIPT" --selftest --dry-run >/dev/null 2>&1; [[ $? == 2 ]] && ok || bad "bad RTO must exit 2"
set -e
if out="$(bash "$SCRIPT" --selftest --dry-run 2>&1)"; then
  [[ "$out" == *"dry run ok"* && "$out" == *"RTO 14400s"* ]] && ok || bad "dry run output: $out"
  bash "$SCRIPT" --selftest --protocol "$WORK/p.md" >/dev/null 2>&1 && ok || bad "selftest failed"
  grep -q "Zeilen bis Zielzeitpunkt (pitr_probe): 150" "$WORK/p.md" && ok || bad "protocol lacks row check"
  grep -q "Gesamtergebnis: bestanden" "$WORK/p.md" && ok || bad "protocol not passed"
  set +e
  PITR_RTO_SECONDS=0 bash "$SCRIPT" --selftest --protocol "$WORK/rto.md" >/dev/null 2>&1; rc=$?
  set -e
  [[ $rc == 1 ]] && grep -q "über RTO 0s" "$WORK/rto.md" && ok || bad "RTO breach must exit 1 (rc $rc)"
else
  echo "skip: PostgreSQL binaries not found, self test not run ($out)"
fi
echo "test-pitr-drill: $PASS passed, $FAIL failed"
[[ "$FAIL" == 0 ]]
