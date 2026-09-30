#!/usr/bin/env bash
# make staging-smoke (M9-07): reads only, changes nothing. Checks that the staging stack
# answers after `make deploy ENV=staging`:
#   STAGING_API_URL   e.g. https://api.staging.mueller-holding.ag   (required)
#   STAGING_CRM_URL   e.g. https://crm.staging.mueller-holding.ag   (required)
#   STAGING_PORTAL_URL optional
# Refuses production hosts by name so that the target cannot be mixed up.
set -euo pipefail

: "${STAGING_API_URL:?STAGING_API_URL must be set}"
: "${STAGING_CRM_URL:?STAGING_CRM_URL must be set}"
for url in "$STAGING_API_URL" "$STAGING_CRM_URL" "${STAGING_PORTAL_URL:-}"; do
  [[ -z "$url" ]] && continue
  case "$url" in
    *staging*|*localhost*|*127.0.0.1*) ;;
    *) echo "staging-smoke: $url does not look like a staging host, refused" >&2; exit 2 ;;
  esac
done

failed=0
check() { # name url expected-status-regex
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$2" || echo 000)"
  if [[ "$code" =~ $3 ]]; then
    echo "ok    $1 ($code)"
  else
    echo "FAIL  $1 ($code, expected $3) $2" >&2
    failed=1
  fi
}

API="${STAGING_API_URL%/}/api/v1"
check "api live" "$API/health/live" '^200$'
check "api ready (database, redis, storage)" "$API/health/ready" '^200$'
check "api rejects anonymous access" "$API/platform/ops/metrics" '^(401|403)$'
check "crm login page (anmelden)" "${STAGING_CRM_URL%/}/anmelden" '^(200|307|308)$'
[[ -z "${STAGING_PORTAL_URL:-}" ]] || check "portal" "${STAGING_PORTAL_URL%/}/" '^(200|307|308)$'
version="$(curl -sS --max-time 15 "$API/health/ready" 2>/dev/null | head -c 300 || true)"
echo "info  ready answer: ${version:-none}"
exit "$failed"
