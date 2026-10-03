#!/usr/bin/env bash
# make deploy ENV=staging|prod (MASTER-PROMPT 17, M9). Brings the tagged release onto the
# server, runs the migrate container and restarts the stack behind Traefik.
#
# Image source:
#   registry (default): pulls MHVP_IMAGE_REGISTRY/mhvp-*:MHVP_IMAGE_TAG; the registry is
#                       ghcr.io/v3ni94 (M1-03, decided 26.09.2026), images are pushed by
#                       .github/workflows/images.yml; the server must be logged in (read:packages
#                       PAT, docs/runbooks/server-setup.md section 4).
#   DEPLOY_BUILD=1:     fallback without registry: builds the images on the server from the git
#                       tag. MHVP_IMAGE_REGISTRY defaults to "local".
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
MHVP_IMAGE_REGISTRY="${MHVP_IMAGE_REGISTRY:-ghcr.io/v3ni94}"
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
# GAJ-508: DEPLOY_ROLLBACK=1 returns to an older tag without the migrate step (an older
# migrate image does not know the newer head revision; the schema stays).
MIGRATE="$COMPOSE run --rm migrate &&"
if [[ "${DEPLOY_ROLLBACK:-0}" == 1 ]]; then
  MIGRATE=""
  PRE=""
fi
# GAJ-508: remember the running release for the rollback step (empty on the first deploy).
PREV_TAG="$(ssh "$DEPLOY_HOST" "cd '$DEPLOY_PATH' && git describe --tags --exact-match 2>/dev/null || true")"
ssh "$DEPLOY_HOST" "cd '$DEPLOY_PATH' && umask 022 && git fetch --quiet --tags && git checkout --quiet '$TAG' \
  && chmod -R u=rwX,go=rX apps packages infra scripts \
  && export MHVP_IMAGE_REGISTRY='$REG' MHVP_IMAGE_TAG='$TAG' MHVP_APP_VERSION='$TAG' \
  && $FETCH && $PRE $MIGRATE $COMPOSE up -d --remove-orphans"
echo "deploy: $ENV_NAME $TAG done${PREV_TAG:+ (previous $PREV_TAG)}"

# GAJ-508: smoke test after the deploy (staging only, scripts/staging-smoke.sh reads only).
# On failure the script offers the rollback to the previous tag: images and code only, the
# database schema stays (migrations are forward only, docs/runbooks/deploy.md); with
# DEPLOY_AUTO_ROLLBACK=1 it runs the rollback itself. Production keeps the manual check.
if [[ "$ENV_NAME" != staging ]]; then
  echo "deploy: check /api/v1/health/ready"
  exit 0
fi
if [[ "${DEPLOY_SKIP_SMOKE:-0}" == 1 ]]; then
  echo "deploy: smoke test skipped (DEPLOY_SKIP_SMOKE=1); run make staging-smoke" >&2
  exit 0
fi
if [[ -z "${STAGING_API_URL:-}" || -z "${STAGING_CRM_URL:-}" ]]; then
  echo "deploy: STAGING_API_URL and STAGING_CRM_URL missing, smoke test not run" >&2
  exit 3
fi
if "$(dirname "${BASH_SOURCE[0]}")/staging-smoke.sh"; then
  echo "deploy: staging smoke test passed"
  exit 0
fi
echo "deploy: staging smoke test FAILED for $TAG" >&2
if [[ -z "$PREV_TAG" ]]; then
  echo "deploy: no previous tag known, rollback must be done manually" >&2
  exit 4
fi
ROLLBACK="ENV=staging MHVP_IMAGE_TAG=$PREV_TAG DEPLOY_ROLLBACK=1 scripts/deploy.sh"
if [[ "${DEPLOY_AUTO_ROLLBACK:-0}" != 1 || "${DEPLOY_ROLLBACK:-0}" == 1 ]]; then
  echo "deploy: rollback step: $ROLLBACK" >&2
  exit 4
fi
echo "deploy: rolling back to $PREV_TAG (code and images only, schema stays)" >&2
ssh "$DEPLOY_HOST" "cd '$DEPLOY_PATH' && umask 022 && git checkout --quiet '$PREV_TAG' \
  && export MHVP_IMAGE_REGISTRY='$REG' MHVP_IMAGE_TAG='$PREV_TAG' MHVP_APP_VERSION='$PREV_TAG' \
  && $COMPOSE up -d --remove-orphans"
exit 4
