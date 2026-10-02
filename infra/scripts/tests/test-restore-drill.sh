#!/usr/bin/env bash
# Plain bash test for infra/scripts/restore-drill.sh --dry-run (GAI-511): no network, no
# database. Exit 0 if every case passes.
# shellcheck disable=SC2015
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../restore-drill.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL $*"; }

# Stub tools so the test does not depend on the runner image.
mkdir "$WORK/bin"
for t in age psql pg_restore; do printf '#!/bin/sh\nexit 0\n' > "$WORK/bin/$t"; chmod +x "$WORK/bin/$t"; done
printf 'AGE-SECRET-KEY-TEST\n' > "$WORK/identity.txt"

run() { env -i PATH="$WORK/bin:$PATH" HOME="$WORK" "$@"; }
base=(PGDATABASE=mhvp BACKUP_S3_BUCKET=test-bucket BACKUP_S3_ACCESS_KEY_ID=test
  BACKUP_S3_SECRET_ACCESS_KEY=test BACKUP_AGE_IDENTITY="$WORK/identity.txt")

if python3 -c "import boto3" 2>/dev/null; then
  out="$(run "${base[@]}" "$SCRIPT" --dry-run 2>&1)" && ok || bad "dry run with full config: $out"
  [[ "$out" == *"dry run ok"* ]] && ok || bad "missing ok line: $out"
else
  echo "skip: boto3 not installed, cases 1 and 2 not run"
fi
[[ ! -e "$WORK/docs" ]] && ok || bad "dry run must not write a protocol"

set +e
run PGDATABASE=mhvp "$SCRIPT" --dry-run >/dev/null 2>&1; rc=$?
set -e
[[ "$rc" != 0 ]] && ok || bad "missing bucket must fail"

set +e
run "${base[@]}" RESTORE_DATABASE=mhvp "$SCRIPT" --dry-run >/dev/null 2>&1; rc=$?
set -e
[[ "$rc" == 2 ]] && ok || bad "restore database equal to production must exit 2, got $rc"

echo "restore-drill tests: $PASS passed, $FAIL failed"
[[ "$FAIL" == 0 ]]
