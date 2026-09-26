#!/usr/bin/env bash
# Validates XRechnung files with the official KoSIT validator (A12, P05).
#
# The validator and the XRechnung configuration are not bundled with the repository and are
# not downloaded here (no network access is assumed). Place them under MHVP_KOSIT_DIR:
#   MHVP_KOSIT_DIR/validationtool-<version>-standalone.jar
#     from https://github.com/itplr-kosit/validator/releases (tested: 1.5.0)
#   MHVP_KOSIT_DIR/cfg/scenarios.xml plus resources/
#     unpacked from https://github.com/itplr-kosit/validator-configuration-xrechnung/releases
#     (tested: validator-configuration-xrechnung_3.0.2_2024-10-31.zip)
# Usage: scripts/kosit_validate.sh <file.xml> [more.xml ...]
# Exit code 0 means every file was accepted; reports are written to MHVP_KOSIT_DIR/report.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <file.xml> [more.xml ...]" >&2
  exit 2
fi
: "${MHVP_KOSIT_DIR:?MHVP_KOSIT_DIR is not set (directory with the validator jar and cfg/)}"
jar="$(ls "$MHVP_KOSIT_DIR"/validationtool-*-standalone.jar 2>/dev/null | grep -v java8 | head -n 1 || true)"
if [ -z "$jar" ]; then
  echo "no validationtool-*-standalone.jar in $MHVP_KOSIT_DIR" >&2
  exit 2
fi
if [ ! -f "$MHVP_KOSIT_DIR/cfg/scenarios.xml" ]; then
  echo "no cfg/scenarios.xml in $MHVP_KOSIT_DIR (XRechnung configuration missing)" >&2
  exit 2
fi
mkdir -p "$MHVP_KOSIT_DIR/report"
exec java -jar "$jar" -s "$MHVP_KOSIT_DIR/cfg/scenarios.xml" -r "$MHVP_KOSIT_DIR/cfg" \
  -o "$MHVP_KOSIT_DIR/report" "$@"
