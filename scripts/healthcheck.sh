#!/usr/bin/env bash
# Periodic health check for the own server (M9-04). Checks readiness of the API and the age of
# the newest backup; on failure it logs to the journal and, if ALERT_WEBHOOK_URL is set, posts a
# short JSON message (no personal data). Exit code 1 on any failure.
set -euo pipefail

: "${HEALTH_URL:?HEALTH_URL must be set, e.g. https://api.example.de/api/v1/health/ready}"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"
problems=()

curl -fsS --max-time 10 -o /dev/null "$HEALTH_URL" || problems+=("API nicht bereit ($HEALTH_URL)")
if [[ -n "${BACKUP_DIR:-}" ]]; then
  newest="$(find "$BACKUP_DIR" -maxdepth 1 -name 'mhvp-2*.dump*' ! -name '*.sha256' -mmin "-$((MAX_AGE_HOURS * 60))" | head -1)"
  [[ -n "$newest" ]] || problems+=("kein Backup in den letzten $MAX_AGE_HOURS Stunden")
fi

if (( ${#problems[@]} )); then
  text="MHVP $(hostname): ${problems[*]}"
  echo "$text" >&2
  if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    body="$(printf '{"text":"%s"}' "${text//\"/\'}")"
    curl -fsS --max-time 10 -H 'content-type: application/json' -d "$body" "$ALERT_WEBHOOK_URL" >/dev/null || true
  fi
  exit 1
fi
echo "health: ok"
