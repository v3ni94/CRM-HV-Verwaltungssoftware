# Runbook: deploy to staging and production

Source: MASTER-PROMPT 3.1, 17. The IONOS server already runs Traefik; the stack joins its
network (`infra/compose.prod.yaml`).

0. Before a deploy that interrupts service: announce the maintenance window (CRM, Platform,
   Maintenance and availability; banner from the lead time, default 48 hours) and mirror it in
   Uptime Kuma, see `verfuegbarkeit.md` section 3 (GB16-01).
1. CI green on the commit; the workflow `Images` (`.github/workflows/images.yml`) has pushed
   `ghcr.io/v3ni94/mhvp-{api,web-crm,web-portal}:<VERSION>` (M1-03, decided 26.09.2026). The
   server is logged in to ghcr.io with a read:packages token (`server-setup.md` section 4).
2. On the server: `.env.staging` / `.env.prod` in `DEPLOY_PATH` (secrets never in git).
3. `ENV=staging DEPLOY_HOST=... DEPLOY_PATH=... MHVP_IMAGE_REGISTRY=... MHVP_IMAGE_TAG=... make deploy`
4. Check `/api/v1/health/ready` and `/api/v1/platform/ops/metrics`. Staging: template
   `infra/env.staging.example` (own secrets, hosts, database, bucket; M9-07) and, after the
   deploy, `STAGING_API_URL=... STAGING_CRM_URL=... make staging-smoke` (reads only; refuses
   hosts without `staging`).
5. Production additionally needs `DEPLOY_CONFIRM=<tag>`; the script runs a backup before
   migrations. Rollback: previous tag, and for a failed migration restore the backup taken in
   step 5.

Own server without Traefik: see `server-setup.md` (`infra/compose.edge.yaml`). Without registry
access (fallback): `DEPLOY_BUILD=1` builds on the server. Missing server data: M9-01.
Manual release directly on the production server in `/opt/mhvp` (local images, `./mhvp.sh`
wrapper, verified backup, rollback hints): `infra/scripts/release.sh`, see `release.md`.
Monitoring and alerts after the deployment: `monitoring.md`. Availability target 99.5 percent
per month and monthly evaluation: `verfuegbarkeit.md`.
