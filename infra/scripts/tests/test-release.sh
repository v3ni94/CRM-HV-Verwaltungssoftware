#!/usr/bin/env bash
# Plain bash tests for infra/scripts/release.sh (no bats needed).
#
# Each case builds a throwaway "/opt/mhvp" in a temp dir: a copy of release.sh, VERSION, a
# fake .env.prod and a stub ./mhvp.sh; stub docker and git are put first on PATH. The stubs
# log every call to calls.log and fail on demand via FAIL_* variables. Assertions cover the
# resulting .env.prod, the abort points (which calls happened) and the printed rollback hint.
#
# Usage: bash infra/scripts/tests/test-release.sh   (exit 0 if every case passes)
# "cond && ok || bad" is intended here (ok never fails); ls on known test file names is fine.
# shellcheck disable=SC2015,SC2012
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${RELEASE_SCRIPT:-$HERE/../release.sh}"
WORK="$(mktemp -d)"
# RELEASE_TEST_KEEP=1 keeps the temp dir (outputs and call logs per case) for inspection.
if [[ -n "${RELEASE_TEST_KEEP:-}" ]]; then echo "work dir: $WORK"; else trap 'rm -rf "$WORK"' EXIT; fi

PASS=0
FAIL=0
CASE=""

ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL [%s] %s\n' "$CASE" "$*"; }
assert_eq() { [[ "$1" == "$2" ]] && ok || bad "$3: expected '$2', got '$1'"; }
assert_contains() { grep -qF -- "$2" "$1" && ok || bad "$3: '$2' not found in $(basename "$1")"; }
assert_not_contains() { grep -qF -- "$2" "$1" && bad "$3: '$2' unexpectedly in $(basename "$1")" || ok; }
env_line() { grep -E "^$1=" "$ROOT/.env.prod" | tail -n 1; }

setup() {
  CASE="$1"
  ROOT="$WORK/$CASE/opt"
  BIN="$WORK/$CASE/bin"
  BACKUP="$WORK/$CASE/backup"
  CALLS="$WORK/$CASE/calls.log"
  OUT="$WORK/$CASE/out.log"
  mkdir -p "$ROOT/infra/scripts" "$BIN"
  cp "$SCRIPT" "$ROOT/infra/scripts/release.sh"
  : > "$CALLS"
  echo "1.39.0" > "$ROOT/VERSION"
  cat > "$ROOT/.env.prod" <<'EOF'
POSTGRES_PASSWORD=very-secret-value
MHVP_IMAGE_REGISTRY=local
MHVP_IMAGE_TAG=1.38.0
MHVP_APP_VERSION=1.38.0
MHVP_HOST_CRM=crm.example.invalid
EOF
  chmod 600 "$ROOT/.env.prod"

  cat > "$ROOT/mhvp.sh" <<'EOF'
#!/usr/bin/env bash
echo "mhvp.sh $*" >> "$CALLS"
case "$*" in
  "exec -T postgres pg_dump"*)
    [[ -n "${FAIL_DUMP:-}" ]] && { echo "pg_dump: connection refused" >&2; exit 1; }
    if [[ -n "${SMALL_DUMP:-}" ]]; then printf 'PGDMP'; else head -c 1200000 /dev/zero; fi ;;
  "exec -T postgres pg_restore --list")
    cat > /dev/null
    [[ -n "${FAIL_LIST:-}" ]] && { echo "pg_restore: input file is not a valid archive" >&2; exit 1; }
    echo "; Archive created" ;;
  "config --images"*)
    reg="$(grep -E '^MHVP_IMAGE_REGISTRY=' .env.prod | tail -n 1 | cut -d= -f2)"
    tag="$(grep -E '^MHVP_IMAGE_TAG=' .env.prod | tail -n 1 | cut -d= -f2)"
    crm_tag="$tag"
    # STALE_CRM: web-crm pinned to the old tag (the "partially set tag" pitfall).
    [[ -n "${STALE_CRM:-}" ]] && crm_tag=1.38.0
    printf '%s\n' "$reg/mhvp-api:$tag" "$reg/mhvp-web-crm:$crm_tag" "$reg/mhvp-web-portal:$tag" ;;
  "run --rm migrate")
    [[ -n "${FAIL_MIGRATE:-}" ]] && { echo "alembic: migration failed" >&2; exit 1; } ;;
  "exec -T api python -c"*)
    [[ -n "${FAIL_HEALTH:-}" ]] && exit 1 ;;
  ps) echo "NAME  STATUS"; echo "mhvp-api-1  Up (healthy)" ;;
  "logs"*)
    echo '{"event": "request", "status": 200}'
    [[ -n "${UNHANDLED:-}" ]] && echo '{"event": "unhandled_exception", "path": "/api/v1/x"}' ;;
esac
exit 0
EOF
  cat > "$BIN/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >> "$CALLS"
if [[ "$1" == build && -n "${FAIL_BUILD:-}" && "$*" == *"$FAIL_BUILD:"* ]]; then
  echo "build failed" >&2; exit 1
fi
exit 0
EOF
  cat > "$BIN/git" <<'EOF'
#!/usr/bin/env bash
echo "git $*" >> "$CALLS"
[[ -n "${FAIL_PULL:-}" ]] && exit 1
if [[ -n "${BUMP_SCRIPT:-}" ]]; then echo "# changed by pull" >> infra/scripts/release.sh; fi
exit 0
EOF
  chmod +x "$ROOT/mhvp.sh" "$BIN/docker" "$BIN/git"
}

# run_release [ENV=VALUE ...] -- [ARGS ...]; sets RC.
run_release() {
  local envs=()
  while (( $# )) && [[ "$1" != "--" ]]; do envs+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] && shift
  RC=0
  (cd "$ROOT" && env PATH="$BIN:$PATH" CALLS="$CALLS" MHVP_BACKUP_DIR="$BACKUP" \
    MHVP_HEALTH_INTERVAL=1 "${envs[@]}" bash infra/scripts/release.sh "$@") > "$OUT" 2>&1 || RC=$?
}

assert_env_unchanged() {
  assert_eq "$(env_line MHVP_IMAGE_TAG)" "MHVP_IMAGE_TAG=1.38.0" "$1 image tag"
  assert_eq "$(env_line MHVP_APP_VERSION)" "MHVP_APP_VERSION=1.38.0" "$1 app version"
}

# --- normal release -------------------------------------------------------------------
setup normal
run_release
assert_eq "$RC" 0 "exit code"
assert_eq "$(env_line MHVP_IMAGE_TAG)" "MHVP_IMAGE_TAG=1.39.0" "image tag"
assert_eq "$(env_line MHVP_APP_VERSION)" "MHVP_APP_VERSION=1.39.0" "app version"
assert_eq "$(env_line POSTGRES_PASSWORD)" "POSTGRES_PASSWORD=very-secret-value" "other lines kept"
assert_eq "$(stat -c %a "$ROOT/.env.prod")" 600 "env mode kept"
assert_contains "$ROOT/.env.prod.bak-1.38.0" "MHVP_IMAGE_TAG=1.38.0" "env backup"
assert_eq "$(stat -c %a "$ROOT/.env.prod.bak-1.38.0")" 600 "env backup mode"
dump="$(ls "$BACKUP"/vor-1.39.0-*.dump 2>/dev/null | head -n 1 || true)"
[[ -n "$dump" ]] && ok || bad "dump file missing"
[[ -n "$dump" ]] && assert_eq "$(stat -c %a "$dump")" 600 "dump mode"
expected_order="git pull --ff-only origin claude/funny-cerf-ppg9in
mhvp.sh config --images migrate api worker beat web-crm web-portal
mhvp.sh exec -T postgres pg_dump -U postgres -Fc mhvp
mhvp.sh exec -T postgres pg_restore --list
docker build --build-arg MHVP_APP_VERSION=1.39.0 -t local/mhvp-api:1.39.0 apps/api
docker build --build-arg MHVP_APP_VERSION=1.39.0 -f apps/web-crm/Dockerfile -t local/mhvp-web-crm:1.39.0 .
docker build --build-arg MHVP_APP_VERSION=1.39.0 -f apps/web-portal/Dockerfile -t local/mhvp-web-portal:1.39.0 .
mhvp.sh config --images migrate api worker beat web-crm web-portal
mhvp.sh stop api worker beat
mhvp.sh run --rm migrate
mhvp.sh up -d --force-recreate api worker beat web-crm web-portal"
assert_eq "$(grep -v '^docker image inspect' "$CALLS" | head -n 11)" "$expected_order" "call order"
assert_contains "$CALLS" "mhvp.sh exec -T api python -c" "health probe"
assert_contains "$CALLS" "mhvp.sh logs --no-color --since 2m api" "log grep"
assert_contains "$OUT" "alter Stand:       1.38.0" "summary old tag"
assert_contains "$OUT" "neuer Stand:       1.39.0" "summary new tag"
assert_contains "$OUT" "Sicherung:         $BACKUP/vor-1.39.0-" "summary backup"
assert_contains "$OUT" "Dauer:" "summary duration"
assert_contains "$OUT" "keine unhandled_exception" "log result"
assert_not_contains "$OUT" "very-secret-value" "no secret printed"
assert_not_contains "$OUT" "ABBRUCH" "no rollback hint"

# --- dry run ----------------------------------------------------------------------------
setup dryrun
run_release -- --dry-run
assert_eq "$RC" 0 "exit code"
assert_env_unchanged "dry run"
[[ ! -e "$ROOT/.env.prod.bak-1.38.0" ]] && ok || bad "env backup written in dry run"
[[ ! -d "$BACKUP" ]] && ok || bad "backup dir created in dry run"
assert_eq "$(wc -l < "$CALLS" | tr -d ' ')" 0 "no command executed"
assert_contains "$OUT" "+ git pull --ff-only origin claude/funny-cerf-ppg9in" "pull printed"
assert_contains "$OUT" "+ ./mhvp.sh exec -T postgres pg_dump -U postgres -Fc mhvp > $BACKUP/vor-1.39.0-" "dump printed"
assert_contains "$OUT" "+ docker build --build-arg MHVP_APP_VERSION=1.39.0 -f apps/web-portal/Dockerfile" "build printed"
assert_contains "$OUT" "+ sed -i" "sed printed"
assert_contains "$OUT" "+ ./mhvp.sh run --rm migrate" "migrate printed"
assert_contains "$OUT" "+ ./mhvp.sh up -d --force-recreate api worker beat web-crm web-portal" "up printed"
assert_contains "$OUT" "Probelauf" "dry run banner"

# --- failing backup (pg_dump) -----------------------------------------------------------
setup backup_fail
run_release FAIL_DUMP=1
assert_eq "$RC" 1 "exit code"
assert_env_unchanged "backup fail"
assert_not_contains "$CALLS" "docker build" "no build after failed backup"
assert_not_contains "$CALLS" "mhvp.sh stop" "no stop after failed backup"
assert_contains "$OUT" "pg_dump fehlgeschlagen" "message"
assert_contains "$OUT" "Abbruch vor jeder Änderung" "abort point"
assert_not_contains "$OUT" "ABBRUCH nach Änderung" "no rollback hint needed"

# --- backup too small -------------------------------------------------------------------
setup backup_small
run_release SMALL_DUMP=1
assert_eq "$RC" 1 "exit code"
assert_env_unchanged "small backup"
assert_contains "$OUT" "zu klein" "message"
assert_not_contains "$CALLS" "docker build" "no build"
ls "$BACKUP"/vor-1.39.0-*.dump.ungueltig > /dev/null 2>&1 && ok || bad "small dump not marked ungueltig"

# --- backup not restorable --------------------------------------------------------------
setup backup_list
run_release FAIL_LIST=1
assert_eq "$RC" 1 "exit code"
assert_env_unchanged "list fail"
assert_contains "$OUT" "pg_restore --list fehlgeschlagen" "message"
assert_not_contains "$CALLS" "docker build" "no build"

# --- failing build ----------------------------------------------------------------------
setup build_fail
run_release FAIL_BUILD=local/mhvp-web-crm
assert_eq "$RC" 1 "exit code"
assert_env_unchanged "build fail"
[[ ! -e "$ROOT/.env.prod.bak-1.38.0" ]] && ok || bad "env backup written after failed build"
assert_not_contains "$CALLS" "mhvp-web-portal:1.39.0" "no later build"
assert_not_contains "$CALLS" "mhvp.sh stop" "no stop"
assert_contains "$OUT" "Build von mhvp-web-crm fehlgeschlagen" "message"

# --- failing migrate --------------------------------------------------------------------
setup migrate_fail
run_release FAIL_MIGRATE=1
assert_eq "$RC" 3 "exit code"
assert_eq "$(env_line MHVP_IMAGE_TAG)" "MHVP_IMAGE_TAG=1.39.0" "env not restored automatically"
assert_contains "$ROOT/.env.prod.bak-1.38.0" "MHVP_IMAGE_TAG=1.38.0" "env backup kept"
assert_contains "$CALLS" "mhvp.sh stop api worker beat" "stopped before migrate"
assert_not_contains "$CALLS" "mhvp.sh up -d" "no start after failed migrate"
assert_contains "$OUT" "ABBRUCH nach Änderung der Konfiguration: Migration fehlgeschlagen" "rollback reason"
assert_contains "$OUT" "cp -p .env.prod.bak-1.38.0 .env.prod" "rollback env step"
assert_contains "$OUT" "./mhvp.sh up -d --force-recreate api worker beat web-crm web-portal" "rollback start step"
assert_contains "$OUT" "pg_restore -U postgres --clean --if-exists --create --exit-on-error -d postgres < $BACKUP/vor-1.39.0-" "rollback restore step"
assert_not_contains "$CALLS" "pg_restore -U postgres --clean" "no automatic restore"

# --- VERSION equals running tag ---------------------------------------------------------
setup same_version
echo "1.38.0" > "$ROOT/VERSION"
run_release
assert_eq "$RC" 2 "exit code without --force"
assert_not_contains "$CALLS" "pg_dump" "no backup without --force"
assert_contains "$OUT" "nur mit --force" "message"
run_release -- --force --skip-pull
assert_eq "$RC" 0 "exit code with --force"
assert_contains "$ROOT/.env.prod.bak-1.38.0" "MHVP_IMAGE_TAG=1.38.0" "env backup with --force"
assert_contains "$CALLS" "local/mhvp-api:1.38.0 apps/api" "rebuilt same tag"

# --- invalid VERSION --------------------------------------------------------------------
setup bad_version
echo "" > "$ROOT/VERSION"
run_release -- --skip-pull
assert_eq "$RC" 2 "empty VERSION"
assert_contains "$OUT" "VERSION ist leer" "empty message"
echo "v1.39" > "$ROOT/VERSION"
run_release -- --skip-pull
assert_eq "$RC" 2 "non semver VERSION"
assert_contains "$OUT" "keine semantische Version" "semver message"
assert_eq "$(wc -l < "$CALLS" | tr -d ' ')" 0 "nothing executed"

# --- health timeout ---------------------------------------------------------------------
setup health_timeout
run_release FAIL_HEALTH=1 MHVP_HEALTH_TIMEOUT=2
assert_eq "$RC" 3 "exit code"
assert_contains "$OUT" "API nach 2 s nicht gesund" "message"
assert_contains "$OUT" "cp -p .env.prod.bak-1.38.0 .env.prod" "rollback hint"

# --- unhandled_exception in logs --------------------------------------------------------
setup unhandled
run_release UNHANDLED=1
assert_eq "$RC" 4 "exit code"
assert_contains "$OUT" "ACHTUNG: unhandled_exception" "warning"
assert_contains "$OUT" '"event": "unhandled_exception"' "matching line shown"

# --- compose resolves other images (registry mismatch) ----------------------------------
setup registry_mismatch
sed -i 's/^MHVP_IMAGE_REGISTRY=.*/MHVP_IMAGE_REGISTRY=ghcr.io\/v3ni94/' "$ROOT/.env.prod"
run_release
assert_eq "$RC" 2 "exit code"
assert_contains "$ROOT/.env.prod" "MHVP_IMAGE_REGISTRY=ghcr.io/v3ni94" "registry untouched"
assert_env_unchanged "registry mismatch"
assert_not_contains "$CALLS" "pg_dump" "aborted before backup"
assert_not_contains "$CALLS" "docker build" "aborted before build"
assert_contains "$OUT" "Compose verwendet nicht local/mhvp-*:1.38.0" "message"

# --- one service stays on the old tag after the switch ----------------------------------
setup stale_service
run_release STALE_CRM=1
assert_eq "$RC" 1 "exit code"
assert_env_unchanged "stale service (env reverted)"
assert_contains "$CALLS" "docker build" "built before the switch"
assert_not_contains "$CALLS" "mhvp.sh stop" "no stop"
assert_contains "$OUT" "local/mhvp-web-crm:1.38.0" "offending image named"
assert_contains "$OUT" "zurückgesetzt, Dienste unverändert" "message"

# --- pull options -----------------------------------------------------------------------
setup pull_options
run_release -- --skip-pull
assert_eq "$RC" 0 "exit code skip pull"
assert_not_contains "$CALLS" "git " "no pull"
setup branch_option
run_release -- --branch feature/x
assert_eq "$RC" 0 "exit code branch"
assert_contains "$CALLS" "git pull --ff-only origin feature/x" "branch used"
setup pull_fail
run_release FAIL_PULL=1
assert_eq "$RC" 1 "exit code failing pull"
assert_not_contains "$CALLS" "pg_dump" "no backup after failed pull"

# --- pull changes release.sh: new version continues ------------------------------------
setup reexec
run_release BUMP_SCRIPT=1
assert_eq "$RC" 0 "exit code"
assert_eq "$(grep -c '^git pull' "$CALLS")" 1 "pulled once"
assert_contains "$OUT" "neue Fassung wird gestartet" "re-exec message"
assert_eq "$(env_line MHVP_IMAGE_TAG)" "MHVP_IMAGE_TAG=1.39.0" "released by new version"

printf 'release.sh tests: %d passed, %d failed\n' "$PASS" "$FAIL"
(( FAIL == 0 ))
