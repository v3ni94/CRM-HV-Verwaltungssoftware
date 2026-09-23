#!/usr/bin/env bash
# make deploy ENV=staging|prod (MASTER-PROMPT 17, M9). Pulls the tagged images on the server,
# runs the migrate container and restarts the stack behind the existing Traefik.
# Server, registry and DNS are operator inputs (OPEN_QUESTIONS M1-02, M1-03, M1-06, M9-01);
# without them the script stops before touching anything.
set -euo pipefail

ENV_NAME="${ENV:-}"
case "$ENV_NAME" in
  staging) PROJECT=mhvp-staging ;;
  prod) PROJECT=mhvp ;;
  *) echo "deploy: ENV=staging|prod required" >&2; exit 2 ;;
esac
missing=()
for var in DEPLOY_HOST DEPLOY_PATH MHVP_IMAGE_REGISTRY MHVP_IMAGE_TAG; do
  [[ -n "${!var:-}" ]] || missing+=("$var")
done
if (( ${#missing[@]} )); then
  echo "deploy: missing ${missing[*]} (see docs/runbooks/deploy.md, OPEN_QUESTIONS M9-01)" >&2
  exit 2
fi
if [[ "$ENV_NAME" == prod && "${DEPLOY_CONFIRM:-}" != "$MHVP_IMAGE_TAG" ]]; then
  echo "deploy: production needs DEPLOY_CONFIRM=$MHVP_IMAGE_TAG (explicit release)" >&2
  exit 2
fi

COMPOSE="docker compose -p $PROJECT --env-file .env.$ENV_NAME -f infra/compose.yaml -f infra/compose.prod.yaml"
# Backup before every production migration (rollback path, docs/runbooks/deploy.md).
PRE=""
[[ "$ENV_NAME" == prod ]] && PRE="scripts/backup.sh &&"
ssh "$DEPLOY_HOST" "cd '$DEPLOY_PATH' && git fetch --quiet && git checkout --quiet '$MHVP_IMAGE_TAG' \
  && export MHVP_IMAGE_REGISTRY='$MHVP_IMAGE_REGISTRY' MHVP_IMAGE_TAG='$MHVP_IMAGE_TAG' \
  && $PRE $COMPOSE pull && $COMPOSE run --rm migrate && $COMPOSE up -d --remove-orphans"
echo "deploy: $ENV_NAME $MHVP_IMAGE_TAG done; check /api/v1/health/ready"
