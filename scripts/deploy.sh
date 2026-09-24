#!/usr/bin/env bash
# make deploy ENV=staging|prod (MASTER-PROMPT 17, M9). Brings the tagged release onto the
# server, runs the migrate container and restarts the stack behind Traefik.
#
# Image source:
#   registry (default): pulls MHVP_IMAGE_REGISTRY/mhvp-*:MHVP_IMAGE_TAG
#   DEPLOY_BUILD=1:     builds the images on the server from the git tag; no registry needed
#                       (single own server, OPEN_QUESTIONS M1-03). MHVP_IMAGE_REGISTRY defaults
#                       to "local".
# Server data are operator inputs (OPEN_QUESTIONS M9-01); without them the script stops before
# touching anything.
set -euo pipefail

ENV_NAME="${ENV:-}"
case "$ENV_NAME" in
  staging) PROJECT=mhvp-staging ;;
  prod) PROJECT=mhvp ;;
  *) echo "deploy: ENV=staging|prod required" >&2; exit 2 ;;
esac
BUILD="${DEPLOY_BUILD:-0}"
[[ "$BUILD" == 1 ]] && MHVP_IMAGE_REGISTRY="${MHVP_IMAGE_REGISTRY:-local}"
missing=()
for var in DEPLOY_HOST DEPLOY_PATH MHVP_IMAGE_REGISTRY MHVP_IMAGE_TAG; do
  [[ -n "${!var:-}" ]] || missing+=("$var")
done
if (( ${#missing[@]} )); then
  echo "deploy: missing ${missing[*]} (see docs/runbooks/deploy.md, OPEN_QUESTIONS M9-01)" >&2
  exit 2
fi
if [[ ! "$MHVP_IMAGE_TAG" =~ ^[A-Za-z0-9._-]+$ || ! "$MHVP_IMAGE_REGISTRY" =~ ^[A-Za-z0-9./:_-]+$ ]]; then
  echo "deploy: MHVP_IMAGE_TAG or MHVP_IMAGE_REGISTRY contains invalid characters" >&2
  exit 2
fi
if [[ "$ENV_NAME" == prod && "${DEPLOY_CONFIRM:-}" != "$MHVP_IMAGE_TAG" ]]; then
  echo "deploy: production needs DEPLOY_CONFIRM=$MHVP_IMAGE_TAG (explicit release)" >&2
  exit 2
fi

REG="$MHVP_IMAGE_REGISTRY"
TAG="$MHVP_IMAGE_TAG"
COMPOSE="docker compose -p $PROJECT --env-file .env.$ENV_NAME -f infra/compose.yaml -f infra/compose.prod.yaml"
if [[ "$BUILD" == 1 ]]; then
  FETCH="docker build -t $REG/mhvp-api:$TAG apps/api \
    && docker build -f apps/web-crm/Dockerfile -t $REG/mhvp-web-crm:$TAG . \
    && docker build -f apps/web-portal/Dockerfile -t $REG/mhvp-web-portal:$TAG ."
else
  FETCH="$COMPOSE pull"
fi
# Backup before every production migration (rollback path, docs/runbooks/deploy.md).
PRE=""
[[ "$ENV_NAME" == prod ]] && PRE="set -a && . ./.env.backup && set +a && scripts/backup.sh &&"
# umask 022: files pulled under a restrictive umask would be unreadable for the non-root
# users inside the images (seen 24.09.2026); the .env files keep their 600.
ssh "$DEPLOY_HOST" "cd '$DEPLOY_PATH' && umask 022 && git fetch --quiet --tags && git checkout --quiet '$TAG' \
  && chmod -R u=rwX,go=rX apps packages infra scripts \
  && export MHVP_IMAGE_REGISTRY='$REG' MHVP_IMAGE_TAG='$TAG' MHVP_APP_VERSION='$TAG' \
  && $FETCH && $PRE $COMPOSE run --rm migrate && $COMPOSE up -d --remove-orphans"
echo "deploy: $ENV_NAME $TAG done; check /api/v1/health/ready"
