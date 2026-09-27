#!/usr/bin/env bash
# Runs gitleaks over the working tree with the repository's .gitleaks.toml (allowlist for
# known fixture dummies such as CI passwords and test IBANs). Part of `make lint`
# (Sicherheitspruefung 27.09.2026, M27-02-03 / OE-M27-02-03).
#
# The binary is not installed by default in every dev environment; when it is missing this
# script reports that plainly and exits 0 so `make lint` keeps working offline. CI always runs
# gitleaks (see .github/workflows/ci.yml, job `secrets-scan`) via the pinned container image,
# so a missing local binary never means the check was skipped end to end.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v gitleaks >/dev/null 2>&1; then
  BIN=gitleaks
elif [ -x "${GITLEAKS_BIN:-}" ]; then
  BIN="$GITLEAKS_BIN"
else
  echo "secrets-scan: gitleaks Binary nicht gefunden, lokal NICHT ausgefuehrt (in CI verpflichtend, siehe .github/workflows/ci.yml)." >&2
  exit 0
fi

"$BIN" detect --source=. --config=.gitleaks.toml --redact --no-banner
