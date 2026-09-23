# syntax=docker/dockerfile:1
# Build context: repository root, e.g.
#   docker build -f apps/web-portal/Dockerfile --build-arg MHVP_APP_VERSION=0.1.0 .
ARG NODE_IMAGE=node:22.22-alpine

FROM ${NODE_IMAGE} AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/web-portal/package.json apps/web-portal/
COPY apps/web-portal/package.json apps/web-portal/
COPY packages/config/package.json packages/config/
COPY packages/ui/package.json packages/ui/
COPY packages/api-client/package.json packages/api-client/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter "@mhvp/web-portal..."

FROM deps AS build
ARG MHVP_APP_VERSION=0.0.0-dev
ENV MHVP_APP_VERSION=${MHVP_APP_VERSION}
COPY packages packages
COPY apps/web-portal apps/web-portal
RUN pnpm --filter @mhvp/web-portal build

FROM ${NODE_IMAGE} AS runtime
# Apply Alpine security fixes (Trivy gate in CI).
# npm, npx and corepack are not needed at runtime; their bundled packages carry CVEs.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
       /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /opt/yarn* \
       /usr/local/bin/yarn /usr/local/bin/yarnpkg
ARG MHVP_APP_VERSION=0.0.0-dev
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 PORT=3001 MHVP_APP_VERSION=${MHVP_APP_VERSION}
WORKDIR /app
COPY --from=build --chown=node:node /repo/apps/web-portal/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web-portal/.next/static ./apps/web-portal/.next/static
USER node
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:3001/api/health || exit 1
CMD ["node", "apps/web-portal/server.js"]
