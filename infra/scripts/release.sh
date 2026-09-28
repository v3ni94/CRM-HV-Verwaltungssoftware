#!/usr/bin/env bash
# Manual production release on the server (docs/runbooks/release.md).
#
# Automates the operator's release sequence in /opt/mhvp: pull, read the tag from VERSION,
# verified database backup, build the three images locally (local/mhvp-*:<tag>), switch
# MHVP_IMAGE_TAG and MHVP_APP_VERSION in .env.prod (copy kept as .env.prod.bak-<old tag>),
# stop api/worker/beat, run the migrate container, start the services, wait for the API
# liveness endpoint and grep the fresh API logs for unhandled_exception.
#
# Nothing is rolled back automatically. On a failure after .env.prod was changed the script
# prints the rollback steps and stops; the operator decides.
#
# Usage (from /opt/mhvp or anywhere, the repository root is derived from this file):
#   infra/scripts/release.sh [--dry-run] [--branch NAME] [--skip-pull] [--force]
#
# Environment:
#   MHVP_WRAPPER          compose wrapper, default ./mhvp.sh (relative to the repository root)
#   MHVP_BACKUP_DIR       backup directory, default /srv/mhvp-backup
#   MHVP_ENV_FILE         env file, default .env.prod
#   MHVP_DB_NAME          database to dump, default mhvp
#   MHVP_ROOT             repository root, default two levels above this script
#   MHVP_HEALTH_TIMEOUT   seconds to wait for /api/v1/health/live, default 120
#   MHVP_HEALTH_INTERVAL  seconds between health probes, default 5
#   MHVP_BACKUP_MIN_BYTES minimum dump size, default 1048576 (1 MB)
#
# Exit codes: 0 done; 1 aborted before any change (nothing to roll back); 2 usage or
# precondition error; 3 failure after .env.prod was changed (rollback steps printed);
# 4 release done but unhandled_exception found in the API logs.
#
# No secrets are printed: .env.prod is never echoed, only the two tag lines are edited.
set -euo pipefail

DEFAULT_BRANCH="claude/funny-cerf-ppg9in"
SERVICES_STOP=(api worker beat)
SERVICES_START=(api worker beat web-crm web-portal)
IMAGE_SERVICES=(migrate api worker beat web-crm web-portal)
BUILD_REGISTRY="local"
HEALTH_PY="import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3).status == 200 else 1)"

say() { printf 'release: %s\n' "$*"; }
err() { printf 'release: FEHLER: %s\n' "$*" >&2; }

usage() {
  cat <<'EOF'
Aufruf: infra/scripts/release.sh [--dry-run] [--branch NAME] [--skip-pull] [--force]

  --dry-run      zeigt jeden Befehl an, ohne ihn auszuführen
  --branch NAME  Zweig für git pull (Standard: claude/funny-cerf-ppg9in)
  --skip-pull    kein git pull, der aktuelle Stand wird ausgerollt
  --force        auch ausrollen, wenn VERSION dem laufenden MHVP_IMAGE_TAG entspricht

Umgebung: MHVP_WRAPPER (./mhvp.sh), MHVP_BACKUP_DIR (/srv/mhvp-backup),
MHVP_ENV_FILE (.env.prod), MHVP_DB_NAME (mhvp), MHVP_HEALTH_TIMEOUT (120).
Ablauf und Rollback: docs/runbooks/release.md
EOF
}

# Print a command in shell-quoted form.
show() {
  local out="+" arg
  for arg in "$@"; do
    if [[ "$arg" =~ ^[A-Za-z0-9_./:=@%+,-]+$ ]]; then
      out+=" $arg"
    else
      out+=" '${arg//\'/\'\\\'\'}'"
    fi
  done
  printf '%s\n' "$out"
}

# check_images TAG: compose resolves every app service to BUILD_REGISTRY/mhvp-*:TAG.
check_images() {
  local images bad tag_re='[^:]+'
  [[ -n "$1" ]] && tag_re="${1//./\\.}"
  if ! images="$("$WRAPPER" config --images "${IMAGE_SERVICES[@]}" 2>/dev/null)" || [[ -z "$images" ]]; then
    err "$WRAPPER config --images lieferte kein Ergebnis"
    return 1
  fi
  bad="$(printf '%s\n' "$images" | grep -vxE "$BUILD_REGISTRY/mhvp-(api|web-crm|web-portal):$tag_re" | tr '\n' ' ' || true)"
  if [[ -n "$bad" ]]; then
    err "Compose verwendet nicht $BUILD_REGISTRY/mhvp-*:$1, sondern: $bad"
    return 1
  fi
}

# run CMD...: print and execute (print only with --dry-run).
run() {
  show "$@"
  (( DRY_RUN )) && return 0
  "$@"
}

# run_to FILE CMD...: stdout of CMD into FILE.
run_to() {
  local file="$1"; shift
  printf '%s > %q\n' "$(show "$@")" "$file"
  (( DRY_RUN )) && return 0
  "$@" > "$file"
}

# run_from FILE CMD...: FILE as stdin of CMD, stdout discarded.
run_from() {
  local file="$1"; shift
  printf '%s < %q > /dev/null\n' "$(show "$@")" "$file"
  (( DRY_RUN )) && return 0
  "$@" < "$file" > /dev/null
}

env_value() {
  # Last assignment of $1 in the env file, without surrounding quotes.
  local line
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 || true)"
  line="${line#*=}"
  line="${line%\"}"; line="${line#\"}"
  line="${line%\'}"; line="${line#\'}"
  printf '%s' "$line"
}

print_rollback() {
  local reason="$1"
  cat >&2 <<EOF

release: ABBRUCH nach Änderung der Konfiguration: $reason
release: Es wird nichts automatisch zurückgesetzt. Rollback bei Bedarf von Hand, in $ROOT:

  1. Konfiguration auf den alten Stand ($OLD_TAG) zurücksetzen:
       cp -p $ENV_BACKUP $ENV_FILE
  2. Dienste mit dem alten Stand starten:
       $WRAPPER up -d --force-recreate ${SERVICES_START[*]}
       $WRAPPER ps
  3. Nur wenn die Migration die Datenbank bereits verändert hat (Migrationen laufen je
     Revision in einer eigenen Transaktion, frühere Revisionen desselben Laufs bleiben
     bestehen) und der alte Stand damit nicht startet: Sicherung zurückspielen.
     Dazu vorher alle Datenbankverbindungen beenden:
       $WRAPPER stop ${SERVICES_STOP[*]}
       $WRAPPER exec -T postgres pg_restore -U postgres --clean --if-exists --create --exit-on-error -d postgres < $BACKUP_FILE
       $WRAPPER up -d --force-recreate ${SERVICES_START[*]}
     Daten, die nach der Sicherung geschrieben wurden, fehlen danach.
  Einzelheiten: docs/runbooks/release.md, Abschnitt Rollback.
EOF
}

# Failure after .env.prod was changed: print rollback steps and exit 3.
fail_after_change() {
  ROLLBACK_PRINTED=1
  print_rollback "$1"
  exit 3
}

# Backup unusable: mark the file so it is never taken for a valid dump, exit 1 (no change yet).
backup_failed() {
  if (( ! DRY_RUN )) && [[ -e "$BACKUP_FILE" ]]; then
    mv -f "$BACKUP_FILE" "$BACKUP_FILE.ungueltig"
    err "$1; Datei umbenannt in $BACKUP_FILE.ungueltig"
  else
    err "$1"
  fi
  err "Abbruch vor jeder Änderung, $ENV_FILE und Dienste unverändert"
  exit 1
}

# shellcheck disable=SC2329 # invoked via trap EXIT
on_exit() {
  local rc=$?
  if (( rc != 0 && CHANGED && ! ROLLBACK_PRINTED )); then
    print_rollback "unerwarteter Fehler (Exit $rc)"
    exit 3
  fi
}

main() {
  local orig_args=("$@")
  DRY_RUN=0
  local branch="$DEFAULT_BRANCH" skip_pull=0 force=0
  while (( $# )); do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --skip-pull) skip_pull=1 ;;
      --force) force=1 ;;
      --branch)
        [[ $# -ge 2 && -n "$2" ]] || { err "--branch braucht einen Namen"; exit 2; }
        branch="$2"; shift ;;
      --branch=*) branch="${1#--branch=}" ;;
      -h|--help) usage; exit 0 ;;
      *) err "unbekannte Option $1"; usage >&2; exit 2 ;;
    esac
    shift
  done
  [[ "$branch" =~ ^[A-Za-z0-9._/-]+$ ]] || { err "ungültiger Zweigname"; exit 2; }

  local script_dir self
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  self="$script_dir/$(basename "${BASH_SOURCE[0]}")"
  ROOT="${MHVP_ROOT:-$(cd "$script_dir/../.." && pwd)}"
  cd "$ROOT"
  WRAPPER="${MHVP_WRAPPER:-./mhvp.sh}"
  local backup_dir="${MHVP_BACKUP_DIR:-/srv/mhvp-backup}"
  ENV_FILE="${MHVP_ENV_FILE:-.env.prod}"
  local db_name="${MHVP_DB_NAME:-mhvp}"
  local health_timeout="${MHVP_HEALTH_TIMEOUT:-120}"
  local health_interval="${MHVP_HEALTH_INTERVAL:-5}"
  local min_bytes="${MHVP_BACKUP_MIN_BYTES:-1048576}"
  CHANGED=0
  ROLLBACK_PRINTED=0
  trap on_exit EXIT
  SECONDS=0

  (( DRY_RUN )) && say "Probelauf (--dry-run): Befehle werden nur angezeigt"
  [[ -x "$WRAPPER" ]] || { err "Wrapper $WRAPPER fehlt oder ist nicht ausführbar (MHVP_WRAPPER)"; exit 2; }
  [[ -f "$ENV_FILE" ]] || { err "$ENV_FILE fehlt in $ROOT"; exit 2; }

  # 1. Pull. If the pull changed this script, continue with the new version.
  if (( skip_pull )); then
    say "git pull übersprungen (--skip-pull)"
  else
    local before after
    before="$(cksum < "$self")"
    run git pull --ff-only origin "$branch" || { err "git pull fehlgeschlagen, nichts geändert"; exit 1; }
    after="$(cksum < "$self")"
    if (( ! DRY_RUN )) && [[ "$before" != "$after" ]]; then
      say "release.sh wurde durch den Pull geändert, neue Fassung wird gestartet"
      trap - EXIT
      exec bash "$self" --skip-pull "${orig_args[@]}"
    fi
  fi

  # 2. Tags.
  [[ -f VERSION ]] || { err "VERSION fehlt"; exit 2; }
  TAG="$(tr -d '[:space:]' < VERSION)"
  [[ -n "$TAG" ]] || { err "VERSION ist leer"; exit 2; }
  [[ "$TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] \
    || { err "VERSION ist keine semantische Version: $TAG"; exit 2; }
  local var count
  for var in MHVP_IMAGE_TAG MHVP_APP_VERSION; do
    count="$(grep -cE "^${var}=" "$ENV_FILE" || true)"
    (( count <= 1 )) || { err "$var ist in $ENV_FILE mehrfach gesetzt, bitte bereinigen"; exit 2; }
  done
  OLD_TAG="$(env_value MHVP_IMAGE_TAG)"
  local old_app_version
  old_app_version="$(env_value MHVP_APP_VERSION)"
  say "laufender Stand: MHVP_IMAGE_TAG=${OLD_TAG:-leer} MHVP_APP_VERSION=${old_app_version:-leer}"
  say "neuer Stand aus VERSION: $TAG"
  # Compose must already resolve every app service to local/mhvp-*:<old tag>; otherwise the
  # images built below would not be used, or one service runs on a different tag.
  if (( DRY_RUN )); then
    show "$WRAPPER" config --images "${IMAGE_SERVICES[@]}"
  elif ! check_images "$OLD_TAG"; then
    err "Abbruch vor jeder Änderung; MHVP_IMAGE_REGISTRY (erwartet $BUILD_REGISTRY) und Tags in $ENV_FILE prüfen"
    exit 2
  fi
  if [[ "$TAG" == "$OLD_TAG" ]] && (( ! force )); then
    if (( DRY_RUN )); then
      say "Hinweis: VERSION entspricht dem laufenden Stand; ohne --force würde der echte Lauf hier abbrechen"
    else
      err "VERSION $TAG entspricht dem laufenden MHVP_IMAGE_TAG; erneut ausrollen nur mit --force"
      exit 2
    fi
  fi
  if (( ! DRY_RUN )) && [[ -n "$OLD_TAG" ]]; then
    local img missing_old=()
    for img in mhvp-api mhvp-web-crm mhvp-web-portal; do
      docker image inspect "$BUILD_REGISTRY/$img:$OLD_TAG" > /dev/null 2>&1 || missing_old+=("$img")
    done
    (( ${#missing_old[@]} == 0 )) \
      || say "Hinweis: alte Images fehlen lokal (${missing_old[*]}:$OLD_TAG); ein Rollback braucht dann einen Neubau des alten Stands"
  fi

  # 3. Verified backup, before any change.
  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  BACKUP_FILE="$backup_dir/vor-$TAG-$stamp.dump"
  run mkdir -p "$backup_dir" || { err "Sicherungsverzeichnis $backup_dir nicht anlegbar"; exit 1; }
  local old_umask dump_ok=1
  old_umask="$(umask)"
  umask 077
  run_to "$BACKUP_FILE" "$WRAPPER" exec -T postgres pg_dump -U postgres -Fc "$db_name" || dump_ok=0
  umask "$old_umask"
  (( dump_ok )) || backup_failed "pg_dump fehlgeschlagen"
  if (( ! DRY_RUN )); then
    local size
    [[ -s "$BACKUP_FILE" ]] || backup_failed "Sicherung fehlt oder ist leer"
    size="$(wc -c < "$BACKUP_FILE" | tr -d ' ')"
    (( size > min_bytes )) || backup_failed "Sicherung ist mit $size Byte zu klein (Minimum $min_bytes)"
    say "Sicherung geschrieben: $BACKUP_FILE ($size Byte)"
  fi
  run_from "$BACKUP_FILE" "$WRAPPER" exec -T postgres pg_restore --list \
    || backup_failed "pg_restore --list fehlgeschlagen, Sicherung unbrauchbar"
  (( DRY_RUN )) || say "Sicherung geprüft (pg_restore --list)"

  # 4. Build all three images before touching the env file.
  local image dockerfile context
  for image in mhvp-api mhvp-web-crm mhvp-web-portal; do
    case "$image" in
      mhvp-api) dockerfile=(); context=apps/api ;;
      *) dockerfile=(-f "apps/${image#mhvp-}/Dockerfile"); context=. ;;
    esac
    run docker build --build-arg "MHVP_APP_VERSION=$TAG" "${dockerfile[@]}" \
      -t "$BUILD_REGISTRY/$image:$TAG" "$context" \
      || { err "Build von $image fehlgeschlagen; $ENV_FILE und Dienste unverändert"; exit 1; }
  done

  # 5. Switch both tag variables (copy of the old file kept).
  ENV_BACKUP="$ENV_FILE.bak-${OLD_TAG:-leer}"
  [[ -e "$ENV_BACKUP" ]] && ENV_BACKUP="$ENV_BACKUP-$stamp"
  run cp -p "$ENV_FILE" "$ENV_BACKUP" || { err "Kopie $ENV_BACKUP nicht anlegbar; nichts geändert"; exit 1; }
  (( DRY_RUN )) || CHANGED=1
  run sed -i "s/^MHVP_IMAGE_TAG=.*/MHVP_IMAGE_TAG=$TAG/; s/^MHVP_APP_VERSION=.*/MHVP_APP_VERSION=$TAG/" "$ENV_FILE"
  for var in MHVP_IMAGE_TAG MHVP_APP_VERSION; do
    if (( DRY_RUN )); then
      grep -qE "^${var}=" "$ENV_FILE" || show "echo $var=$TAG >> $ENV_FILE"
    elif ! grep -qE "^${var}=" "$ENV_FILE"; then
      say "$var fehlte in $ENV_FILE und wird ergänzt"
      printf '%s=%s\n' "$var" "$TAG" >> "$ENV_FILE"
    fi
  done
  if (( ! DRY_RUN )); then
    [[ "$(env_value MHVP_IMAGE_TAG)" == "$TAG" && "$(env_value MHVP_APP_VERSION)" == "$TAG" ]] \
      || fail_after_change "Tags in $ENV_FILE nicht wie erwartet gesetzt"
    say "$ENV_FILE umgestellt auf $TAG, alter Stand in $ENV_BACKUP"
  fi

  # 6. Compose must resolve every app service to the freshly built images. A mismatch is
  # caught here while all services still run; the env file is then reverted (own edit only).
  if (( DRY_RUN )); then
    show "$WRAPPER" config --images "${IMAGE_SERVICES[@]}"
  elif ! check_images "$TAG"; then
    cp -p "$ENV_BACKUP" "$ENV_FILE"; CHANGED=0
    err "$ENV_FILE aus $ENV_BACKUP zurückgesetzt, Dienste unverändert; Tags in $ENV_FILE prüfen"
    exit 1
  else
    say "Images geprüft: alle Dienste auf $BUILD_REGISTRY/mhvp-*:$TAG"
  fi

  # 7. Stop, migrate, start.
  run "$WRAPPER" stop "${SERVICES_STOP[@]}" || fail_after_change "Stoppen von ${SERVICES_STOP[*]} fehlgeschlagen"
  run "$WRAPPER" run --rm migrate || fail_after_change "Migration fehlgeschlagen (api, worker, beat sind gestoppt)"
  run "$WRAPPER" up -d --force-recreate "${SERVICES_START[@]}" || fail_after_change "Start der Dienste fehlgeschlagen"

  # 8. Wait for liveness.
  show "$WRAPPER" exec -T api python -c "$HEALTH_PY"
  if (( ! DRY_RUN )); then
    local waited=0
    until "$WRAPPER" exec -T api python -c "$HEALTH_PY" > /dev/null 2>&1; do
      if (( waited >= health_timeout )); then
        "$WRAPPER" ps >&2 || true
        fail_after_change "API nach $health_timeout s nicht gesund (/api/v1/health/live)"
      fi
      sleep "$health_interval"
      waited=$(( waited + health_interval ))
    done
    say "API gesund nach etwa $waited s"
  fi

  # 9. Status, logs, summary.
  run "$WRAPPER" ps || true
  local hits="" rc=0
  printf '%s | grep unhandled_exception\n' "$(show "$WRAPPER" logs --no-color --since 2m api)"
  if (( ! DRY_RUN )); then
    hits="$("$WRAPPER" logs --no-color --since 2m api 2>&1 | grep unhandled_exception || true)"
    if [[ -n "$hits" ]]; then
      rc=4
      say "ACHTUNG: unhandled_exception in den API-Logs der letzten 2 Minuten (letzte 20 Treffer):"
      printf '%s\n' "$hits" | tail -n 20
    else
      say "keine unhandled_exception in den API-Logs der letzten 2 Minuten"
    fi
  fi

  local dur="$SECONDS"
  printf '\nrelease: Zusammenfassung%s\n' "$( (( DRY_RUN )) && echo ' (Probelauf, nichts ausgeführt)')"
  printf '  alter Stand:       %s\n' "${OLD_TAG:-leer}"
  printf '  neuer Stand:       %s\n' "$TAG"
  printf '  Sicherung:         %s\n' "$BACKUP_FILE"
  printf '  alte Konfiguration: %s\n' "$ENV_BACKUP"
  printf '  Dauer:             %d min %02d s\n' $(( dur / 60 )) $(( dur % 60 ))
  (( rc == 4 )) && printf '  Befund:            unhandled_exception in den API-Logs, bitte prüfen\n'
  trap - EXIT
  exit "$rc"
}

# Everything above is a function definition and main always exits itself, so a pull that
# rewrites this file cannot change the running release (bash reads scripts incrementally).
main "$@"
