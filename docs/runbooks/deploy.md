# Runbook: deploy to staging and production

Source: MASTER-PROMPT 3.1, 17. The IONOS server already runs Traefik; the stack joins its
network (`infra/compose.prod.yaml`).

1. CI green on the commit; images built and pushed with tag `MHVP_IMAGE_TAG` (registry M1-03).
2. On the server: `.env.staging` / `.env.prod` in `DEPLOY_PATH` (secrets never in git).
3. `ENV=staging DEPLOY_HOST=... DEPLOY_PATH=... MHVP_IMAGE_REGISTRY=... MHVP_IMAGE_TAG=... make deploy`
4. Check `/api/v1/health/ready` and `/api/v1/platform/ops/metrics`.
5. Production additionally needs `DEPLOY_CONFIRM=<tag>`; the script runs a backup before
   migrations. Rollback: previous tag, and for a failed migration restore the backup taken in
   step 5.

Own server without Traefik or registry: see `server-setup.md` (`DEPLOY_BUILD=1`,
`infra/compose.edge.yaml`). Missing server data: M9-01.
