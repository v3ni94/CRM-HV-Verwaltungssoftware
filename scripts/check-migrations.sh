#!/usr/bin/env bash
# Sperre gegen Umnummerieren oder Loeschen bereits gemergter Alembic-Migrationen
# (apps/api/alembic/versions). Hintergrund: umbenannte, produktiv bereits angewandte
# Migrationen haben einen Produktionsausfall verursacht.
#
# Regeln:
#   1. Jede Migrationsdatei der Basis muss im aktuellen Stand unter demselben Dateinamen
#      vorhanden sein (Umbenennung oder Loeschung ist ein Fehler).
#   2. revision und down_revision einer vorhandenen Datei duerfen sich nicht aendern.
#   3. Neue Dateien tragen fortlaufend die naechsten freien Nummern nach der hoechsten
#      Revision der Basis, die Dateinummer entspricht der Revision, und die Kette
#      down_revision beginnt bei der bisherigen Head-Revision.
#
# Aufruf:
#   scripts/check-migrations.sh                 Basis origin/claude/funny-cerf-ppg9in
#   scripts/check-migrations.sh <ref>           andere Basis (Branch, Tag, Commit)
#   BASE=<ref> scripts/check-migrations.sh      Basis per Umgebungsvariable
# Verglichen wird der Merge-Base von Basis und HEAD (Fallback: die Basis selbst) mit dem
# Arbeitsverzeichnis. Exit 0 ohne Verstoss, 1 bei Verstoss, 2 bei Aufruffehler.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="apps/api/alembic/versions"
BASE="${1:-${BASE:-origin/claude/funny-cerf-ppg9in}}"

cd "$ROOT"

if ! git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
  echo "check-migrations: Basis '$BASE' ist kein bekannter Git-Ref (fetch-depth 0 und Branch vorhanden?)" >&2
  exit 2
fi
REF="$(git merge-base "$BASE" HEAD 2>/dev/null || true)"
if [[ -z "$REF" ]]; then
  echo "check-migrations: kein Merge-Base zwischen '$BASE' und HEAD, vergleiche direkt mit '$BASE'" >&2
  REF="$(git rev-parse "$BASE")"
fi
echo "check-migrations: Basis $BASE ($(git rev-parse --short "$REF")), Verzeichnis $DIR"

errors=0
fail() { echo "FEHLER: $*" >&2; errors=$((errors + 1)); }

# Liest revision bzw. down_revision aus Dateiinhalt auf stdin.
extract() {
  sed -n -E "s/^${1}[[:space:]]*(:[^=]*)?=[[:space:]]*[\"']([^\"']*)[\"'].*/\2/p" | head -n 1
}
extract_down() {
  local v
  v="$(sed -n -E "s/^down_revision[[:space:]]*(:[^=]*)?=[[:space:]]*(.*)$/\2/p" | head -n 1)"
  v="${v%%#*}"
  v="$(printf '%s' "$v" | tr -d '"'"'"' ' | tr -d '()')"
  printf '%s' "$v"
}

is_migration() { [[ "$1" == *.py && "$(basename "$1")" != __init__.py ]]; }

declare -A base_rev base_down
base_max=""
while IFS= read -r path; do
  is_migration "$path" || continue
  name="$(basename "$path")"
  content="$(git show "$REF:$path")"
  rev="$(printf '%s\n' "$content" | extract revision)"
  down="$(printf '%s\n' "$content" | extract_down)"
  base_rev["$name"]="$rev"
  base_down["$name"]="$down"
  if [[ "$rev" =~ ^[0-9]{4}$ ]] && { [[ -z "$base_max" ]] || (( 10#$rev > 10#$base_max )); }; then
    base_max="$rev"
  fi
done < <(git ls-tree -r --name-only "$REF" -- "$DIR")

if [[ ${#base_rev[@]} -eq 0 ]]; then
  echo "check-migrations: Basis enthaelt keine Migrationen unter $DIR, nichts zu pruefen"
  exit 0
fi

# Regel 1 und 2: vorhandene Dateien unveraendert im Namen, revision und down_revision.
for name in "${!base_rev[@]}"; do
  file="$DIR/$name"
  if [[ ! -f "$file" ]]; then
    fail "Migration '$name' (revision ${base_rev[$name]}) existiert in der Basis, fehlt aber im aktuellen Stand. Gemergte Migrationen duerfen weder umbenannt noch geloescht werden."
    continue
  fi
  rev="$(extract revision < "$file")"
  down="$(extract_down < "$file")"
  if [[ "$rev" != "${base_rev[$name]}" ]]; then
    fail "Migration '$name': revision wurde von '${base_rev[$name]}' auf '$rev' geaendert. Revision-IDs gemergter Migrationen sind unveraenderlich."
  fi
  if [[ "$down" != "${base_down[$name]}" ]]; then
    fail "Migration '$name': down_revision wurde von '${base_down[$name]}' auf '$down' geaendert. Die Kette gemergter Migrationen ist unveraenderlich."
  fi
done

# Regel 3: neue Dateien fortlaufend nummeriert, Kette ab bisherigem Head.
declare -A seen_rev
new_files=()
for file in "$DIR"/*.py; do
  [[ -e "$file" ]] || continue
  is_migration "$file" || continue
  name="$(basename "$file")"
  [[ -n "${base_rev[$name]+x}" ]] && continue
  new_files+=("$name")
done

if [[ ${#new_files[@]} -gt 0 ]]; then
  # Sortierung nach Dateinummer (Praefix).
  mapfile -t new_files < <(printf '%s\n' "${new_files[@]}" | sort)
  expected_down="$base_max"
  expected_rev="$base_max"
  for name in "${new_files[@]}"; do
    file="$DIR/$name"
    rev="$(extract revision < "$file")"
    down="$(extract_down < "$file")"
    prefix="${name%%_*}"
    expected_rev="$(printf '%04d' $((10#$expected_rev + 1)))"
    if [[ ! "$rev" =~ ^[0-9]{4}$ ]]; then
      fail "Neue Migration '$name': revision '$rev' ist keine vierstellige Nummer (erwartet '$expected_rev')."
      continue
    fi
    if [[ "$prefix" != "$rev" ]]; then
      fail "Neue Migration '$name': Dateinummer '$prefix' entspricht nicht der revision '$rev'."
    fi
    if [[ -n "${seen_rev[$rev]+x}" ]]; then
      fail "Neue Migration '$name': revision '$rev' ist bereits durch '${seen_rev[$rev]}' belegt."
    fi
    seen_rev["$rev"]="$name"
    if [[ "$rev" != "$expected_rev" ]]; then
      fail "Neue Migration '$name': revision '$rev' erwartet '$expected_rev' (naechste freie Nummer nach Basis-Head '$base_max'). Bei Konflikten die eigene Migration auf die naechste freie Nummer setzen, nie bestehende umnummerieren."
    fi
    if [[ "$down" != "$expected_down" ]]; then
      fail "Neue Migration '$name': down_revision '$down' erwartet '$expected_down' (bisherige Head-Revision bzw. vorherige neue Migration)."
    fi
    expected_down="$rev"
  done
fi

if (( errors > 0 )); then
  echo "check-migrations: $errors Verstoss/Verstoesse. Bereits gemergte Migrationen werden nie umnummeriert oder geloescht, Konflikte werden durch eine neue Migration mit der naechsten freien Nummer geloest." >&2
  exit 1
fi
echo "check-migrations: OK (${#base_rev[@]} Migrationen der Basis unveraendert, ${#new_files[@]} neue)"
