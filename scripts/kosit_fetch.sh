#!/usr/bin/env bash
# Downloads the pinned KoSIT validator and XRechnung configuration into MHVP_KOSIT_DIR
# (default: <repo>/.cache/kosit) and verifies the SHA-256 checksums of scripts/kosit.lock
# before anything is unpacked (AC11-01, P05). Used by `make kosit-fetch` and the CI job
# `xrechnung-kosit`.
#
# Optional environment (override the lock file, e.g. CI repository variables):
#   KOSIT_JAR_URL, KOSIT_JAR_SHA256, KOSIT_CFG_URL, KOSIT_CFG_SHA256   empty means: use lock
#   MHVP_KOSIT_DIR   target directory
#   KOSIT_LOCK       alternative lock file
#   KOSIT_FORCE=1    download again although the pins are already unpacked
#
# Exit codes: 0 ready, 2 usage or missing tool, 3 pin missing or placeholder,
#             4 checksum mismatch (nothing unpacked), 5 download failed.
# The last line on stdout is MHVP_KOSIT_DIR=<dir>; all messages go to stderr.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lock="${KOSIT_LOCK:-$root/scripts/kosit.lock}"
dir="${MHVP_KOSIT_DIR:-$root/.cache/kosit}"

say() { echo "kosit_fetch: $*" >&2; }

if [ ! -f "$lock" ]; then
  say "lock file $lock not found"
  exit 2
fi
for tool in curl unzip; do
  command -v "$tool" >/dev/null 2>&1 || { say "$tool is required"; exit 2; }
done
if command -v sha256sum >/dev/null 2>&1; then
  hash_file() { sha256sum "$1" | cut -d ' ' -f 1; }
elif command -v shasum >/dev/null 2>&1; then
  hash_file() { shasum -a 256 "$1" | cut -d ' ' -f 1; }
else
  say "sha256sum or shasum is required"
  exit 2
fi

lock_value() { sed -n "s/^$1=//p" "$lock" | head -n 1 | tr -d '\r'; }
jar_url="${KOSIT_JAR_URL:-$(lock_value KOSIT_JAR_URL)}"
jar_sha="${KOSIT_JAR_SHA256:-$(lock_value KOSIT_JAR_SHA256)}"
cfg_url="${KOSIT_CFG_URL:-$(lock_value KOSIT_CFG_URL)}"
cfg_sha="${KOSIT_CFG_SHA256:-$(lock_value KOSIT_CFG_SHA256)}"

check_pin() { # name url sha256
  if [ -z "$2" ] || ! [[ "$3" =~ ^[0-9a-fA-F]{64}$ ]]; then
    say "pin for '$1' is missing or a placeholder (url='$2', sha256='$3')."
    say "Set a real value in $lock (docs/runbooks/xrechnung-kosit.md, section Pins aktualisieren)."
    exit 3
  fi
}
check_pin validator "$jar_url" "$jar_sha"
check_pin config "$cfg_url" "$cfg_sha"

stamp="$dir/.pins"
want="$jar_sha $cfg_sha"
if [ "${KOSIT_FORCE:-0}" != "1" ] && [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$want" ] \
  && ls "$dir"/validationtool-*-standalone.jar >/dev/null 2>&1 && [ -f "$dir/cfg/scenarios.xml" ]; then
  say "pinned validator already present in $dir"
  echo "MHVP_KOSIT_DIR=$dir"
  exit 0
fi

mkdir -p "$dir"
work="$(mktemp -d "$dir/.fetch.XXXXXX")"
trap 'rm -rf "$work"' EXIT

fetch() { # name url sha target
  say "downloading $1"
  curl -fsSL --retry 2 --retry-delay 2 "$2" -o "$work/$1.zip" || { say "download of $1 failed: $2"; exit 5; }
  actual="$(hash_file "$work/$1.zip")"
  expected="$(echo "$3" | tr 'A-F' 'a-f')"
  if [ "$actual" != "$expected" ]; then
    say "checksum mismatch for $1: expected $expected, got $actual. Nothing was unpacked."
    exit 4
  fi
}
fetch validator "$jar_url" "$jar_sha"
fetch config "$cfg_url" "$cfg_sha"

# Both archives are verified: replace the previous installation.
rm -rf "$dir/cfg" "$dir/libs" "$dir"/validationtool-*.jar "$dir/.pins"
mkdir -p "$dir/cfg"
unzip -q -o "$work/validator.zip" -d "$dir"
unzip -q -o "$work/config.zip" -d "$dir/cfg"
if ! ls "$dir"/validationtool-*-standalone.jar >/dev/null 2>&1 || [ ! -f "$dir/cfg/scenarios.xml" ]; then
  say "unexpected archive layout (validationtool-*-standalone.jar or cfg/scenarios.xml missing)"
  exit 2
fi
echo "$want" >"$stamp"
say "ready in $dir"
echo "MHVP_KOSIT_DIR=$dir"
